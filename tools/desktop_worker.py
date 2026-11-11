"""Outbound-only private desktop worker; never sends Codex credentials to the web service."""
import argparse
import ctypes
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4
import requests

BASE=Path(__file__).resolve().parents[1]
ENGINE=BASE/'legacy/拾界插件/开发源码/自动拆图'
sys.path.insert(0,str(ENGINE))
from local_project_store import atomic_replace, read_json_atomic
DEFAULT_STATE=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'AI拆图助手/共享服务'
MAX_BYTES=276*1024**2


def service_url(value):
    url=urlsplit(value.strip())
    if not url.hostname or url.username or url.password or url.query or url.fragment or '\\' in value or '%' in url.path or '..' in url.path.split('/'):
        raise ValueError('请填写完整的网站地址，不包含登录凭证、查询参数或文件路径')
    if url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('127.0.0.1','localhost')):
        raise ValueError('远程共享服务需要 HTTPS；本机测试可用 http://127.0.0.1')
    if not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)*/?',url.path):raise ValueError('网站子路径无效')
    return value.strip().rstrip('/')


def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as output:
            temp=Path(output.name);output.write(json.dumps(value,ensure_ascii=False,allow_nan=False).encode());output.flush();os.fsync(output.fileno())
        atomic_replace(temp,path)
    finally:
        if temp:temp.unlink(missing_ok=True)


def protect(raw, decrypt=False):
    """Pair token protection uses the current Windows user's credential boundary."""
    if os.name!='nt':raise ValueError('此启动入口供 Windows 本机服务使用')
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    function=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('无法读取或保护本机配对凭证')
    try:return ctypes.string_at(target.data,target.size)
    finally:ctypes.windll.kernel32.LocalFree(target.data)


def private_directory(path):
    path.mkdir(parents=True,exist_ok=True)
    if os.name!='nt':path.chmod(0o700);return
    from ctypes import wintypes
    sid=subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command','[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],creationflags=subprocess.CREATE_NO_WINDOW).decode('ascii').strip()
    if not re.fullmatch(r'S-1-[0-9-]+',sid):raise ValueError('无法确认当前 Windows 用户')
    advapi=ctypes.WinDLL('advapi32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.c_void_p]
    advapi.SetFileSecurityW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_void_p]
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    descriptor=ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW('D:P(A;OICI;FA;;;'+sid+')(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)',1,ctypes.byref(descriptor),None):raise ValueError('无法保护本机服务目录')
    try:
        if not advapi.SetFileSecurityW(str(path),0x80000004,descriptor):raise ValueError('无法保护本机服务目录')
    finally:kernel.LocalFree(descriptor)


class ProcessTree:
    """Windows closes this job handle on parent exit, terminating its descendants."""
    def __init__(self,process):
        self.process=process;self.handle=None
        if os.name!='nt':return
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_=[('processTime',ctypes.c_int64),('jobTime',ctypes.c_int64),('flags',wintypes.DWORD),('minimum',ctypes.c_size_t),('maximum',ctypes.c_size_t),('active',wintypes.DWORD),('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class Counters(ctypes.Structure):_fields_=[(name,ctypes.c_uint64) for name in ('readOps','writeOps','otherOps','readBytes','writeBytes','otherBytes')]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',Counters),('processMemory',ctypes.c_size_t),('jobMemory',ctypes.c_size_t),('peakProcess',ctypes.c_size_t),('peakJob',ctypes.c_size_t)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateJobObjectW.restype=wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT]
        kernel.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
        self.kernel=kernel;self.handle=kernel.CreateJobObjectW(None,None)
        info=Extended();info.basic.flags=0x2000
        if not self.handle or not kernel.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(self.handle,wintypes.HANDLE(process._handle)):
            self.close();raise OSError('无法隔离本机任务进程')
    def close(self):
        if self.handle:
            self.kernel.TerminateJobObject(self.handle,1)
            stats=ctypes.create_string_buffer(48);deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if not self.kernel.QueryInformationJobObject(self.handle,1,stats,48,None) or int.from_bytes(stats.raw[40:44],'little')==0:break
                time.sleep(.02)
            self.kernel.CloseHandle(self.handle);self.handle=None
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=8)


