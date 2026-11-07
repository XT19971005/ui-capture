"""Build the explicitly requested colleague launcher; no Codex credentials are packaged."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '同事启动器' / 'AI拆图助手.exe'


def validate(config):
    if set(config) != {'serverUrl', 'accessCode', 'serviceId'}:
        raise ValueError('启动器配置字段无效')
    address = urlsplit(config['serverUrl'])
    ip = ipaddress.IPv4Address(address.hostname or '')
    private = any(ip in ipaddress.ip_network(network) for network in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    if (address.scheme != 'http' or not private or address.username or address.password or
        address.path not in ('', '/') or address.query or address.fragment or
        not address.port or not 1024 <= address.port <= 65535):
        raise ValueError('启动器只能连接指定的办公内网服务地址')
    if not isinstance(config['accessCode'], str) or not 8 <= len(config['accessCode']) <= 80:
        raise ValueError('局域网访问码无效')
    if not isinstance(config['serviceId'], str) or len(config['serviceId']) < 16:
        raise ValueError('共享服务标识无效')


def build(config, destination=OUTPUT):
    validate(config)
    if os.name != 'nt':
        raise ValueError('请在共享服务的 Windows 电脑上制作启动器')
    sources = sorted((ROOT / 'tools/lan_launcher').glob('*.cs'))
    if not sources:
        raise ValueError('缺少启动器维护源码')
    compiler = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():
        raise ValueError('找不到 Windows .NET Framework 编译器')
    destination = Path(destination).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(prefix='shijie-launcher-', dir=temp_root) as temporary:
        folder = Path(temporary).resolve()
        if folder.parent != temp_root:
            raise ValueError('临时构建目录无效')
        from desktop_worker import private_directory
        private_directory(folder)
        resource = folder / 'launcher.json'
        resource.write_text(json.dumps(config, ensure_ascii=False), encoding='utf8')
        binary = folder / 'launcher.exe'
        command = [str(compiler), '/nologo', '/target:winexe', '/optimize+', '/langversion:5',
                   '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
                   '/reference:System.Web.Extensions.dll', '/reference:System.Net.Http.dll',
                   '/resource:' + str(resource) + ',launcher.json', '/out:' + str(binary)]
        icon = ROOT / 'legacy/拾界插件/插件程序/edge/favicon.ico'
        if icon.exists():
            command.append('/win32icon:' + str(icon))
        result = subprocess.run(command + [str(p) for p in sources], capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            # Compiler diagnostics contain source locations, never the embedded resource contents.
            print(result.stdout.decode('mbcs', errors='replace'))
            print(result.stderr.decode('mbcs', errors='replace'))
            raise ValueError('启动器编译未通过，原文件保留')
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = destination.with_suffix('.pending')
        try:
            shutil.copyfile(binary, staged)
            os.replace(staged, destination)
        finally:
            staged.unlink(missing_ok=True)
    return destination


def main():
    from lan_server import STATE, protect
    site = json.loads((STATE / 'site.json').read_text('utf8'))
    access = protect((STATE / 'access.dat').read_bytes(), decrypt=True).decode()
    config = {'serverUrl': 'http://{}:{}'.format(site['host'], site['port']), 'accessCode': access,
              'serviceId': hashlib.sha256(site['secret_key'].encode()).hexdigest()[:32]}
    output = build(config)
    print('同事启动器已生成：' + str(output))
    print('已内置本次局域网地址和访问码；不含 Codex 凭据。')
    print('文件大小：{} KB'.format(round(output.stat().st_size / 1024)))


if __name__ == '__main__':
    main()
