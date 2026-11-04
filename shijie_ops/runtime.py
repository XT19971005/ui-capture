"""Private host executor. Only this process can read deployment secrets or run Docker."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
import tomllib
from urllib.parse import unquote, urlsplit
import uuid

DEPLOYMENTS = {'deploy', 'resume_deployment', 'repair_deployment'}
MUTATIONS = DEPLOYMENTS | {'control_service', 'backup'}
SCHEMAS = {
    'authorize_user': ({'email'}, {'email'}),
    'get_project_status': (set(), set()), 'diagnose': (set(), set()),
    'get_job': ({'job_id'}, {'job_id'}), 'get_logs': (set(), {'job_id', 'service'}),
    'deploy': ({'commit', 'request_id'}, {'commit', 'request_id'}),
    'resume_deployment': ({'pending_commit', 'request_id'}, {'pending_commit', 'request_id'}),
    'repair_deployment': ({'commit', 'pending_commit', 'request_id'}, {'commit', 'pending_commit', 'request_id'}),
    'control_service': ({'operation', 'service', 'request_id'}, {'operation', 'service', 'request_id'}),
    'backup': ({'request_id'}, {'request_id'}),
}
LOG_LIMIT = 128 * 1024


def user_email(value):
    # Corporate identities use ASCII mailboxes; reject ambiguous/control input before normalization.
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('用户邮箱无效。')
    email = value.strip().lower()
    label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
    if (len(email) > 254 or not re.fullmatch(r'[a-z0-9_+-]+(?:\.[a-z0-9_+-]+)*@' + label + r'(?:\.' + label + r')+', email)
            or len(email.split('@')[0]) > 64):
        raise ValueError('用户邮箱无效。')
    return email

class Redactor:
    def __init__(self, directory):
        self.secrets = set()
        self.valid = True
        try:
            cfg = tomllib.loads((directory / 'config.toml').read_text())
            def collect(value, key=''):
                if isinstance(value, dict):
                    for k, v in value.items():
                        collect(v, k)
                elif isinstance(value, str):
                    if re.search('secret|password|token|api_key', key, re.I) and len(value) >= 4:
                        self.secrets.add(value)
                    if '://' in value:
                        password = urlsplit(value).password
                        if password:
                            self.secrets.update((password, unquote(password)))
            collect(cfg)
            password = (directory / 'postgres-password').read_text().strip()
            if password:
                self.secrets.add(password)
        except (OSError, ValueError):
            # Invalid config must not turn log retrieval into a secret-disclosure fallback.
            self.valid = False

    def __call__(self, text):
        if not self.valid:
            return '[日志暂不可展示：无法读取完整脱敏配置，请先修复私有配置。]'
        for value in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(value, '[REDACTED]')
        text = re.sub(r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+@', r'\1[REDACTED]@', text)
        text = re.sub(r'(?i)([?&](?:token|key|secret|password|access_token|code|state)=)[^\s&#]+', r'\1[REDACTED]', text)
        text = re.sub(r'(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)[^\s]+', r'\1[REDACTED]', text)
        text = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|glpat-[A-Za-z0-9_-]{16,})', '[REDACTED]', text)
        text = re.sub(r'''(?ix)((?:password|secret_key|client_secret|api_key|access_token|token)["']?\s*[:=]\s*)
                        ("[^"\n]*"|'[^'\n]*'|[^\s,;}]+)''', r'\1[REDACTED]', text)
        return text

class Operations:
    def __init__(self, directory, state, *, env=None, timeout=7200):
        self.directory, self.state = map(lambda p: Path(p).resolve(), (directory, state))
        self.controller = Path(__file__).resolve().parents[1] / "shijiectl"
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = (self.state / 'executor.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.env = dict(env) if env is not None else {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                                                       'LANG': 'C.UTF-8', 'HOME': '/root', 'PYTHONUNBUFFERED': '1'}
        self.timeout = timeout
        self.worker = None
        self.process = None
        self.stopping = threading.Event()
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, actor TEXT NOT NULL, request_id TEXT NOT NULL,
                action TEXT NOT NULL, params TEXT NOT NULL, status TEXT NOT NULL,
                phase TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                exit_code INTEGER, log TEXT NOT NULL DEFAULT '', UNIQUE(actor, request_id))''')
            db.execute("UPDATE jobs SET status='interrupted', updated=? WHERE status IN ('queued','running')", (time.time(),))
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_operation ON jobs((1)) WHERE status IN ('queued','running')")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.state / 'jobs.sqlite3', timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def close(self):
        if self.lock.closed:
            return
        self.stopping.set()
        if self.worker:
            self.worker.join(timeout=10)
        if self.worker and self.worker.is_alive():
            raise RuntimeError('执行器仍未停止，保留锁；请检查子进程。')
        self.lock.close()

    def snapshot(self):
        result = {'project': 'shijie'}
        for label, filename in [('active', 'deployment.json'), ('pending', 'pending.json')]:
            path = self.directory / filename
            record = json.loads(path.read_text()) if path.exists() else None
            result[label] = None if record is None else {k: record.get(k) for k in
                                                        ('commit', 'image', 'phase', 'backup', 'repair_history')}
        with self.db() as db:
            row = db.execute('SELECT id, status, action, phase FROM jobs ORDER BY created DESC LIMIT 1').fetchone()
            result['latest_job'] = dict(row) if row else None
        return result


    def dispatch(self, actor, action, params):
        actor = user_email(actor) if actor != 'local-admin' else actor
        if action not in SCHEMAS or not isinstance(params, dict):
            raise ValueError('不支持的操作。')
        required, allowed = SCHEMAS[action]
        if required - params.keys() or params.keys() - allowed or any(type(v) is not str for v in params.values()):
            raise ValueError('操作参数不匹配。')
        for key in ('commit', 'pending_commit'):
            if key in params and not re.fullmatch(r'[0-9a-f]{40}', params[key]):
                raise ValueError('提交必须是完整的小写 Git SHA（40 位）。')
        if 'job_id' in params and not re.fullmatch(r'[0-9a-f]{32}', params['job_id']):
            raise ValueError('任务 ID 无效。')
        services = ('web', 'worker', 'all') if action == 'control_service' else ('web', 'worker', 'db')
        if 'service' in params and params['service'] not in services:
            raise ValueError('服务名称不在允许列表。')
        if 'operation' in params and params['operation'] not in ('start', 'stop', 'restart'):
            raise ValueError('仅支持 start/stop/restart。')
        if action == 'authorize_user':
            return {'allowed': self.authorize_user(user_email(params['email']))}
        if action in MUTATIONS:
            return self.submit(actor, action, params)
        if action == 'get_project_status': return self.snapshot()
        if action == 'get_job': return self.job(params['job_id'])
        if action == 'get_logs':
            if 'job_id' in params:
                with self.db() as db:
                    row = db.execute('SELECT log FROM jobs WHERE id=?', (params['job_id'],)).fetchone()
                if not row: raise ValueError('任务不存在。')
                return {'text': Redactor(self.directory)(row['log']), 'tail_limit': LOG_LIMIT}
            return self.capture('logs', params.get('service', 'web'))
        result = self.snapshot()
        result['services'] = self.capture('status', timeout=8)
        try:
            config = tomllib.loads((self.directory / 'config.toml').read_text())
            info = os.statvfs(config['deployment']['data_dir'])
            result['disk'] = {'available_bytes': info.f_bavail * info.f_frsize}
        except (OSError, ValueError, KeyError):
            result['disk'] = {'error': '无法读取数据盘空间。'}
        result['next_action'] = ('有未完成发布，先看日志，再使用 resume_deployment 或 repair_deployment。' if result['pending'] else '可发布 origin/main 历史中的完整 SHA。')
        return result


    def authorize_user(self, email):
        # ponytail: one bounded DB lookup per request; no cache, so revocation is immediate.
        # Query the stable auth tables through the DB container, even when Web is down.
        # If throughput becomes material, use a dedicated read-only DB connection pool.
        query = """SET statement_timeout = '3s';
