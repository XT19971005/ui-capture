"""Local administrator setup. Published application releases never replace this runtime."""
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

CONTROL = Path('/opt/shijie-control')
AUTH = Path('/etc/shijie-mcp')
UNITS = Path('/etc/systemd/system')
MARKER = '# Shijie managed operations\n'


def atomic_json(path, value, mode=0o600):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        try:
            os.chmod(temporary, mode)
            if os.geteuid() == 0:
                os.chown(temporary, 0, path.parent.stat().st_gid)
            json.dump(value, out, indent=2)
            out.flush()
            os.fsync(out.fileno())
            os.replace(temporary, path)
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)


def issue_token(directory, actor, role='deploy', revoke=False):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@+-]{0,95}', actor) or role not in ('read', 'deploy'):
        raise ValueError('成员标识或权限无效。')
    directory = Path(directory)
    directory.mkdir(mode=0o750, parents=True, exist_ok=True)
    with (directory / 'credentials.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / 'operators.json'
        identities = json.loads(path.read_text()) if path.exists() else {}
        token_directory = directory / 'tokens'
        token_directory.mkdir(mode=0o700, exist_ok=True)
        destination = token_directory / actor
        if revoke:
            identities.pop(actor, None)
            atomic_json(path, identities, 0o640)
            destination.unlink(missing_ok=True)
            return None
        token = secrets.token_urlsafe(48)
        # Only hashes are readable by the network service. Plaintext is for local handoff.
        with tempfile.NamedTemporaryFile(mode='w', dir=token_directory, delete=False) as out:
            temporary = Path(out.name)
            os.chmod(temporary, 0o600)
            out.write(token + '\n')
            out.flush()
            os.fsync(out.fileno())
        temporary.replace(destination)
        identities[actor] = {'sha256': hashlib.sha256(token.encode()).hexdigest(), 'role': role}
        atomic_json(path, identities, 0o640)
        return destination


def service_units():
    return {
        'shijie-ops.service': MARKER + '''[Unit]
Description=Shijie private deployment executor
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=shijie-mcp
WorkingDirectory=/opt/shijie-control/current
ExecStart=/usr/bin/python3 -m shijie_ops.runtime
Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RuntimeDirectory=shijie-ops
RuntimeDirectoryMode=0750
StateDirectory=shijie-ops
StateDirectoryMode=0700
UMask=0077
Restart=on-failure
RestartSec=3
KillMode=control-group
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
''',
        'shijie-mcp.service': MARKER + '''[Unit]
Description=Shijie authenticated deployment MCP
After=shijie-ops.service network-online.target
Wants=shijie-ops.service network-online.target

[Service]
Type=simple
User=shijie-mcp
Group=shijie-mcp
WorkingDirectory=/opt/shijie-control/current
ExecStart=/opt/shijie-control/current/.venv/bin/python -m shijie_ops.mcp
Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
UMask=0077
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
''',
    }


def command(*args):
    subprocess.run(args, check=True, stdin=subprocess.DEVNULL)


def install(source, directory, deployed_commit=None, deployed_image=None):
    if directory != Path('/etc/shijie'):
        raise ValueError('正式 MCP 使用 /etc/shijie；请显式传入 --config-dir /etc/shijie。')
    if os.geteuid() != 0 or not Path('/run/systemd/system').is_dir() or sys.version_info[:2] != (3, 12):
        raise ValueError('MCP 安装需要 Python 3.12、Linux/systemd 和 sudo。')
    for folder in (CONTROL, AUTH):
        if folder.is_symlink() or (folder.exists() and (folder.stat().st_uid != 0 or folder.stat().st_mode & 0o022)):
            raise ValueError('控制服务目录必须由 root 管理且不可被其他账号写入。')
    for name in service_units():
        path = UNITS / name
        if path.exists() and (path.is_symlink() or not path.read_text().startswith(MARKER)):
            raise ValueError(f'{name} 已存在且不属于本项目，未覆盖。')
    current = CONTROL / 'current'
    if current.exists() and (not current.is_symlink() or not current.resolve().is_relative_to(CONTROL / 'releases')):
        raise ValueError('控制程序目录已有其他内容，未覆盖。')
    CONTROL.mkdir(mode=0o755, exist_ok=True)
    CONTROL.chmod(0o755)
    with (CONTROL / 'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        releases = CONTROL / 'releases'
        releases.mkdir(mode=0o755, exist_ok=True)
        releases.chmod(0o755)
        destination = Path(tempfile.mkdtemp(prefix='control-', dir=releases))
        for relative in ('shijiectl', 'config/__init__.py', 'config/transport.py',
                         'deploy/compose.yml', 'deploy/config.example.toml', 'deploy/mcp-requirements.lock'):
            src, dst = source / relative, destination / relative
            if not src.resolve().is_relative_to(source.resolve()):
                raise ValueError('控制程序源码含外部符号链接。')
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        shutil.copytree(source / 'shijie_ops', destination / 'shijie_ops', ignore=shutil.ignore_patterns('__pycache__'))
        command('/usr/bin/python3', '-m', 'venv', str(destination / '.venv'))
        command(str(destination / '.venv/bin/python'), '-m', 'pip', '--isolated', 'install', '--disable-pip-version-check',
                '--index-url', 'https://mirrors.aliyun.com/pypi/simple/', '--require-hashes',
                '-r', str(destination / 'deploy/mcp-requirements.lock'))
        for path in [destination, *destination.rglob('*')]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | (0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444))
        try:
            group = grp.getgrnam('shijie-mcp')
        except KeyError:
            command('groupadd', '--system', 'shijie-mcp')
            group = grp.getgrnam('shijie-mcp')
        try:
            account = pwd.getpwnam('shijie-mcp')
        except KeyError:
            command('useradd', '--system', '--gid', 'shijie-mcp', '--home-dir', '/nonexistent',
                    '--no-create-home', '--shell', '/usr/sbin/nologin', 'shijie-mcp')
            account = pwd.getpwnam('shijie-mcp')
        try:
            docker_group = grp.getgrnam('docker').gr_gid
        except KeyError:
            docker_group = None
        if account.pw_uid == 0 or account.pw_gid != group.gr_gid or docker_group in os.getgrouplist('shijie-mcp', account.pw_gid):
            raise ValueError('shijie-mcp 必须是独立低权限账号，不能属于 docker 组。')
        AUTH.mkdir(mode=0o750, exist_ok=True)
        os.chown(AUTH, 0, group.gr_gid)
        AUTH.chmod(0o750)
        if not (AUTH / 'operators.json').exists():
            atomic_json(AUTH / 'operators.json', {}, 0o640)
        if not (AUTH / 'server.json').exists():
            atomic_json(AUTH / 'server.json', {'host': '127.0.0.1', 'port': 8095,
                                              'allowed_hosts': ['127.0.0.1:*', 'localhost:*']}, 0o640)
        from .release import maintenance_lock
        with maintenance_lock(directory):
            adopt(source, directory, deployed_commit, deployed_image)
        old_target = current.resolve() if current.exists() else None
        old_units = {name: (UNITS / name).read_text() for name in service_units() if (UNITS / name).exists()}
        if old_target:
            # Close network admission before checking the durable queue. Never kill an update to upgrade MCP.
            command('systemctl', 'stop', 'shijie-mcp')
            try:
                from .runtime import request
                try:
                    snapshot = request('/run/shijie-ops/control.sock', 'local-admin', 'get_project_status', {})
                except OSError:
                    active = subprocess.run(['systemctl', 'is-active', '--quiet', 'shijie-ops']).returncode == 0
                    if active:
                        raise ValueError('执行器仍运行但无法查询状态，请先在本机检查。') from None
                    snapshot = {'latest_job': None}
                if snapshot['latest_job'] and snapshot['latest_job']['status'] in ('queued', 'running'):
                    raise ValueError('发布任务仍在执行，请完成后再升级控制服务。')
            except Exception:
                command('systemctl', 'start', 'shijie-mcp')
                raise
            command('systemctl', 'stop', 'shijie-ops')
        try:
            link = CONTROL / 'next'
            link.unlink(missing_ok=True)
            link.symlink_to(destination)
            link.replace(current)
            for name, content in service_units().items():
                (UNITS / name).write_text(content)
                (UNITS / name).chmod(0o644)
            command('systemctl', 'daemon-reload')
            command('systemctl', 'enable', '--now', 'shijie-ops', 'shijie-mcp')
            for service in ('shijie-ops', 'shijie-mcp'):
                command('systemctl', 'is-active', '--quiet', service)
        except Exception:
            if old_target:
                current.unlink()
                current.symlink_to(old_target)
                for name, content in old_units.items():
                    (UNITS / name).write_text(content)
                command('systemctl', 'daemon-reload')
                command('systemctl', 'restart', 'shijie-ops', 'shijie-mcp')
            raise
        print('MCP 已随系统启动：127.0.0.1:8095/mcp；通过 HTTPS 代理接入。')
        print('使用当前仓库的 sudo ./shijiectl mcp-token <成员标识> 生成个人凭据；默认没有可用凭据。')


def adopt(source, directory, commit, image):
    """Explicit one-time adoption; never guess the running commit from checkout HEAD."""
    if (directory / 'deployment.json').exists():
        if not (directory / 'operations.json').exists(): raise ValueError('发布记录缺少运维配置，请在宿主核对。')
        return
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('首次安装需要 --deployed-commit，必须为线上实际运行的完整 SHA。')
    if image not in ('shijie:' + commit, 'shijie:' + commit[:7]):
        raise ValueError('首次安装需要对应 --deployed-image shijie:<SHA> 标签。')
    source = source.resolve()
    owner = pwd.getpwuid(source.stat().st_uid)
    prefix = ['runuser', '-u', owner.pw_name, '--'] if owner.pw_uid else []
    def git(*args):
        result = subprocess.run([*prefix, 'git', '-C', str(source), *args], capture_output=True, check=True)
        return result.stdout
    remote = git('remote', 'get-url', 'origin').decode().strip()
    if remote != 'https://tygit.tuyoo.com/qp_agents/shijie.git':
        raise ValueError('正式控制器只接入已指定的拾界 HTTPS 仓库。')
    git('cat-file', '-e', commit + '^{commit}')
    records = json.loads(subprocess.check_output(['docker', 'inspect', 'shijie-web-1', 'shijie-worker-1']))
    expected = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]['Id']
    if any(row['Image'] != expected for row in records):
        raise ValueError('已部署镜像标签与当前 Web/Worker 不一致，未登记。')
    release = directory / 'releases' / (commit + '-adopted')
    release.parent.mkdir(exist_ok=True)
    from .release import extract_release
    extract_release(git('archive', '--format=zip', commit), release)
    atomic_json(directory / 'operations.json', {'repository': str(source), 'remote_url': remote,
                                              'backup_dir': '/home/shijie/backups'})
    atomic_json(directory / 'deployment.json', {'commit': commit, 'release': str(release),
                                              'image': image, 'phase': 'ready'})