class DesktopWorker:
    def __init__(self,config,state=DEFAULT_STATE):
        self.url=service_url(config['url']);self.token=config['token'];self.state=state.resolve()
        self.state.mkdir(parents=True,exist_ok=True)
        self.session=requests.Session();self.session.trust_env=False
        self.capabilities={'ready':False,'models':[],'model':'','imageGeneration':False}
        self.last_probe=0
    def remote(self,action,data):
        from local_project_store import pack_record
        from image_wire import decode_job
        with self.session.post(self.url+'/desktop-relay/v1/'+action,json=pack_record(data),headers={'Authorization':'Bearer '+self.token},timeout=(10,45),allow_redirects=False,stream=True) as response:
            if response.status_code!=200:raise RuntimeError('共享网站暂未接受请求（HTTP '+str(response.status_code)+'），原任务不会自动重跑')
            buffer=bytearray()
            for part in response.iter_content(65536):
                buffer.extend(part)
                if len(buffer)>MAX_BYTES:raise ValueError('服务器返回的数据过大')
            value=json.loads(buffer)
            if not isinstance(value,dict):raise ValueError('服务器回复格式无效')
            return decode_job(value)
    def environment(self,folder):
        keys=('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','LANG','SSL_CERT_FILE','CODEX_CA_CERTIFICATE')
        env={k:os.environ[k] for k in keys if k in os.environ}
        binaries=list((BASE/'node_modules/@openai').glob('codex-*/vendor/*/bin/codex.exe'))
        if not binaries:raise ValueError('缺少随项目安装的 Codex，请先安装项目依赖')
        home=folder/'home';home.mkdir(parents=True,exist_ok=True)
        env.update(PYTHONPATH=str(ENGINE)+os.pathsep+str(BASE),PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONUTF8='1',
                   SHIJIE_TASK_ROOT=str(folder),CODEX_HOME=str(self.state/'codex'),SHIJIE_CODEX_BIN=str(binaries[0]),
                   SHIJIE_PYTHON=sys.executable,SHIJIE_CONFIG=str(folder/'no-server-config.toml'),SHIJIE_DATA_ROOT=str(folder/'private'),
                   HOME=str(home),USERPROFILE=str(home),DISABLE_SYSTEM_FONTS_LOAD='1',DJANGO_SETTINGS_MODULE='config.settings')
        return env
    def probe(self):
        temporary=tempfile.TemporaryDirectory(prefix='probe-',dir=self.state);tree=None
        try:
            process=subprocess.Popen([sys.executable,str(BASE/'tools/desktop_probe.py')],cwd=temporary.name,env=self.environment(Path(temporary.name)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            tree=ProcessTree(process)
            output,_=process.communicate(timeout=80)
            if process.returncode:raise ValueError('本机 Codex 连接检查失败，请在本机重新登录后重新配置共享服务')
            self.capabilities=json.loads(output)
            # Transport only the explicit public fields; no account email, plan, paths or auth file.
            self.capabilities={key:self.capabilities[key] for key in ('ready','models','model','imageGeneration','analysisProvider','imageProvider','imageModel') if key in self.capabilities}
            self.last_probe=time.monotonic()
        finally:
            if tree:tree.close()
            # Windows can briefly retain a terminated child's working-directory handle.
            # Retry cleanup after process exit; never leave probe credentials or outputs behind.
            if Path(temporary.name).resolve().parent!=self.state:raise ValueError('本机检查目录不匹配')
            deadline=time.monotonic()+5
            while True:
                try:temporary.cleanup();break
                except PermissionError:
                    if os.name!='nt' or time.monotonic()>=deadline:raise
                    time.sleep(.1)
    def launch(self,folder,job):
        modes=('codex','refine-ui','refine-selected','repair-order','replace-image','assistant-plan','assistant-split')
        if job.get('mode') not in modes or not isinstance(job.get('model'),str):raise ValueError('不支持的远程任务')
        from desktop_connections import credentials as desktop_credentials
        credentials=desktop_credentials(BASE,job.get('analysisProvider','codex'),{'provider':job.get('imageProvider','codex'),'model':job.get('imageModel','gpt-image-2')},job['mode'])
        process=subprocess.Popen([sys.executable,str(BASE/'tools/run_job.py'),job['id'],job['model']],cwd=folder,env=self.environment(folder),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        tree=ProcessTree(process)
        try:process.stdin.write(json.dumps(credentials).encode());process.stdin.close()
        except BaseException:tree.close();raise
        return process,tree
    def packet(self,folder,job,terminal=False):
        from image_wire import decode_job
        data={'id':job['id'],'lease':job['lease'],'status':'running',**({'run':job['run']} if job.get('run') else {})}
        progress=folder/'progress.json'
        if progress.exists():
            value=read_json_atomic(progress);data['progress']=value.get('progress',0)
        for name in ('partial','result'):
            path=folder/(name+'.json')
            if path.exists() and (name=='partial' or terminal):data[name]=decode_job(read_json_atomic(path))
        reply=folder/'reply.json'
        if reply.exists():data['previewText']=read_json_atomic(reply).get('text','')[:4000]
        if terminal:
            finished=folder/'finished.json'
            outcome=read_json_atomic(finished) if finished.exists() else {'status':'failed'}
            data['status']=outcome['status']
            if data['status']=='failed' and (folder/'failure.json').exists():
                from shijie.pipeline.diagnostics import sanitize_failure
                try:diagnostic=sanitize_failure(json.loads((folder/'failure.json').read_text('utf8')))
                except (OSError,ValueError):diagnostic=None
                if diagnostic:data['diagnostic']=diagnostic
            if 'elapsedSeconds' in outcome:data['elapsedSeconds']=outcome['elapsedSeconds']
        return data
    def discard(self,folder):
        target=folder.resolve();expected=(self.state/'jobs').resolve()
        if target.parent!=expected or target.is_symlink():raise ValueError('本机临时任务目录不匹配')
        shutil.rmtree(target)
    def upload_psd(self,folder,job):
        target=folder/'result.psd'
        # Large PSDs can be rendered from the complete scene in the user's browser.
        # Their binary copy must not prevent the editable result from being delivered.
        if not target.exists() or target.stat().st_size>MAX_BYTES:return False
        with target.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
        with target.open('rb') as stream:
            with self.session.post(self.url+'/desktop-relay/v1/artifact',data=stream,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/octet-stream','X-Shijie-Job':job['id'],'X-Shijie-Lease':job['lease'],'X-Shijie-Run':job.get('run',''),'X-Content-SHA256':checksum},timeout=(10,60),allow_redirects=False) as response:
                if response.status_code==413:return False
                if response.status_code!=200 or not response.json().get('ack'):raise RuntimeError('PSD 尚未回传成功，已保存在本机等待重传')
        return True
    def recover_outbox(self):
        waiting=[]
        for receipt in (self.state/'jobs').glob('*/receipt.json'):
            value=json.loads(receipt.read_text('utf8'))
            waiting.append((value.get('retryAfter',0),str(receipt),receipt,value))
        # One due result per cycle bounds recovery work. Oldest retry first also
        # lets another user's results pass a repeatedly failing delivery.
        for retry_at,_,receipt,value in sorted(waiting):
            if retry_at>time.time():continue
            self.handle({'id':receipt.parent.name,'lease':value['lease']})
            break
    def defer_delivery(self,folder,job):
        if not job.get('run'):
            raise RuntimeError('旧待回传任务缺少执行许可，保留本机结果并暂停接单')
        response=self.remote('update',{key:job[key] for key in ('id','lease','run')}|{'status':'delivery-pending'})
        if response.get('ack'):
            self.discard(folder)
        elif response.get('deferred'):
            receipt=folder/'receipt.json';saved=json.loads(receipt.read_text('utf8'))
            atomic_json(receipt,{**saved,'retryAfter':time.time()+60})
        else:
            raise RuntimeError('服务器尚未确认待回传状态，保留本机结果并暂停接单')
    def handle(self,job):
        ident=str(UUID(job['id']))
        if ident!=job['id'] or not isinstance(job.get('lease'),str) or not 1<=len(job['lease'])<=64:raise ValueError('接单标识无效')
        folder=self.state/'jobs'/ident;folder.mkdir(parents=True,exist_ok=True)
        receipt=folder/'receipt.json'
        if receipt.exists():
            saved=json.loads(receipt.read_text('utf8'))
            if saved.get('lease')!=job['lease']:raise ValueError('接单凭证发生变化，保留本机结果供处理')
            if saved.get('run'):
                job['run']=saved['run']
                permission=self.remote('start',{'id':ident,'lease':job['lease'],'run':job['run']})
                if not permission.get('owned'):self.discard(folder);return
            # A previous process may already have billed a turn. Only upload, never run again.
        else:
            atomic_json(folder/'input.json',job['input'])
            job['run']=str(uuid4());atomic_json(receipt,{'lease':job['lease'],'run':job['run'],'started':True})
            if job.get('cancel'):
                atomic_json(folder/'finished.json',{'status':'cancelled'})
            else:
                permission=self.remote('start',{'id':ident,'lease':job['lease'],'run':job['run']})
                if not permission.get('execute'):self.discard(folder);return
                process=None;tree=None;disconnected=None;started=time.monotonic();sent_revision=None;cancelled_at=None
                try:
                    process,tree=self.launch(folder,job)
                    while process.poll() is None:
                        if ((self.state/'stop').exists() or time.monotonic()-started>7200) and not (folder/'cancel').exists():(folder/'cancel').touch()
                        try:
                            self.remote('heartbeat',self.capabilities)
                            packet=self.packet(folder,job)
                            revision=(folder/'partial.json').stat().st_mtime_ns if (folder/'partial.json').exists() else None
                            if revision==sent_revision:packet.pop('partial',None)
                            response=self.remote('update',packet);sent_revision=revision
                            disconnected=None
                            if response.get('cancel') and not (folder/'cancel').exists():(folder/'cancel').touch()
                        except (requests.RequestException,ValueError,RuntimeError):
                            disconnected=disconnected or time.monotonic()
                            if time.monotonic()-disconnected>60 and not (folder/'cancel').exists():(folder/'cancel').touch()
                        if (folder/'cancel').exists() and time.time()-(folder/'cancel').stat().st_mtime>15:tree.close();break
                        time.sleep(2)
                finally:
                    if tree:tree.close()
        try:
            self.upload_psd(folder,job)
            response=self.remote('update',self.packet(folder,job,terminal=True))
        except (requests.RequestException,ValueError,RuntimeError,OSError):
            # Defer must be confirmed before another job can start. The receipt
            # always prevents another model execution, including after restart.
            self.defer_delivery(folder,job)
            return
        if response.get('ack'):self.discard(folder)
        else:raise RuntimeError('服务器尚未确认结果，已保存在本机等待回传')
    def run(self):
        from host_lock import exclusive
        with exclusive(self.state/'worker.lock'):
            (self.state/'stop').unlink(missing_ok=True)
            while not (self.state/'stop').exists():
                try:
                    if time.monotonic()-self.last_probe>30:
                        try:self.probe()
                        except (ValueError,OSError,subprocess.SubprocessError):
                            self.capabilities={'ready':False,'models':[],'model':'','imageGeneration':False};self.last_probe=time.monotonic()
                    self.remote('heartbeat',self.capabilities)
                    self.recover_outbox()
                    response=self.remote('claim',{})
                    if response.get('job'):self.handle(response['job'])
                    atomic_json(self.state/'status.json',{'connected':True,'ready':self.capabilities['ready'],'heartbeat':time.time(),
                        'pendingDelivery':sum(1 for _ in (self.state/'jobs').glob('*/receipt.json'))})
                except (requests.RequestException,ValueError,RuntimeError,OSError):
                    atomic_json(self.state/'status.json',{'connected':False,'ready':False,'heartbeat':time.time()})
                time.sleep(3)


def login_cache():
    # AIOA may set CODEX_HOME for its own runtime without a CLI login cache.
    # Prefer an explicit existing cache; otherwise use the user's normal CLI login.
    configured=os.environ.get('CODEX_HOME')
    if configured:
        candidate=Path(configured)/'auth.json'
        if candidate.is_file():return candidate
    return Path.home()/'.codex/auth.json'


def configure(state, url=None, token=None):
    url=service_url(url if url is not None else input('共享网站地址（例如 https://你的域名/shijie）：').strip())
    token=token if token is not None else getpass.getpass('管理员页面生成的配对码（输入不显示）：').strip()
    if not 32<=len(token)<=256:raise ValueError('配对码格式无效')
    auth=login_cache()
    if not auth.is_file():raise ValueError('没有找到本机 Codex 文件登录缓存，请先在本机完成 Codex CLI 登录')
    value=json.loads(auth.read_text('utf8'))
    if not isinstance(value.get('tokens'),dict):raise ValueError('需要本机 ChatGPT 套餐登录，不能用 API Key 代替')
    private_directory(state)
    from host_lock import exclusive
    with exclusive(state/'worker.lock'):
        if any((state/'jobs').glob('*/receipt.json')):raise ValueError('还有待回传的任务，请恢复原连接处理后再重新配对')
        # Import only the login cache, never the personal hooks, plugins, MCP servers or history.
        account=state/'codex';private_directory(account)
        atomic_json(account/'auth.json',value)
        (account/'config.toml').write_text('cli_auth_credentials_store = "file"\nhistory.persistence = "none"\nweb_search = "disabled"\n[features]\nshell_tool = false\nunified_exec = false\nmulti_agent = false\nview_image = false\napps = false\nremote_plugin = false\n',encoding='utf8')
        worker=DesktopWorker({'url':url,'token':token},state);worker.probe()
        if not worker.capabilities['ready']:raise ValueError('本机 Codex 套餐连接尚未就绪，未启用共享服务')
        worker.remote('heartbeat',worker.capabilities)
        encrypted=protect(json.dumps({'url':url,'token':token}).encode())
        temp=state/'connection.tmp';temp.write_bytes(encrypted);os.replace(temp,state/'connection.dat')
    print('本机配对成功。请在网页管理员页面启用共享服务，然后启动本机共享服务。')


def main():
    parser=argparse.ArgumentParser(description='AI拆图助手 · 本机 Codex 共享服务')
    parser.add_argument('--configure',action='store_true');parser.add_argument('--stop',action='store_true');parser.add_argument('--status',action='store_true')
    args=parser.parse_args();state=DEFAULT_STATE
    if args.configure:return configure(state)
    if args.stop:state.mkdir(parents=True,exist_ok=True);(state/'stop').touch();print('已请求停止接单，正在保留当前结果');return
    if args.status:
        value=json.loads((state/'status.json').read_text()) if (state/'status.json').exists() else {}
        online=time.time()-value.get('heartbeat',0)<90
        print('本机服务在线' if online and value.get('connected') and value.get('ready') else '本机服务未就绪或离线');return
    config=json.loads(protect((state/'connection.dat').read_bytes(),decrypt=True))
    DesktopWorker(config,state).run()


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError,requests.RequestException) as error:
        print('本机共享服务未启动或连接中断。请检查配置、Codex 登录和网页服务状态；没有自动重跑任务。',file=sys.stderr)
        raise SystemExit(1)
