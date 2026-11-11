"""Direct TLS colleague entrance. No proxy, executable download, or remote owner login."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop_worker import atomic_json, private_directory, protect
from host_lock import exclusive

STATE = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AI拆图助手/局域网共享'
PORT = 19218
ENTRY = ROOT / '同事网页入口'


def password(folder):
    path = folder / 'password.dat'
    if not path.exists():
        path.write_bytes(protect(secrets.token_urlsafe(48).encode()))
    return protect(path.read_bytes(), decrypt=True)


def certificates(folder, host):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    folder = Path(folder)
    private_directory(folder)
    address = ipaddress.IPv4Address(host)
    if not any(address in ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValueError('HTTPS 入口仅允许办公内网地址')
    now = datetime.now(timezone.utc)
    secret = password(folder)
    ca_file, ca_key = folder/'root.crt', folder/'root-key.pem'
    cert_file, key_file = folder/'server.crt', folder/'server-key.pem'
    encryption = serialization.BestAvailableEncryption(secret)
    def store_key(path, key):
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption))
    if ca_file.exists() != ca_key.exists():
        raise ValueError('内网证书文件不完整；请恢复原证书，不会自动替换已分发的信任证书')
    if not ca_file.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'AI Image Splitter Office ' + secrets.token_hex(6))])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
              .not_valid_after(now+timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
              .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
              .sign(key,hashes.SHA256()))
        store_key(ca_key,key)
        ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    ca = x509.load_pem_x509_certificate(ca_file.read_bytes())
    key = serialization.load_pem_private_key(ca_key.read_bytes(),password=secret)
    if key.public_key().public_numbers()!=ca.public_key().public_numbers():
        raise ValueError('内网证书与密钥不匹配')
    if ca.not_valid_after_utc < now+timedelta(days=365):
        raise ValueError('内网根证书即将到期，请更新同事电脑的信任证书')
    if cert_file.exists() and key_file.exists():
        leaf=x509.load_pem_x509_certificate(cert_file.read_bytes())
        leaf.verify_directly_issued_by(ca)
        names=leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        server_key=serialization.load_pem_private_key(key_file.read_bytes(),password=secret)
        if (address in names.get_values_for_type(x509.IPAddress) and leaf.not_valid_after_utc>now+timedelta(days=30)
                and leaf.public_key().public_numbers()==server_key.public_key().public_numbers()):
            return cert_file,key_file,ca_file
    server_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    leaf=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,host)]))
          .issuer_name(ca.subject).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=180))
          .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.IPAddress(address)]),critical=False)
          .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
          .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),critical=True)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),critical=False)
          .sign(key,hashes.SHA256()))
    store_key(key_file,server_key)
    cert_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    return cert_file,key_file,ca_file


def write_entry(folder,url,code,ca_file):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    ca=x509.load_pem_x509_certificate(Path(ca_file).read_bytes())
    (folder/'办公内网信任证书.cer').write_bytes(ca.public_bytes(serialization.Encoding.DER))
    entry_url=url+'/login/?entry=1#access='+quote(code,safe='')
    browser_script=r'''@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title AI拆图助手
set "taskEntry=__URL__"
if /I "%~1"=="--compatible" goto choose
if /I "%~1"=="--check" goto choose
start "" "%taskEntry%"
exit /b %errorlevel%
:choose
set "taskBrowser="
for %%B in ("%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe") do if exist "%%~B" (
set "taskBrowser=%%~B"
goto launch
)
echo 未找到 Microsoft Edge 或 Google Chrome，请安装或更新其中一个浏览器。
if /I "%~1"=="--check" exit /b 1
pause
exit /b 1
:launch
if /I "%~1"=="--check" goto checked
set "taskEntry=__URL__"
start "" "%taskBrowser%" "%taskEntry%"
exit /b %errorlevel%
:checked
echo 已找到浏览器："%taskBrowser%"
exit /b 0
'''
    (folder/'打开AI拆图助手.cmd').write_text(browser_script.replace('__URL__',entry_url.replace('%','%%')),encoding='utf8',newline='\r\n')
    # Retire the generated default-browser shortcut; its browser choice differs
    # from the original launcher and can select an incompatible browser.
    old=folder/'打开AI拆图助手.url'
    if old.exists():
        old.unlink()
    # Use Windows' own certificate utility, not another unsigned executable or
    # an execution-policy bypass. New trust requires the recipient's consent.
    script = r'''@echo off
setlocal
chcp 65001 >nul
title AI拆图助手 - 首次使用
if not exist "%~dp0办公内网信任证书.cer" goto missing
if not exist "%~dp0打开AI拆图助手.cmd" goto missing
certutil -hashfile "%~dp0办公内网信任证书.cer" SHA256 2>nul | findstr /I /X /C:"__SHA256__" >nul
if errorlevel 1 goto invalid
certutil -user -store Root "__THUMBPRINT__" 2>nul | findstr /I /C:"__THUMBPRINT__" >nul
if not errorlevel 1 goto ready
if /I "%~1"=="--check" exit /b 2
echo 此操作将为当前 Windows 用户信任 AI拆图助手的办公内网证书。
echo 仅在当前用户的受信任根证书库安装，不需要管理员权限。
echo 证书 SHA256：__SHA256__
echo.
choice /C YN /N /M "确认安装并进入网页？按 Y 继续，按 N 取消："
if errorlevel 2 exit /b 0
certutil -user -addstore Root "%~dp0办公内网信任证书.cer"
if errorlevel 1 goto denied
certutil -user -store Root "__THUMBPRINT__" 2>nul | findstr /I /C:"__THUMBPRINT__" >nul
if errorlevel 1 goto denied
:ready
echo 证书校验和当前用户信任检查已通过。
if /I "%~1"=="--check" exit /b 0
if /I "%~1"=="--install-only" exit /b 0
call "%~dp0打开AI拆图助手.cmd"
if errorlevel 1 goto browser
exit /b 0
:missing
echo 文件不完整，请将整个“同事网页入口”文件夹保存到本机后重试。
goto failed
:invalid
echo 证书与此入口不匹配，已停止安装，请向管理员重新获取完整入口。
goto failed
:denied
echo Windows 未允许安装证书，请交公司 IT 处理。没有修改系统策略。
goto failed
:browser
echo 无法自动打开浏览器，请手动双击“打开AI拆图助手.cmd”。
:failed
if /I "%~1"=="--check" exit /b 1
pause
exit /b 1
'''
    script=script.replace('__SHA256__',ca.fingerprint(hashes.SHA256()).hex().upper()).replace('__THUMBPRINT__',ca.fingerprint(hashes.SHA1()).hex().upper())
    (folder/'首次使用.cmd').write_text(script,encoding='utf8',newline='\r\n')
    (folder/'首次使用说明.txt').write_text(
        'AI拆图助手 · 使用说明\n'
        '\n'
        '1. 首次打开：把整个文件夹放到自己电脑，双击“首次使用.cmd”，按提示按 Y 安装证书并打开网页。\n'
        '2. 以后打开：双击“打开AI拆图助手.cmd”。\n'
        '3. 无法连接：确认连接同一局域网，并让共享主机运行“启动局域网共享.ps1”。证书报错请联系管理员。\n'
        '\n'
        '工程和PSD保存在自己电脑。入口仅分享给同事。\n'
        ,encoding='utf-8-sig')


def prepare():
    if not (STATE/'site.json').exists():
        raise ValueError('请先启动局域网共享服务')
    config=json.loads((STATE/'site.json').read_text('utf8'))
    with exclusive(STATE/'https-prepare.lock'):
        cert,key,ca=certificates(STATE/'https',config['host'])
        code=protect((STATE/'access.dat').read_bytes(),decrypt=True).decode()
        write_entry(ENTRY,f"https://{config['host']}:{PORT}",code,ca)
    return config,cert,key,ca


def tls_adapter(certificate, private_key, *, private_key_password=None):
    """Keep lazy TLS handshakes and retry only the unsent output buffer."""
    from cheroot.ssl.pyopenssl import (
        SSLFileobjectStreamReader, SSLFileobjectStreamWriter, pyOpenSSLAdapter, ssl_conn_type,
    )

    class TLSReader(SSLFileobjectStreamReader):
        def __init__(self, sock, mode='r', bufsize=-1):
            super().__init__(sock, mode, bufsize)
            self.ssl_timeout = sock.gettimeout()
            # BufferedReader reads through SocketIO.recv_into, not mixin.recv.
            # Retry this raw read only: replaying BufferedReader.read would lose
            # bytes already consumed earlier in the same large request body.
            raw_readinto = self.raw.readinto
            self.raw.readinto = lambda buffer: self._safe_call(True, raw_readinto, buffer)

    class TLSWriter(SSLFileobjectStreamWriter):
        def _flush_unlocked(self):
            # SocketIO.write calls the connection's send directly, bypassing
            # SSLFileobjectMixin.send. A transient TLS WantRead/WantWrite must
            # retry this remaining buffer, not append the HTTP body again.
            return self._safe_call(False, super()._flush_unlocked)

    class TLSAdapter(pyOpenSSLAdapter):
        def makefile(self, sock, mode='r', bufsize=-1):
            if not isinstance(sock, ssl_conn_type):
                return super().makefile(sock, mode, bufsize)
            stream = (TLSReader if 'r' in mode else TLSWriter)(sock, mode, bufsize)
            stream.ssl_timeout = sock.gettimeout()
            return stream

    return TLSAdapter(certificate, private_key, private_key_password=private_key_password)


def run():
    config,cert,key,ca=prepare()
    with exclusive(STATE/'https.lock'):
        os.environ.update(DJANGO_SETTINGS_MODULE='config.lan_settings',SHIJIE_LAN_STATE=str(STATE),
                          SHIJIE_LAN_HTTPS='1',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
        import django
        django.setup()
        from django.core.wsgi import get_wsgi_application
        from cheroot.wsgi import Server
        from OpenSSL import SSL
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        loaded_certificate=x509.load_pem_x509_certificate(cert.read_bytes()).fingerprint(hashes.SHA256()).hex()
        server=Server((config['host'],PORT),get_wsgi_application(),numthreads=8,max=24,
                      request_queue_size=32,timeout=120,shutdown_timeout=10,accepted_queue_size=32)
        server.max_request_body_size=276*1024**2
        server.max_request_header_size=65536
        # BuiltinSSLAdapter handshakes synchronously in the single accept loop.
        # One browser preconnect (or certificate rejection) can stall everyone for
        # the entire socket timeout. The official OpenSSL adapter performs the
        # handshake on worker I/O instead, so idle peers cannot block acceptance.
        server.ssl_adapter=tls_adapter(str(cert),str(key),private_key_password=password(STATE/'https').decode())
        server.ssl_adapter.context=server.ssl_adapter.get_context()
        server.ssl_adapter.context.set_min_proto_version(SSL.TLS1_2_VERSION)
        server.prepare()
        stop=STATE/'https-stop';stop.unlink(missing_ok=True)
        exit_event=threading.Event()
        def monitor():
            while not exit_event.wait(2):
                if stop.exists():
                    server.stop();return
                atomic_json(STATE/'https-status.json',{'running':True,'pid':os.getpid(),'heartbeat':time.time(),
                    'url':f"https://{config['host']}:{PORT}", 'certificate':loaded_certificate})
        thread=threading.Thread(target=monitor,daemon=True);thread.start()
        try:
            server.serve()
        finally:
            exit_event.set();server.stop();thread.join(3)
            atomic_json(STATE/'https-status.json',{'running':False,'heartbeat':time.time()})


def main():
    parser=argparse.ArgumentParser(description='AI拆图助手 · 无EXE的HTTPS网页入口')
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--stop',action='store_true')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.stop:
        (STATE/'https-stop').touch();return
    if args.prepare:
        prepare();print('网页入口已生成：'+str(ENTRY));return
    if args.check:
        import urllib.request
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        site=json.loads((STATE/'site.json').read_text('utf8'))
        status=json.loads((STATE/'https-status.json').read_text('utf8'))
        expected=f"https://{site['host']}:{PORT}"
        certificate=x509.load_pem_x509_certificate((STATE/'https/server.crt').read_bytes()).fingerprint(hashes.SHA256()).hex()
        if (not status.get('running') or time.time()-status.get('heartbeat',0)>20
                or status.get('url')!=expected or status.get('certificate')!=certificate):
            raise ValueError('网页入口地址或证书已更新，请停止并重新启动局域网共享')
        context=ssl.create_default_context(cafile=str(STATE/'https/root.crt'))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
        with opener.open(expected+'/health/live',timeout=5) as response:
            if response.status!=200:raise ValueError('HTTPS入口未就绪')
        return
    run()


if __name__=='__main__':
    try:main()
    except Exception as error:
        if STATE.exists() and not any(flag in sys.argv for flag in ('--prepare','--check','--stop')):
            atomic_json(STATE/'https-status.json',{'running':False,'heartbeat':time.time(),'error':type(error).__name__})
        print('HTTPS入口未能启动：'+type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
