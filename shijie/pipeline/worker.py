import fcntl
import json
import signal
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
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
    return Job.objects.filter(status='running',executor='server').update(status='failed', message='执行进程已中断，中间图层保留，请手动续拆', finished_at=timezone.now())


def resources(job):
    connection = job_root(job) / 'connection.json'
    snapshot = json.loads(connection.read_text()) if connection.exists() else {'provider':ai.selected_provider(job.owner)}
    result = set()
    if snapshot.get('needsCodex', snapshot['provider']=='codex'): result.add('codex:' + str(job.owner_id))
    if snapshot['provider']=='local': result.add('local-gpu')
    if snapshot.get('project'): result.add('project:' + str(job.owner_id) + ':' + snapshot['project'])
    return result


def claim(blocked=frozenset()):
    with transaction.atomic():
        Job.objects.filter(status='queued',cancel_requested=True).update(status='cancelled',message='已取消',finished_at=timezone.now())
        # ponytail: scan the bounded persistent queue; add indexed resource columns if queue scale requires it.
        for job in Job.objects.select_for_update(skip_locked=True).filter(status='queued', cancel_requested=False,executor='server').order_by('created_at'):
            if resources(job) & blocked: continue
            job.status = 'running'
            job.started_at = job.heartbeat = timezone.now()
            job.save(update_fields=['status', 'started_at', 'heartbeat'])
            return job
        return None


def run(job):
    root = job_root(job)
    connection = root / 'connection.json'
    snapshot = json.loads(connection.read_text()) if connection.exists() else {'provider':ai.selected_provider(job.owner)}
    provider = snapshot['provider']
    from .providers import job_credentials
    credentials = job_credentials(job.owner, snapshot) if provider!='local' else None
    if provider == 'local':
        credentials = {'local_model_root': str(settings.LOCAL_MODEL_ROOT)}
    if provider == 'company' and not credentials:
        raise ValueError('公司 Agent 连接已停用')
    credentials['mode'] = job.mode
    process = start('run_job.py', root, user_root(job.owner_id) / 'codex', job.pk, snapshot.get('codexModel', job.owner.codex_model), input_data=credentials or {})
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
            if job.cancel_requested or not allowed(job.owner) or expired or (root/'cancel').exists():
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
        # One durable coordinator; two child jobs, with Codex account and local GPU exclusivity.
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recover()
        def shutdown(*args):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, shutdown)
        active = {}
        pool = ThreadPoolExecutor(max_workers=2)
        def execute(job):
            try:
                close_old_connections()
                run(job)
            except Exception:
                Job.objects.filter(pk=job.pk, status='running').update(status='failed', message='执行已中断，中间图层保留', finished_at=timezone.now())
            finally:
                close_old_connections()
        try:
            while True:
                close_old_connections()
                for future in list(active):
                    if future.done(): future.result(); active.pop(future)
                blocked = set().union(*(keys for _, keys in active.values()))
                job = claim(blocked) if len(active)<2 else None
                if job:
                    active[pool.submit(execute,job)] = (job,resources(job))
                    if once:
                        wait(active)
                        return
                elif once and not active:
                    return
                elif active:
                    wait(active, timeout=.5, return_when=FIRST_COMPLETED)
                else:
                    time.sleep(.5)
        finally:
            for job,_ in active.values():
                root=job_root(job);root.mkdir(parents=True,exist_ok=True);(root/'cancel').touch()
            pool.shutdown(wait=True)
            for job,_ in active.values():
                Job.objects.filter(pk=job.pk, status__in=['running','cancelled']).update(status='failed', message='执行进程已中断，中间图层保留，请手动续拆', finished_at=timezone.now())
