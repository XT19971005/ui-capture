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
    used = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
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
    return decode_job(json.loads(Path(path).read_text()))
