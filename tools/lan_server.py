"""Windows office-LAN web service and local Codex worker lifecycle."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop_worker import DesktopWorker, ProcessTree, atomic_json, configure, private_directory, protect
from host_lock import exclusive

STATE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AI拆图助手/局域网共享'
PORT = 19218


def adapter():
    command = "$r=Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1; Get-NetIPAddress -InterfaceIndex $r.InterfaceIndex -AddressFamily IPv4 | Where-Object {$_.AddressState -eq 'Preferred'} | Select-Object -First 1 IPAddress,PrefixLength | ConvertTo-Json -Compress"
    raw = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
        creationflags=subprocess.CREATE_NO_WINDOW)
    value = json.loads(raw.decode('ascii'))
    address = ipaddress.IPv4Address(value['IPAddress'])
    prefix = int(value['PrefixLength'])
    if not address.is_private or address.is_loopback or address.is_link_local or not 16 <= prefix <= 30:
        raise ValueError('未找到可用的公司局域网，请连接办公网络后再启动')
    return str(address), prefix


def prepare():
    if os.name != 'nt':
        raise ValueError('此启动入口仅供 Windows 本机使用')
    private_directory(STATE)
    with exclusive(STATE / 'server.lock'):
        host, prefix = adapter()
        site = STATE / 'site.json'
        if site.exists():
            value = json.loads(site.read_text('utf8'))
        else:
            access = '-'.join(secrets.token_hex(3).upper() for _ in range(3))
            value = {'secret_key': secrets.token_urlsafe(64), 'access_digest': hashlib.sha256(access.encode()).hexdigest()}
            (STATE / 'access.dat').write_bytes(protect(access.encode()))
        value.update(host=host, prefix_length=prefix, port=PORT)
        atomic_json(site, value)
        print('局域网配置已准备；原工程与现有单机程序保留。')


def environment():
    os.environ.update(DJANGO_SETTINGS_MODULE='config.lan_settings', SHIJIE_LAN_STATE=str(STATE),
                      PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')


def info(show_code=True):
    if not (STATE / 'site.json').exists():
        print('局域网共享尚未配置'); return
    value = json.loads((STATE / 'site.json').read_text('utf8'))
    status = json.loads((STATE / 'status.json').read_text('utf8')) if (STATE / 'status.json').exists() else {}
    online = status.get('running') and time.time() - status.get('heartbeat', 0) < 20
    print('局域网网页正在运行' if online else '局域网网页未启动或已停止')
    print(f"同事访问：https://{value['host']}:{value['port']}/")
    print(f"本机管理：http://127.0.0.1:{value['port']}/")
    if show_code:
        print('访问码：' + protect((STATE / 'access.dat').read_bytes(), decrypt=True).decode())
    print('同事首次导入“同事网页入口”内的证书，然后使用网页快捷方式。')
    print('新版 Chrome/Edge 可选择自己的工程文件夹并直接保存，无需同事端EXE。PSD直接下载。不要关闭共享电脑。')


def run_worker():
    folder = STATE / 'worker'
    value = json.loads(protect((folder / 'connection.dat').read_bytes(), decrypt=True))
    DesktopWorker(value, folder).run()


def run():
    if not (STATE / 'site.json').exists(): prepare()
    private_directory(STATE)
    with exclusive(STATE / 'server.lock'):
        environment()
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.db import connections
        from shijie.pipeline.models import DesktopService
        from waitress.server import create_server
        from django.core.wsgi import get_wsgi_application
        call_command('migrate', verbosity=0, interactive=False)
        with connections['default'].cursor() as cursor:
            cursor.execute('PRAGMA journal_mode=WAL')
        folder = STATE / 'worker'; private_directory(folder)
        existing = folder / 'connection.dat'
        connection = json.loads(protect(existing.read_bytes(), decrypt=True)) if existing.exists() else {
            'url': f'http://127.0.0.1:{PORT}', 'token': secrets.token_urlsafe(48)}
        if not existing.exists():
            staged = folder / 'connection.tmp'
            staged.write_bytes(protect(json.dumps(connection).encode()))
            os.replace(staged, existing)
        digest = hashlib.sha256(connection['token'].encode()).hexdigest()
        service, created = DesktopService.objects.get_or_create(pk=1, defaults={'token_digest': digest, 'enabled': True})
        if service.token_digest != digest:
            raise ValueError('局域网配对已被更改，请在本机恢复正确配对；不会覆盖待回传任务')
        (STATE / 'stop').unlink(missing_ok=True)
        # Plain HTTP is owner/worker-only. Colleagues use direct TLS on the LAN IP.
        server = create_server(get_wsgi_application(), listen=f"127.0.0.1:{PORT}",
            threads=8, connection_limit=100, max_request_body_size=276*1024**2, expose_tracebacks=False)
        thread = threading.Thread(target=server.run, daemon=True); thread.start()
        process = tree = None
        try:
            if not any((folder / 'jobs').glob('*/receipt.json')):
                configure(folder, url=connection['url'], token=connection['token'])
            worker = DesktopWorker(connection, folder)
            try: worker.probe()
            except (ValueError, OSError, subprocess.SubprocessError):
                if not any((folder / 'jobs').glob('*/receipt.json')): raise
                # A stale model login must not prevent delivery of already-finished results.
                worker.capabilities = {'ready': False, 'models': [], 'model': '', 'imageGeneration': False}
            worker.remote('heartbeat', worker.capabilities)
            env = os.environ.copy(); env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
            process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--worker'],
                cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            tree = ProcessTree(process)
            while not (STATE / 'stop').exists():
                if process.poll() is not None:
                    raise ValueError('本机接单程序已停止，请重新启动局域网共享')
                atomic_json(STATE / 'status.json', {'running': True, 'heartbeat': time.time(), 'pid': os.getpid()})
                time.sleep(2)
        finally:
            (folder / 'stop').touch()
            if process:
                try: process.wait(timeout=35)
                except subprocess.TimeoutExpired: pass
            if tree: tree.close()
            server.close()
            if hasattr(server, 'task_dispatcher'): server.task_dispatcher.shutdown()
            connections.close_all()
            atomic_json(STATE / 'status.json', {'running': False, 'heartbeat': time.time()})


def main():
    parser = argparse.ArgumentParser(description='AI拆图助手 · 局域网共享')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--prepare', action='store_true'); group.add_argument('--status', action='store_true')
    group.add_argument('--stop', action='store_true'); group.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.prepare: return prepare()
    if args.status: return info(show_code=False)
    if args.stop:
        STATE.mkdir(parents=True, exist_ok=True); (STATE / 'stop').touch()
        print('已请求停止，正在保留已有任务结果。'); return
    if args.worker: return run_worker()
    run()


if __name__ == '__main__':
    try: main()
    except Exception as error:
        # Only controlled local messages; never put credential values or provider responses in logs.
        if STATE.exists():
            atomic_json(STATE / 'status.json', {'running': False, 'heartbeat': time.time(), 'error': type(error).__name__})
        print('启动未完成：' + (str(error) if isinstance(error, (ValueError, BlockingIOError)) else type(error).__name__), file=sys.stderr)
        raise SystemExit(1)
