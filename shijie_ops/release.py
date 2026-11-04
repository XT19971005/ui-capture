"""Fixed-project host control. Every write uses the same maintenance lock as shijiectl."""
import argparse
import base64
from contextlib import contextmanager
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        try:
            os.chmod(temporary, 0o600)
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.flush(); os.fsync(out.fileno())
            os.replace(temporary, path)
            fd = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def maintenance_lock(directory):
    with (Path(directory) / 'maintenance.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('已有拾界维护操作执行中，请稍后重试。') from None
        yield


def backup(run, directory, data, destination, *, keep_stopped=False):
    directory, data, destination = map(lambda p: Path(p).resolve(), (directory, data, destination))
    if destination.is_relative_to(data):
        raise ValueError('备份目录不能位于数据目录内。')
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    # Disk estimates are conservative; an I/O failure deliberately leaves writers stopped.
    size = sum(p.stat().st_size for p in data.rglob('*') if p.is_file())
    db_size = int(run('exec', '-T', 'db', 'psql', '-X', '-U', 'shijie', '-d', 'shijie', '-Atc',
                      'SELECT pg_database_size(current_database())', stdout=subprocess.PIPE, text=True).stdout.strip())
    if shutil.disk_usage(destination).free < int((size + db_size) * 1.2) + 1024**3:
        raise ValueError('备份空间不足；尚未停止应用。')
    running = run('ps', '--status', 'running', '--services', 'web', 'worker', stdout=subprocess.PIPE, text=True).stdout.split()
    running = [name for name in running if name in ('web', 'worker')]
    run('stop', 'web', 'worker')
    with (destination / 'database.sql').open('xb') as stream:
        run('exec', '-T', 'db', 'pg_dump', '-U', 'shijie', '--clean', '--if-exists', 'shijie', stdout=stream)
        stream.flush(); os.fsync(stream.fileno())
    with (destination / 'data.tar.gz').open('xb') as stream:
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            archive.add(data, arcname='data')
            archive.add(directory / 'config.toml', arcname='config.toml')
            archive.add(directory / 'postgres-password', arcname='postgres-password')
        stream.flush(); os.fsync(stream.fileno())
    manifest = {}
    for name in ('database.sql', 'data.tar.gz'):
        with (destination / name).open('rb') as stream:
            manifest[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    atomic_json(destination / 'COMPLETE', manifest)
    if not keep_stopped and running:
        run('up', '-d', '--wait', *running)
    print('备份完成：' + str(destination), flush=True)


def check_backup(destination):
    source = Path(destination)
    manifest = json.loads((source / 'COMPLETE').read_text())
    if set(manifest) != {'database.sql', 'data.tar.gz'}:
        raise ValueError('备份完成记录无效。')
    for name, expected in manifest.items():
        with (source / name).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('备份校验失败；保留现状，不继续迁移。')


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def extract_release(content, destination):
    destination.mkdir(mode=0o700, exist_ok=False)
    with tempfile.TemporaryFile() as stream:
        stream.write(content); stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            for info in archive.infolist():
                target = destination / info.filename
                if not target.resolve().is_relative_to(destination) or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError('发布源码不允许越界路径或符号链接。')
                if info.is_dir(): target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info))
                    target.chmod(0o755 if info.external_attr >> 16 & 0o111 else 0o644)


