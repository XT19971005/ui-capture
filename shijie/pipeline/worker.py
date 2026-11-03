import fcntl
import json
import json
import signal
import uuid
import time
from django.conf import settings
from django.db import transaction, close_old_connections
from django.utils import timezone
from shijie.accounts.services import allowed
from .models import Job
from . import company, ai
from .storage import job_root, user_root, write_json
from .processes import start, stop


def recover():
    # Called only while holding the host-wide worker lock: never replay a potentially billed turn.
    return Job.objects.filter(status='running').update(status='failed', message='执行进程已中断，中间图层保留，请手动续拆', finished_at=timezone.now())


def claim():
    with transaction.atomic():
        job = Job.objects.select_for_update(skip_locked=True).filter(status='queued').order_by('created_at').first()
        if job:
            job.status = 'running'
            job.started_at = job.heartbeat = timezone.now()
            job.save(update_fields=['status', 'started_at', 'heartbeat'])
        return job


def run(job):
    root = job_root(job)
    connection = root / 'connection.json'
    provider = json.loads(connection.read_text())['provider'] if connection.exists() else ai.selected_provider(job.owner)
    credentials = company.credentials(job.owner) if provider == 'company' else None
    if provider == 'local':
        credentials = {'local_model_root': str(settings.LOCAL_MODEL_ROOT)}
    if provider == 'company' and not credentials:
        raise ValueError('公司 Agent 连接已停用')
    process = start('run_job.py', root, user_root(job.owner_id) / 'codex', job.pk, job.owner.codex_model, input_data=credentials or {})
    started = time.monotonic()
    cancellation = None
    expired = False
    result = {'status': 'failed', 'message': '任务进程异常退出，中间图层已保留'}
    try:
        while process.poll() is None:
            close_old_connections()
            job.refresh_from_db()
            job.owner.refresh_from_db()
            now = time.monotonic()
            expired = now - started > settings.JOB_TIMEOUT
            if job.cancel_requested or not allowed(job.owner) or expired:
                (root / 'cancel').touch()
                cancellation = cancellation or now
                if now - cancellation > 12:
                    stop(process)
                    result = {'status': 'failed' if expired else 'cancelled', 'message': '任务超时，结果保留' if expired else '已取消，中间图层保留'}
                    break
            progress = root / 'progress.json'
            updates = {'heartbeat': timezone.now()}
            try:
                value = json.loads(progress.read_text())
            except FileNotFoundError:
                pass  # A missing progress snapshot is not a failed inference; retry next poll.
            else:
                updates.update(progress=max(job.progress, value['progress']), message=value['message'], partial_revision=value['revision'])
            Job.objects.filter(pk=job.pk).update(**updates)
            time.sleep(0.5)
        if (root / 'finished.json').exists():
            result = json.loads((root / 'finished.json').read_text())
        job.refresh_from_db()
        if job.cancel_requested or not allowed(job.owner):
            result = {'status': 'cancelled', 'message': '已取消，中间图层保留'}
        elif expired:
            result = {'status': 'failed', 'message': '任务超时，原图和中间图层已保留，可继续拆分'}
            write_json(root / 'finished.json', result)
        Job.objects.filter(pk=job.pk).update(**result, finished_at=timezone.now(), progress=1 if result['status'] == 'completed' else job.progress)
    finally:
        try:
            if provider == 'local' and result['status'] != 'completed':
                reference = root / 'local-request.json'
                if reference.exists():
                    native_id = str(uuid.UUID(json.loads(reference.read_text())['id']))
                    (settings.LOCAL_MODEL_ROOT / 'jobs' / native_id / 'cancel').touch()
        finally:
            stop(process)


def work(once=False):
    settings.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with (settings.DATA_ROOT / '.worker.lock').open('a') as lock:
        # ponytail: One worker per data volume. Upgrade to resource-aware parallel scheduling when needed.
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recover()
        def shutdown(*args):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, shutdown)
        while True:
            close_old_connections()
            job = claim()
            if job:
                try:
                    run(job)
                except BaseException:
                    Job.objects.filter(pk=job.pk, status='running').update(status='failed', message='执行已中断，中间图层保留', finished_at=timezone.now())
                    raise
            elif once:
                return
            else:
                time.sleep(1)
            if once:
                return