SET default_transaction_read_only = on;
SELECT count(*) = 1 AND coalesce(bool_and(u.is_active AND (u.is_superuser OR EXISTS (
 SELECT 1 FROM accounts_user_groups ug JOIN auth_group g ON g.id = ug.group_id
 WHERE ug.user_id = u.id AND g.name = '超级管理员'))), false)
FROM accounts_user u WHERE lower(u.email) = :'email';
"""
        try:
            project = 'shijie'
            def run(args, data=None):
                return subprocess.run(args, input=data, capture_output=True, text=True, encoding='utf-8',
                                      env=self.env, timeout=5, check=True).stdout.strip()
            container = run(['docker', 'ps', '-q', '--no-trunc', '--filter',
                             'label=com.docker.compose.project=' + project, '--filter',
                             'label=com.docker.compose.service=db'])
            if not re.fullmatch(r'[0-9a-f]{64}', container):
                raise ValueError('数据库容器不唯一或不可用。')
            result = run(['docker', 'exec', '-i', container, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
                          '-v', 'email=' + email, '-U', 'shijie', '-d', 'shijie'], query)
            if result not in ('t', 'f'):
                raise ValueError('身份查询结果无效。')
            return result == 't'
        except (OSError, ValueError, subprocess.SubprocessError):
            raise ValueError('超级管理员身份校验不可用。') from None

    def argv(self, *args):
        return [sys.executable, '-m', 'shijie_ops.release', args[0], '--config-dir', str(self.directory),
                '--params', json.dumps({'service': args[1]} if len(args) > 1 else {})]


    def capture(self, *args, timeout=20):
        process = subprocess.Popen(self.argv(*args), env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        output, deadline = bytearray(), time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as poll:
                poll.register(process.stdout, selectors.EVENT_READ)
                while poll.get_map():
                    if time.monotonic() > deadline or len(output) > 1024 * 1024:
                        return {'exit_code': None, 'text': '诊断超时或输出过大；请缩小检查范围或在本机核对。'}
                    for key, _ in poll.select(.2):
                        chunk = os.read(key.fileobj.fileno(), 8192)
                        if not chunk:
                            poll.unregister(key.fileobj)
                        else:
                            output.extend(chunk)
            return {'exit_code': process.wait(timeout=3),
                    'text': Redactor(self.directory)(output.decode('utf-8', 'replace'))[-LOG_LIMIT:]}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
            process.stdout.close()

    def job(self, job_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise ValueError('任务不存在。')
        result = dict(row)
        result.pop('log')
        result['params'] = json.loads(result['params'])
        return result

    def submit(self, actor, action, params):
        request_id = params['request_id']
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,96}', request_id):
            raise ValueError('request_id 须为 1–96 位字母、数字或 ._:-。')
        if self.stopping.is_set():
            raise ValueError('执行器正在停止。')
        encoded = json.dumps(params, sort_keys=True)
        job_id = uuid.uuid4().hex
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM jobs WHERE actor=? AND request_id=?', (actor, request_id)).fetchone()
            if previous:
                if previous['action'] != action or previous['params'] != encoded:
                    raise ValueError('同一 request_id 不能用于不同操作或参数。')
                return self.job(previous['id'])
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
                raise ValueError('另一运维操作正在执行，请查询其状态。')
            now = time.time()
            db.execute('INSERT INTO jobs(id,actor,request_id,action,params,status,phase,created,updated) '
                       "VALUES(?,?,?,?,?,'queued','queued',?,?)", (job_id, actor, request_id, action, encoded, now, now))
        # ponytail: one host / one worker; SQLite is the durable history and admission lock.
        # Multiple hosts would require a real distributed scheduler, not more local threads.
        self.worker = threading.Thread(target=self.execute, args=(job_id,), daemon=True)
        self.worker.start()
        return self.job(job_id)

    def update(self, job_id, **fields):
        with self.db() as db:
            db.execute('UPDATE jobs SET ' + ', '.join(k + '=?' for k in fields) + ', updated=? WHERE id=?',
                       (*fields.values(), time.time(), job_id))

    def append(self, job_id, line, redact):
        if line.startswith('SHIJIE_STAGE:'):
            stage = line.strip().partition(':')[2]
            if stage in ('build', 'backup', 'stop_writers', 'migrate', 'check', 'preflight', 'health_check'):
                self.update(job_id, phase=stage)
        safe = redact(line)
        with self.db() as db:
            db.execute('UPDATE jobs SET log=substr(log || ?, -?), updated=? WHERE id=?',
                       (safe, LOG_LIMIT, time.time(), job_id))

    def execute(self, job_id):
        status, code = 'failed', None
        redact = Redactor(self.directory)
        process = None
        try:
            job = self.job(job_id)
            params = job['params']
            self.update(job_id, status='running', phase='preparing')
            argv = [sys.executable, '-m', 'shijie_ops.release', job['action'], '--config-dir',
                    str(self.directory), '--params', json.dumps(params)]
            process = subprocess.Popen(argv, env=self.env, stdin=subprocess.DEVNULL,
                                       cwd=self.controller.parent,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            self.process = process
            started, buffer, discard = time.monotonic(), b'', False
            deadline = self.timeout
            with selectors.DefaultSelector() as poll:
                poll.register(process.stdout, selectors.EVENT_READ)
                while poll.get_map():
                    if self.stopping.is_set() or time.monotonic() - started > deadline:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=3)
                        self.append(job_id, '执行中断；先检查部署状态和遗留维护容器，再显式恢复。\n', redact)
                        status = 'interrupted'
                        break
                    for key, _ in poll.select(.2):
                        chunk = os.read(key.fileobj.fileno(), 8192)
                        if not chunk:
                            poll.unregister(key.fileobj)
                            continue
                        buffer += chunk
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            if not discard and len(line) <= 16384:
                                self.append(job_id, line.decode('utf-8', 'replace') + '\n', redact)
                            else:
                                self.append(job_id, '[超长日志行已省略]\n', redact)
                            discard = False
                        if len(buffer) > 16384:
                            buffer, discard = b'', True
                if buffer and not discard:
                    self.append(job_id, buffer.decode('utf-8', 'replace'), redact)
            code = process.wait(timeout=5)
            process.stdout.close()
            if status != 'interrupted':
                if job['action'] in DEPLOYMENTS:
                    snapshot = self.snapshot()
                    expected = params.get('commit', params.get('pending_commit'))
                    ready = not snapshot['pending'] and snapshot['active'] and snapshot['active']['commit'] == expected
                else:
                    ready = True
                status = 'succeeded' if code == 0 and ready else 'failed'
                if code == 0 and not ready:
                    self.append(job_id, '命令退出但完成记录不匹配，未标记成功。\n', redact)
        except Exception as error:
            self.append(job_id, f'执行器错误：{type(error).__name__}。请查询诊断并保留现场。\n', redact)
        finally:
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
                status = 'interrupted'
            if process and process.stdout:
                process.stdout.close()
            self.process = None
            self.update(job_id, status=status, exit_code=code)

def request(socket_path, actor, action, params):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(30)
        client.connect(str(socket_path))
        client.sendall(json.dumps({'actor': actor, 'action': action, 'params': params}).encode() + b'\n')
        with client.makefile('rb') as stream:
            response = json.loads(stream.readline(1024 * 1024))
    if 'error' in response:
        raise ValueError(response['error'])
    return response['result']

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        try:
            raw = self.rfile.readline(65537)
            if len(raw) > 65536:
                raise ValueError('请求过大。')
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {'actor', 'action', 'params'}:
                raise ValueError('请求格式无效。')
            result = {'result': self.server.operations.dispatch(**data)}
        except ValueError as error:
            result = {'error': str(error)}
        except Exception:
            result = {'error': '执行器无法完成请求，请检查本机服务状态。'}
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode() + b'\n')

class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=Path('/etc/shijie'))
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/shijie-ops'))
    parser.add_argument('--socket', type=Path, default=Path('/run/shijie-ops/control.sock'))
    args = parser.parse_args()
    os.umask(0o077)
    operations = Operations(args.config_dir, args.state_dir)
    args.socket.parent.mkdir(parents=True, exist_ok=True)
    args.socket.unlink(missing_ok=True)
    try:
        with Server(str(args.socket), Handler) as server:
            server.operations = operations
            os.chmod(args.socket, 0o660)
            def stop(*_):
                operations.stopping.set()
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            server.serve_forever()
    finally:
        operations.close()
        args.socket.unlink(missing_ok=True)

if __name__ == "__main__": main()