class Controller:
    def __init__(self, directory, *, env=None):
        self.directory = Path(directory).resolve()
        self.config = tomllib.loads((self.directory / 'config.toml').read_text())
        self.options = json.loads((self.directory / 'operations.json').read_text())
        self.repository = Path(self.options['repository']).resolve()
        self.data = Path(self.config['deployment']['data_dir']).resolve()
        self.env = dict(os.environ if env is None else env)
        for key in list(self.env):
            if key.startswith(('GIT_TRACE', 'GIT_CONFIG_', 'SHIJIE_')) or key in ('GIT_CURL_VERBOSE', 'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'DOCKER_HOST', 'DOCKER_CONTEXT'):
                self.env.pop(key)
        self.env.update(SHIJIE_CONFIG_FILE=str(self.directory / 'config.toml'),
                        SHIJIE_DB_PASSWORD_FILE=str(self.directory / 'postgres-password'), SHIJIE_DATA_DIR=str(self.data),
                        SHIJIE_IMAGE_REGISTRY=self.config['deployment'].get('image_registry', 'docker.io/library/'),
                        SHIJIE_PIP_INDEX_URL=self.config['deployment'].get('pip_index_url', 'https://pypi.org/simple'),
                        GIT_TERMINAL_PROMPT='0')

    def record(self, name):
        path = self.directory / (name + '.json')
        return json.loads(path.read_text()) if path.exists() else None

    def run(self, record, *args, **kwargs):
        return subprocess.run(['docker', 'compose', '--env-file', '/dev/null', '-p', 'shijie', '-f',
                               str(Path(record['release']) / 'deploy/compose.yml'), *args],
                              env={**self.env, 'SHIJIE_IMAGE': record['image']}, check=True, **kwargs)

    def git(self, *args):
        owner = pwd.getpwuid(self.repository.stat().st_uid)
        prefix = ['runuser', '-u', owner.pw_name, '--'] if os.geteuid() == 0 and owner.pw_uid else []
        env = dict(self.env)
        credentials = self.directory / 'git-read.json'
        if credentials.exists():
            if credentials.is_symlink() or credentials.stat().st_mode & 0o077:
                raise ValueError('Git 读取凭据必须为私有普通文件。')
            identity = json.loads(credentials.read_text())
            if self.options['remote_url'] != 'https://tygit.tuyoo.com/qp_agents/shijie.git':
                raise ValueError('读取凭据只允许发送到已登记的拾界 HTTPS 仓库。')
            username, token = identity['username'], identity['token']
            if not all(isinstance(v, str) and v and not any(c in v for c in '\r\n\x00') for v in (username, token)) or ':' in username:
                raise ValueError('Git 读取凭据格式无效。')
            header = 'Authorization: Basic ' + base64.b64encode((username + ':' + token).encode()).decode()
            env.update(GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='credential.helper', GIT_CONFIG_VALUE_0='',
                       GIT_CONFIG_KEY_1='http.https://tygit.tuyoo.com/qp_agents/shijie.git.extraHeader', GIT_CONFIG_VALUE_1=header)
        result = subprocess.run([*prefix, 'git', '-c', 'http.sslVerify=true', '-c', 'http.followRedirects=false',
                                 '-C', str(self.repository), *args], env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
        if result.returncode:
            raise ValueError('Git ' + args[0] + ' 失败；请检查已登记仓库的权限、认证和提交关系。原始输出已隐藏。')
        return result.stdout

    def source(self, commit, baseline):
        if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise ValueError('提交必须是完整的 40 位小写 Git SHA。')
        # Local config reads must not cause credentials to be sent to an unregistered origin.
        if self.git('remote', 'get-url', 'origin').decode().strip() != self.options['remote_url']:
            raise ValueError('origin 与管理员登记的仓库不一致。')
        if self.git('rev-parse', '--show-toplevel').decode().strip() != str(self.repository):
            raise ValueError('登记目录不是仓库根目录。')
        if self.git('symbolic-ref', '--short', 'HEAD').strip() != b'main' or self.git('status', '--porcelain'):
            raise ValueError('仓库须为干净的 main；不会覆盖未提交文件。')
        self.git('fetch', 'origin', 'main')
        tip = self.git('rev-parse', 'FETCH_HEAD').decode().strip()
        self.git('cat-file', '-e', commit + '^{commit}')
        self.git('merge-base', '--is-ancestor', commit, tip)
        self.git('merge-base', '--is-ancestor', baseline, commit)
        releases = self.directory / 'releases'; releases.mkdir(exist_ok=True)
        destination = releases / (commit + '-' + timestamp())
        # ponytail: immutable git archive; no checkout/reset and no dependency on a later main tip.
        # Release retention is manual until a separately specified retention policy exists.
        extract_release(self.git('archive', '--format=zip', commit), destination)
        return {'commit': commit, 'release': str(destination), 'image': 'shijie:' + commit, 'phase': 'build'}

    def stage(self, pending, phase):
        pending['phase'] = phase
        atomic_json(self.directory / 'pending.json', pending)
        print('SHIJIE_STAGE:' + phase, flush=True)

    def ensure_no_maintenance_container(self, active):
        result = self.run(active, 'ps', '--all', '--format', 'json', stdout=subprocess.PIPE, text=True)
        text = result.stdout.strip()
        rows = json.loads(text) if text.startswith('[') else [json.loads(line) for line in text.splitlines()]
        if any(row.get('State') == 'running' and (row.get('OneOff') is True or
               'com.docker.compose.oneoff=True' in str(row.get('Labels', ''))) for row in rows):
            raise ValueError('仍有维护容器运行；先在宿主检查，不重复迁移。')

    def perform(self, action, params):
        with maintenance_lock(self.directory):
            active, pending = self.record('deployment'), self.record('pending')
            if not active:
                raise ValueError('缺少已部署基线；请先由宿主管理员安装并登记。')
            self.ensure_no_maintenance_container(active)
            waiting = self.run(active, 'exec', '-T', 'db', 'psql', '-X', '-U', 'shijie', '-d', 'shijie', '-Atc',
                               "SELECT count(*) FROM pipeline_job WHERE status IN ('queued','running')",
                               stdout=subprocess.PIPE, text=True).stdout.strip()
            if waiting != '0':
                raise ValueError('仍有拆图任务排队或运行；请先等待完成或在拾界中取消，未停止应用。')
            if action in ('control_service', 'backup'):
                if pending: raise ValueError('有未完成发布，请先诊断并恢复。')
                if action == 'control_service':
                    operation, service = params['operation'], params['service']
                    if operation not in ('start', 'stop', 'restart') or service not in ('web', 'worker', 'all'):
                        raise ValueError('仅允许启动、停止、重启拾界 web/worker。')
                    selected = ['web', 'worker'] if service == 'all' else [service]
                    self.run(active, operation, *selected)
                    if operation != 'stop': self.run(active, 'up', '-d', '--wait', *selected)
                else:
                    backup(lambda *a, **kw: self.run(active, *a, **kw), self.directory, self.data,
                           Path(self.options['backup_dir']) / ('shijie-' + timestamp()))
                return
            if action == 'deploy':
                if pending: raise ValueError('有未完成发布，请使用恢复或修复发布。')
                candidate = self.source(params['commit'], active['commit'])
                print('SHIJIE_STAGE:build', flush=True)
                self.run(candidate, 'build')
                candidate['backup'] = str(Path(self.options['backup_dir']) / ('shijie-' + timestamp()))
                pending = candidate; self.stage(pending, 'backup')
            elif action in ('resume_deployment', 'repair_deployment'):
                if not pending or params['pending_commit'] != pending['commit']:
                    raise ValueError('失败提交已变化或不存在，请重新查询状态。')
                if action == 'repair_deployment':
                    candidate = self.source(params['commit'], pending['commit'])
                    for old in Path(pending['release']).glob('**/migrations/*.py'):
                        new = Path(candidate['release']) / old.relative_to(pending['release'])
                        if not new.is_file() or old.read_bytes() != new.read_bytes():
                            raise ValueError('修复提交不得修改或删除已有迁移。')
                    self.run(candidate, 'build')
                    candidate.update(backup=pending['backup'], phase=pending['phase'])
                    pending = candidate
                    atomic_json(self.directory / 'pending.json', pending)
            else:
                raise ValueError('不支持的维护操作。')
            if pending['phase'] == 'backup' and not (Path(pending['backup']) / 'COMPLETE').exists():
                if Path(pending['backup']).exists():
                    pending['backup'] = str(Path(self.options['backup_dir']) / ('shijie-' + timestamp()))
                    self.stage(pending, 'backup')
                backup(lambda *a, **kw: self.run(active, *a, **kw), self.directory, self.data,
                       pending['backup'], keep_stopped=True)
            check_backup(pending['backup'])
            self.stage(pending, 'stop_writers'); self.run(active, 'stop', 'web', 'worker')
            self.run(pending, 'up', '-d', '--wait', 'db')
            self.stage(pending, 'migrate'); self.run(pending, 'run', '--rm', 'web', 'python', 'manage.py', 'migrate', '--noinput')
            self.stage(pending, 'preflight'); self.run(pending, 'run', '--rm', 'web', 'python', 'manage.py', 'preflight')
            self.stage(pending, 'health_check'); self.run(pending, 'up', '-d', '--wait', 'web', 'worker')
            pending['phase'] = 'ready'; atomic_json(self.directory / 'deployment.json', pending)
            (self.directory / 'pending.json').unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action'); parser.add_argument('--config-dir', type=Path, required=True)
    parser.add_argument('--params', required=True)
    args = parser.parse_args(); os.umask(0o077)
    try:
        controller = Controller(args.config_dir)
        params = json.loads(args.params)
        if args.action == 'status':
            controller.run(controller.record('deployment'), 'ps', '--all', '--format', 'json')
        elif args.action == 'logs':
            if params.get('service') not in ('web', 'worker', 'db'): raise ValueError('不支持的日志服务。')
            controller.run(controller.record('deployment'), 'logs', '--no-color', '--tail', '100', params['service'])
        else:
            controller.perform(args.action, params)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('操作未完成：' + str(error), flush=True)
        raise SystemExit(1) from None


if __name__ == '__main__': main()
