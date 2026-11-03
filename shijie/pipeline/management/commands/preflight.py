import importlib
import shutil
import subprocess
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from shijie.pipeline.storage import write_json


class Command(BaseCommand):
    help = '检查运行时、数据盘及站点配置，不使用真实 AI 账号'

    def handle(self, *args, **options):
        from urllib.parse import urlsplit
        public = urlsplit(settings.PUBLIC_URL)
        if public.hostname not in ('localhost', '127.0.0.1'):
            oidc = settings.OIDC
            needed = ('discovery_url', 'client_id', 'client_secret') if oidc.get('mode', 'direct') == 'direct' else ('login_url', 'token_url', 'client_id')
            if not all(oidc.get(k) and 'example.com' not in str(oidc[k]) and 'REGISTER_' not in str(oidc[k]) for k in needed):
                raise CommandError('请完成独立的公司 OIDC/Broker 配置')
            if not oidc.get('bootstrap_admin_emails'):
                raise CommandError('请配置首次管理员 bootstrap_admin_emails')
        for name in ('PIL', 'cv2', 'numpy', 'scipy', 'psd_tools', 'vtracer'):
            importlib.import_module(name)
        for name in ('node', 'codex'):
            if not shutil.which(name):
                raise CommandError('缺少运行时：' + name)
        subprocess.run(['node', '-e', "require('@napi-rs/canvas');require('ag-psd')"], cwd=settings.BASE_DIR, check=True)
        probe = settings.DATA_ROOT / '.write-probe.json'
        write_json(probe, {'ok': True})
        probe.unlink()
        if shutil.disk_usage(settings.DATA_ROOT).free < settings.MIN_FREE:
            raise CommandError('数据盘剩余空间不足')
        self.stdout.write('运行时与私有盘通过；公司登录和个人 AI 需各自完成真实账号验收。')
