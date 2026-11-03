"""One user's Codex session; no service settings or database access in this process."""
import fcntl
import os
import sys
import time
import shutil
from pathlib import Path
from codex_client import CLIENT
from shijie.pipeline.storage import write_json

os.umask(0o077)
root = Path(os.environ['SHIJIE_TASK_ROOT'])
CLIENT.selected_model = sys.argv[2] or None
action = sys.argv[1]
pending_file = Path(os.environ['CODEX_HOME']) / 'device-login.json'
try:
    with (Path(os.environ['CODEX_HOME']) / 'account.lock').open('a') as lock:
        if action != 'status':
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('已有账号登录或处理进行中，请稍后重试')
        if action == 'login':
            value = CLIENT.call('account/login/start', {'type': 'chatgptDeviceCode'}, timeout=25)
            from urllib.parse import urlsplit
            url = value.get('verificationUrl', '')
            if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'auth.openai.com' or not value.get('userCode'):
                raise ValueError('登录服务未提供有效设备码')
            state = {'url': url, 'userCode': value['userCode'], 'expiresAt': time.time() + 900}
            write_json(pending_file, {**state, 'requestId': root.name})
            write_json(root / 'response.json', {'ok': True, **state})
            try:
                for _ in range(3600):
                    if CLIENT.login_done.wait(.25):
                        break
                    if (root / 'cancel').exists():
                        CLIENT.call('account/login/cancel', {'loginId': value['loginId']})
                        break
                else:
                    CLIENT.call('account/login/cancel', {'loginId': value['loginId']})
            finally:
                pending_file.unlink(missing_ok=True)
        elif action == 'status':
            state = CLIENT.account()
            models = CLIENT.models() if state['ready'] else []
            capabilities = CLIENT.call('modelProvider/capabilities/read', {}) if state['ready'] else {}
            write_json(root / 'response.json', {'ok': True, **state, 'models': models,
                       'model': CLIENT.model() if models else None, 'imageGeneration': capabilities.get('imageGeneration', False)})
        elif action == 'logout':
            CLIENT.call('account/logout', {})
            write_json(root / 'response.json', {'ok': True})
        else:
            raise ValueError('账号操作无效')
except Exception:
    if not (root / 'response.json').exists():
        write_json(root / 'response.json', {'ok': False, 'ready': False, 'error': 'Codex 未连接；请检查设备码登录权限、服务网络或已有登录操作'})
finally:
    CLIENT.close()
    if action == 'login' and (root / 'response.json').exists():
        # The parent has consumed the one-time code long before the login window closes.
        time.sleep(1)
        shutil.rmtree(root)
