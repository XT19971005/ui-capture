"""Capture real browser pages in isolated RAM-only sessions."""
import atexit,json,os,queue,shutil,subprocess,tempfile,threading,time,uuid
from urllib.parse import urlparse
from flask import request,jsonify
from runtime import ROOT,STATE

class BrowserBridge:
    def __init__(self,headless=False,profile=None):
        self.process=None;self.lock=threading.Lock();self.send_lock=threading.Lock();self.cancel_lock=threading.Lock();self.cancelled={};self.messages=queue.Queue();self.headless=headless;self.temp=None;self.manual_targets=set()
        atexit.register(self.stop)
    def start(self):
        if self.process and self.process.poll() is None:return
        node=shutil.which('node') or 'C:/Program Files/nodejs/node.exe'
        env=os.environ.copy()
        if self.headless:env['SHIJIE_WEB_HEADLESS']='1'
        # Never use any persistent or caller-supplied browser profile.
        if self.temp:self.temp.cleanup()
        self.temp=tempfile.TemporaryDirectory(prefix='shijie-web-')
        env['SHIJIE_WEB_TEMP']=self.temp.name
        self.messages=queue.Queue()
        self.manual_targets.clear()
        try:self.process=subprocess.Popen([node,str(ROOT/'开发源码/自动拆图/browser_capture.cjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:
            self.temp.cleanup();self.temp=None;raise
        pipe=self.process.stdout;messages=self.messages
        def read():
            for line in pipe:
                try:messages.put(json.loads(line))
                except ValueError:pass
            messages.put({'ok':False,'error':'网页浏览器已断开，请重新打开'})
        threading.Thread(target=read,daemon=True).start()
    def call(self,action,**args):
        if action=='capture' and not args.get('captureKey'):args['captureKey']=uuid.uuid4().hex
        key=args.get('captureKey') if action=='capture' else None
        with self.lock:
            running=bool(self.process and self.process.poll() is None)
            try:
                if self.was_cancelled(key):raise RuntimeError('已取消抓取')
                self.start();ident=uuid.uuid4().hex
                with self.send_lock:
                    if self.was_cancelled(key):
                        if not running:self.stop()
                        raise RuntimeError('已取消抓取')
                    self.process.stdin.write(json.dumps({'id':ident,'action':action,**args},ensure_ascii=False)+'\n');self.process.stdin.flush()
                deadline=time.monotonic()+90
                while True:
                    try:result=self.messages.get(timeout=max(.001,deadline-time.monotonic()))
                    except queue.Empty:
                        if action=='capture' and self.manual_targets:
                            if key:self.cancel(key)
                        else:self.stop()
                        raise RuntimeError('网页抓取超时，请重新打开后重试')
                    if result.get('id') not in (ident,None):continue
                    if not result.get('ok'):
                        if result.get('remaining')==0:self.stop()
                        raise RuntimeError(result.get('error','网页操作失败'))
                    response=result['result']
                    if action=='open' and response.get('id'):self.manual_targets.add(response['id'])
                    if action=='close':self.manual_targets.discard(args.get('target'))
                    if action in ('close','capture') and response.get('remaining')==0:self.stop()
                    if self.was_cancelled(key):raise RuntimeError('已取消抓取')
                    return response
            finally:
                with self.cancel_lock:self.cancelled.pop(key,None)
    def was_cancelled(self,key):
        with self.cancel_lock:
            now=time.monotonic()
            self.cancelled={k:v for k,v in self.cancelled.items() if now-v<300}
            return bool(key and key in self.cancelled)
    def cancel(self,key):
        with self.cancel_lock:
            self.cancelled[key]=time.monotonic()
            while len(self.cancelled)>512:self.cancelled.pop(next(iter(self.cancelled)))
        with self.send_lock:
            proc=self.process
            if proc and proc.poll() is None:
                try:proc.stdin.write(json.dumps({"action":"cancel","captureKey":key})+"\n");proc.stdin.flush()
                except (OSError,ValueError):pass
    def stop(self):
        proc=self.process;self.process=None
        self.manual_targets.clear()
        if proc:
            try:proc.stdin.close();proc.wait(timeout=30)
            except (OSError,subprocess.TimeoutExpired):
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                else:proc.terminate()
                proc.wait(timeout=5)
            finally:
                if proc.stdout:proc.stdout.close()
        if self.temp:
            # Edge background services may briefly hold a just-closed temp file.
            for attempt in range(30):
                try:self.temp.cleanup();self.temp=None;break
                except OSError:
                    if attempt==29:raise
                    time.sleep(.3)

def register_web_capture(app,bridge=None):
    bridge=bridge or BrowserBridge()
    app.extensions['shijie_web_capture']=bridge
    def valid_url(url):
        if not isinstance(url,str) or len(url)>8192:return False
        try:
            parsed=urlparse(url)
            return parsed.scheme in ('http','https') and bool(parsed.hostname) and not parsed.username and not parsed.password
        except ValueError:return False
    def valid_key(key):return isinstance(key,str) and bool(key) and len(key)<=128
    @app.post('/web/open')
    def web_open():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='请求参数必须是对象'),400
        url=data.get('url')
        if not valid_url(url):return jsonify(error='请输入有效的 http 或 https 网址'),400
        try:
            return jsonify(bridge.call('open',url=url))
        except (OSError,RuntimeError,ValueError) as exc:return jsonify(error=str(exc)),502
    @app.post('/web/capture')
    def web_capture():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='请求参数必须是对象'),400
        target=data.get('target')
        url=data.get('url')
        if url:
            if not valid_url(url):return jsonify(error='请输入有效的 http 或 https 网址'),400
        elif not valid_key(target):return jsonify(error='请输入网址或打开网页'),400
        key=data.get('captureKey');scope=data.get('scope','page')
        if key is not None and not valid_key(key):return jsonify(error='抓取任务标识无效'),400
        if scope not in ('page','viewport'):return jsonify(error='抓取范围无效'),400
        try:return jsonify(bridge.call('capture',target=target,url=url,scope=data.get('scope','page'),captureKey=data.get('captureKey')))
        except (OSError,RuntimeError,ValueError) as exc:return jsonify(error=str(exc)),502
    @app.post('/web/close')
    def web_close():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='请求参数必须是对象'),400
        if not valid_key(data.get('target')):return jsonify(error='请先打开网页'),400
        try:return jsonify(bridge.call('close',target=data['target']))
        except (OSError,RuntimeError,ValueError) as exc:return jsonify(error=str(exc)),502

    @app.post('/web/cancel')
    def web_cancel():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='请求参数必须是对象'),400
        key=data.get('captureKey')
        if not valid_key(key):return jsonify(error='缺少有效抓取任务'),400
        bridge.cancel(key)
        return jsonify(ok=True)
