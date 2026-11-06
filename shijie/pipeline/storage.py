import json
import os
import shutil
import tempfile
from pathlib import Path
from django.conf import settings
from image_wire import decode_job
from local_project_store import pack_record


def user_root(user_id):
    root = settings.DATA_ROOT / 'users' / str(int(user_id))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def job_root(job):
    return user_root(job.owner_id) / 'jobs' / str(job.pk)


def check_space(root, size=0):
    # ponytail: Per-user directory scan is O(number of files); replace with a ledger when measured necessary.
    used = 0
    for path in root.rglob('*'):
        try:
            if path.is_file(): used += path.stat().st_size
        except FileNotFoundError:
            pass  # Atomic job snapshots may be renamed during the scan.
    if used + size > settings.USER_QUOTA or shutil.disk_usage(root).free - size < settings.MIN_FREE:
        raise OSError('存储空间不足，原工程保留')


def write_json(path, value):
    path = Path(path)
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        # Persist the rename as well as the bytes across host power failure.
        if os.name != 'nt':
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def write_scene(path, value):
    write_json(path, pack_record(value))


def read_scene(path):
    return decode_job(json.loads(Path(path).read_text(encoding='utf8')))


def connection_version(path):
    import hashlib
    try:return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:return None


def commit_connection(user, path, version, value):
    """Network checks run before this short, shared commit boundary."""
    from django.db import transaction
    from shijie.accounts.models import User
    from .models import Job
    with transaction.atomic():
        User.objects.select_for_update().get(pk=user.pk)
        if Job.objects.filter(owner=user,status__in=['queued','running']).exists():
            raise ValueError('请先完成或取消当前任务，再修改或测试 AI 连接')
        if connection_version(path)!=version:
            raise ValueError('连接设置已在另一窗口发生变化，请重新打开 AI 设置后重试；当前连接已保留')
        write_json(path,value)
        return connection_version(path)
