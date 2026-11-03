import os
import json
import signal
import subprocess
import sys
from django.conf import settings


def environment(root, codex_home):
    # Child tools receive no Django config, database password or developer credentials.
    env = {k: os.environ[k] for k in ('PATH', 'LANG', 'SSL_CERT_FILE', 'CODEX_CA_CERTIFICATE') if k in os.environ}
    env.update(PATH=str(settings.BASE_DIR / 'node_modules/.bin') + os.pathsep + env.get('PATH', ''),
               PYTHONPATH=str(settings.ENGINE_ROOT) + os.pathsep + str(settings.BASE_DIR),
               PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
               # Fonts are registered from fonts.json; avoid home-directory discovery for mapped Docker UIDs.
               DISABLE_SYSTEM_FONTS_LOAD='1',
               SHIJIE_TASK_ROOT=str(root), CODEX_HOME=str(codex_home),
               SHIJIE_PYTHON=sys.executable)
    return env


def start(script, root, codex_home, *arguments, input_data=None):
    payload = json.dumps(input_data).encode() if input_data is not None else None
    if payload is not None and len(payload) > 16 * 1024:
        raise ValueError('任务连接配置超过大小限制')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    codex_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    codex_home.chmod(0o700)
    process = subprocess.Popen([sys.executable, str(settings.BASE_DIR / 'tools' / script), *map(str, arguments)],
                            cwd=root, env=environment(root, codex_home), start_new_session=True,
                            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if input_data is not None:
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except (OSError, ValueError):
            stop(process)
            raise
    return process


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    except ProcessLookupError:
        process.wait()
