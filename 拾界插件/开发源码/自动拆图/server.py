from runtime import ROOT, STATE
import concurrent.futures, copy, io, json, logging, math, os, re, secrets, threading, time, uuid
from session_outputs import SESSIONS,CAPTURES
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file
from werkzeug.serving import make_server
from image_wire import decode_job,measure,MAX_HTTP_BYTES

PORT=19217
TOKEN=secrets.token_urlsafe(32)
app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=MAX_HTTP_BYTES
jobs={};lock=threading.Lock();pool=concurrent.futures.ThreadPoolExecutor(max_workers=1)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
LOCAL_ORIGINS={'http://127.0.0.1:19217','http://localhost:19217'}
ALLOWED_ORIGINS=LOCAL_ORIGINS|{o.rstrip('/') for o in json.loads(Path(__file__).with_name('native-host.json').read_text('utf-8-sig')).get('allowed_origins',[])}

@app.errorhandler(413)
def payload_too_large(error):return jsonify(error='工程传输数据超过容量限制，原工程已保留。请保存工程后重试；不会自动重新拆分或压缩图片。'),413

@app.before_request
def guard():
    if request.host not in ('127.0.0.1:'+str(PORT),'localhost:'+str(PORT)):return jsonify(error='Invalid host'),403
    origin=request.headers.get('Origin')
    if origin and origin not in ALLOWED_ORIGINS:return jsonify(error='Origin not allowed'),403
    if request.method=='OPTIONS':return '',204
    if request.path in ('/ping','/') or request.path.endswith(('.html','.js','.css','.png','.svg','.ico','.wasm','.gz','.traineddata')):return None
    if request.path=='/connection':
        if request.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'):return jsonify(error='Same-origin connection required'),403
        return None
    if not secrets.compare_digest(request.headers.get('X-Shijie-Token',''),TOKEN):return jsonify(error='连接已过期，请重新连接本机引擎'),401

@app.after_request
def cors(response):
    origin=request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin']=origin
        response.headers['Vary']='Origin'
        response.headers['Access-Control-Allow-Headers']='Content-Type, X-Shijie-Token'
        response.headers['Access-Control-Allow-Methods']='GET, POST, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Private-Network']='true'
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response

@app.get('/')
def home():return send_from_directory(ROOT/'插件程序/edge','image-editor.html')

@app.get('/connection')
def local_connection():return jsonify(url='http://127.0.0.1:19217',token=TOKEN)

@app.get('/<path:name>')
def static_editor(name):
    if name.startswith(('api/','projects/')):return jsonify(error='Not found'),404
    return send_from_directory(ROOT/'插件程序/edge',name)

def stored_projects():
    import hashlib
    items={}
    for root in (ROOT.parent/'交付包',ROOT/'项目'):
      if not root.exists():continue
      for p in root.iterdir():
        file=p/'1_过程/02_结构/工程.scene.json'
        if not p.is_dir() or not file.is_file() or not file.resolve().is_relative_to(root.resolve()):continue
        ident='codex-'+hashlib.sha256(str(p.resolve()).encode('utf8')).hexdigest()[:20];items[ident]=file
    return items

@app.get('/projects')
def list_projects():
    items=[]
    for ident,file in stored_projects().items():
        try:
            scene=json.loads(file.read_text('utf8'))
            if not scene.get('delivery'):continue
            items.append({'id':ident,'title':scene.get('title','图片拆分'),'updated':int(file.stat().st_mtime*1000)})
        except (OSError,ValueError):continue
    return jsonify(items=items)

@app.get('/projects/<ident>')
def read_project(ident):
    file=stored_projects().get(ident)
    if file is None:return jsonify(error='项目不存在'),404
    scene=json.loads(file.read_text('utf8'));scene['_projectId']=ident
    return jsonify(scene)

@app.get('/projects/<ident>/psd')
def download_verified_psd(ident):
    import hashlib
    file=stored_projects().get(ident)
    if file is None:return jsonify(error='项目不存在'),404
    try:
        scene=json.loads(file.read_text('utf8'));project=file.parents[2].resolve()
        target=Path(scene['delivery']['psd']).resolve();output=(project/'2_输出').resolve()
        if target.parent!=output or target.suffix.lower()!='.psd' or not target.is_file():return jsonify(error='项目输出路径无效'),409
        audit=json.loads((project/'1_过程/03_检查/检查结果.json').read_text('utf8'))
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        if audit.get('structuralChecks')!='PASS' or audit.get('assetChecks')!='PASS' or audit.get('psdSHA256')!=digest:return jsonify(error='PSD 已变化或独立检查未通过，请重新导出并检查'),409
        from session_outputs import visual_records
        visual_records(scene,project/'1_过程/03_检查')
        response=send_file(target,as_attachment=True,download_name=target.name,mimetype='image/vnd.adobe.photoshop')
        response.headers['X-Shijie-PSD-SHA256']=digest
        return response
    except (OSError,ValueError,KeyError):return jsonify(error='项目输出或实际画面复核未通过'),409

@app.get('/ping')
def ping():return jsonify(service='shijie-engine',version='0.9.0')

@app.get('/sessions/<ident>/scene')
def session_scene(ident):
    item=SESSIONS.get(ident)
    if item is None:return jsonify(error='当前会话已释放或过期'),404
    return jsonify(item['scene'])

@app.get('/sessions/<ident>/psd')
def session_psd(ident):
    import hashlib
    item=SESSIONS.get(ident)
    if item is None:return jsonify(error='当前会话已释放或过期'),404
    if item['psd'] is None:return jsonify(error='独立画面检查尚未通过，请校对后重新导出'),409
    item=SESSIONS.take(ident)
    if item is None:return jsonify(error='当前会话已释放或过期'),404
    digest=hashlib.sha256(item['psd']).hexdigest() if item['psd'] is not None else None
    if digest is None or digest!=item['scene']['delivery'].get('psdSHA256'):return jsonify(error='PSD 会话字节已变化，请重新导出并检查'),409
    response=send_file(io.BytesIO(item['psd']),as_attachment=True,download_name=item['filename'],mimetype='image/vnd.adobe.photoshop')
    response.headers['X-Shijie-PSD-SHA256']=digest
    return response

@app.get('/sessions/<ident>/review')
def session_review(ident):
    item=SESSIONS.get(ident)
    if item is None:return jsonify(error='当前会话已释放或过期'),404
    return jsonify(item['audit'] or {})

@app.delete('/sessions/<ident>')
def release_session(ident):
    SESSIONS.take(ident)
    return jsonify(ok=True)

@app.post('/captures')
def create_capture():
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)-{'image','title','token'}:return jsonify(error='框选参数无效'),400
    image=data.get('image')
    if not isinstance(image,str) or len(image)>36000000 or not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',image):return jsonify(error='框选图片无效'),400
    try:
        from engine import load_source
        loaded=load_source(image);loaded.close()
    except Exception:return jsonify(error='框选图片无法读取或超过尺寸限制'),400
    result=CAPTURES.put({'src':image,'title':str(data.get('title') or '框选截图')[:160],'created':int(time.time()*1000)},None)
    return jsonify(id=result['_sessionId']),201

@app.get('/captures/<ident>')
def consume_capture(ident):
    item=CAPTURES.take(ident)
    if item is None:return jsonify(error='框选图片已读取或过期'),404
    return jsonify({k:item['scene'][k] for k in ('src','title','created')})

@app.delete('/captures/<ident>')
def release_capture(ident):
    CAPTURES.take(ident)
    return jsonify(ok=True)

@app.get('/health')
def health():
    from codex_pipeline import requirements
    from codex_client import command
    missing=requirements()
    try:command();available=True
    except RuntimeError:available=False
    with lock:active_jobs=sum(j['status'] in ('queued','running') for j in jobs.values())
    return jsonify(service='shijie-engine',version='0.9.0',ready=not missing,missing=missing,codexAvailable=available,activeJobs=active_jobs,imageWireVersion=1,jobModes=['codex','refine-ui','refine-selected','repair-order'])

@app.get('/codex/status')
def codex_status():
    from codex_client import CLIENT
    try:
        a=CLIENT.account();return jsonify(ok=True,**a,models=CLIENT.models() if a['ready'] else [],model=CLIENT.model() if a['ready'] else None)
    except Exception as e:return jsonify(ok=False,ready=False,error=str(e)[:400])

@app.post('/codex/model')
def codex_model():
    from codex_client import CLIENT
    data=request.get_json(silent=True) or {}
    if set(data)!={'model'} or not isinstance(data['model'],str):return jsonify(error='模型参数无效'),400
    if data['model'] not in [m['id'] for m in CLIENT.models()]:return jsonify(error='该模型不在当前账号可用列表中'),400
    CLIENT.selected_model=data['model'];return jsonify(ok=True,model=data['model'])

@app.post('/codex/login')
def codex_login():
    from codex_client import CLIENT
    try:return jsonify(ok=True,**CLIENT.login())
    except Exception as e:return jsonify(error=str(e)[:400]),400

@app.post('/open-output')
def open_output():
    import subprocess
    data=request.get_json(silent=True) or {}
    if set(data)!={'project'} or not isinstance(data['project'],str):return jsonify(error='项目参数无效'),400
    target=(Path(data['project'])/'2_输出').resolve()
    if not any(target.is_relative_to(r.resolve()) for r in (ROOT/'项目',ROOT.parent/'交付包')) or not target.is_dir():return jsonify(error='项目不存在'),400
    subprocess.Popen(['explorer.exe',str(target)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return jsonify(ok=True)

def validate_resume(value):
    if value is None:return None
    measure(value)
    if not isinstance(value,dict) or value.get('format')!='shijie-scene' or value.get('version')!=2:raise ValueError('续拆工程格式无效')
    def number(n,low,high):return isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) and low<=n<=high
    def valid_id(ident):return isinstance(ident,str) and bool(ident) and len(ident)<=160
    if not all(number(value.get(k),1,6000) for k in ('width','height')):raise ValueError('续拆画板尺寸无效')
    def node_ids(nodes):
        if not isinstance(nodes,list) or len(nodes)>700:raise ValueError('续拆图层数量无效')
        ids=set()
        for n in nodes:
            if not isinstance(n,dict) or n.get('type') not in ('text','image','path','rect','ellipse'):raise ValueError('续拆图层类型无效')
            ident=n.get('id')
            if not valid_id(ident) or ident in ids:raise ValueError('续拆图层标识无效')
            ids.add(ident)
            if not all(number(n.get(k),-12000,12000) for k in ('x','y')) or not all(number(n.get(k),.001,12000) for k in ('width','height')):raise ValueError('续拆图层尺寸无效')
        return ids
    ids=node_ids(value.get('nodes'))
    for k in ('edges','groups'):
        if k in value and (not isinstance(value[k],list) or len(value[k])>1400):raise ValueError('续拆工程结构无效')
    def groups_valid(groups):
        if not isinstance(groups,list) or len(groups)>1400:raise ValueError('续拆分组数量无效')
        seen=set();owners={}
        for group in groups:
            if not isinstance(group,dict) or not valid_id(group.get('id')) or group['id'] in seen or not isinstance(group.get('children'),list) or not group['children'] or len(group['children'])>2100:raise ValueError('续拆分组结构无效')
            seen.add(group['id'])
            for ident in group['children']:
                if not valid_id(ident) or ident in owners or ident==group['id']:raise ValueError('续拆分组成员无效')
                owners[ident]=group['id']
        for ident in owners:
            path=set();current=ident
            while current in owners:
                if current in path:raise ValueError('续拆分组循环引用')
                path.add(current);current=owners[current]
    groups_valid(value.get('groups',[]))
    recognition=value.get('recognition',{})
    if not isinstance(recognition,dict):raise ValueError('续拆恢复记录无效')
    if 'resumePendingNodes' in recognition and len(ids|node_ids(recognition['resumePendingNodes']))>700:raise ValueError('续拆待完成图层数量无效')
    if 'resumeGroups' in recognition:groups_valid(recognition['resumeGroups'])
    for key in ('resumeNodeOrder','pendingGenerationIds'):
        if key in recognition:
            entries=recognition[key]
            if not isinstance(entries,list) or len(entries)>1400 or any(not valid_id(ident) for ident in entries) or len(set(entries))!=len(entries):raise ValueError('续拆恢复图层标识无效')
    if 'resumePlan' in recognition and not isinstance(recognition['resumePlan'],dict):raise ValueError('续拆恢复规划无效')
    def inspect(v,depth=0):
        if depth>40:raise ValueError('续拆工程层级过多')
        if isinstance(v,float) and not math.isfinite(v):raise ValueError('续拆工程数值无效')
        if isinstance(v,dict):
            for k,item in v.items():
                if k in ('src','source','originalSource','comparisonSource') and item is not None and (not isinstance(item,str) or not item.startswith('data:image/') or len(item)>36000000):raise ValueError('续拆图片必须内嵌在工程中')
                inspect(item,depth+1)
        elif isinstance(v,list):
            for item in v:inspect(item,depth+1)
    inspect(value)
    result=copy.deepcopy(value)
    for k in ('delivery','_sessionId','_projectId'):result.pop(k,None)
    return result

def run(ident,source,title,mode,original,resume=None,selected_ids=None):
    item=jobs[ident]
    def progress(value,message):
        with lock:item.update(progress=max(item.get('progress',0),float(value)),message=message)
    def preview(scene):
        with lock:
            if item['status']=='running' and not item['cancel'].is_set():item.update(partial=copy.deepcopy(scene),partialRevision=item.get('partialRevision',0)+1)
    try:
        if item['cancel'].is_set():raise InterruptedError('已取消')
        item['status']='running'
        if mode=='repair-order':
            from layer_order import process
        elif mode=='refine-selected':
            from selected_refine import process
        elif mode=='refine-ui':
            from refine_ui import process
        else:
            from codex_pipeline import process
        options={'selected_ids':selected_ids} if mode=='refine-selected' else {}
        result=process(source,title,progress,item['cancel'].is_set,original_source=original,on_scene=preview,resume_scene=resume,**options)
        with lock:
            if item['cancel'].is_set():
                SESSIONS.take(result.get('_sessionId'));item.update(status='cancelled',message='已取消')
            else:
                missing=result.get('recognition',{}).get('pendingGenerationIds',[])
                split_message=('仍有'+str(len(missing))+'项未完成，可继续拆分') if missing else '尚未全部完成，可继续拆分' if result.get('_partial') or result.get('recognition',{}).get('extractionStatus')=='INCOMPLETE' else '拆分完成'
                item.update(status='completed',progress=1,message='层级修复完成，请核对遮挡关系' if mode=='repair-order' else '选中项处理完成' if mode=='refine-selected' else '精修完成，请校对标记项' if mode=='refine-ui' else split_message,sessionId=result['_sessionId'])
    except InterruptedError:item.update(status='cancelled',message='已取消，临时文件已清理')
    except Exception as e:
        # Local processing errors only; no source pixels or credentials are logged.
        logging.exception('Local pipeline failed')
        item.update(status='failed',message=('层级修复未完成：' if mode=='repair-order' else '选中项处理未完成：' if mode=='refine-selected' else '精修未完成：' if mode=='refine-ui' else '智能拆图未完成：')+str(e)[:240])
        if isinstance(getattr(e,'diagnostics',None),dict):item['diagnostics']=e.diagnostics
    finally:
        with lock:
            if item['status']=='completed':item.pop('partial',None)
            item['finished']=time.time()

@app.post('/jobs')
def submit():
    try:data=decode_job(request.get_json(silent=True))
    except (ValueError,TypeError,RecursionError,UnicodeError) as exc:return jsonify(error=str(exc)[:240]),400
    if not isinstance(data,dict) or set(data)-{'image','title','mode','original','resume','selectedIds'}:return jsonify(error='任务参数无效'),400
    source=data.get('image');original=data.get('original',source);title=str(data.get('title') or '智能拆图')[:160];mode=data.get('mode','codex')
    if mode not in ('codex','refine-ui','refine-selected','repair-order'):return jsonify(error='处理方式无效'),400
    if not isinstance(source,str) or len(source)>36000000 or not source.startswith('data:image/'):return jsonify(error='请选择有效图片'),400
    if not isinstance(original,str) or len(original)>36000000 or not original.startswith('data:image/'):return jsonify(error='原图无效'),400
    try:resume=validate_resume(data.get('resume'))
    except (ValueError,TypeError,RecursionError) as exc:return jsonify(error=str(exc)),400
    selected_ids=data.get('selectedIds')
    if mode=='refine-selected':
        from selected_refine import validate_selection
        try:validate_selection(resume,selected_ids)
        except (ValueError,TypeError):return jsonify(error='请选择工程中存在的图层'),400
    elif selected_ids is not None:return jsonify(error='当前处理方式不接受选中图层'),400
    if mode=='repair-order':
        from layer_order import hierarchy
        try:hierarchy(resume)
        except (ValueError,TypeError,RecursionError) as exc:return jsonify(error=str(exc)),400
    if mode=='refine-ui':
        from refine_ui import can_refine
        if not can_refine(resume):return jsonify(error='当前工程没有可精修的完整、未锁定文字或矢量图层；请先完成拆图'),400
    with lock:
        for key in list(jobs):
            if jobs[key].get('finished',float('inf'))<time.time()-3600:del jobs[key]
        if any(j['status'] in ('queued','running') for j in jobs.values()):return jsonify(error='已有图片正在处理，请等待完成或取消'),409
        ident=uuid.uuid4().hex;jobs[ident]={'status':'queued','progress':0,'message':'准备修复层级…' if mode=='repair-order' else '准备精修…' if mode=='refine-ui' else '准备智能拆图…','mode':mode,'cancel':threading.Event()}
    if resume:
        with lock:jobs[ident].update(partial=copy.deepcopy(resume),partialRevision=1)
    pool.submit(run,ident,source,title,mode,original,resume,selected_ids)
    return jsonify(id=ident),202

@app.get('/jobs/<ident>')
def status(ident):
    item=jobs.get(ident)
    if not item:return jsonify(error='任务不存在或已过期'),404
    with lock:
        data={k:v for k,v in item.items() if k not in ('cancel','finished','sessionId','partial')}
        try:after=int(request.args.get('afterRevision','-1'))
        except ValueError:after=-1
        if item.get('partial') and after<item.get('partialRevision',0):data['partial']=item['partial']
        if item.get('sessionId'):
            session=SESSIONS.get(item['sessionId'])
            if session:data['result']=session['scene']
            else:data.update(status='expired',message='当前会话已释放或过期')
        return jsonify(data)

@app.delete('/jobs/<ident>')
def cancel(ident):
    with lock:
        item=jobs.get(ident)
        if not item:return jsonify(error='任务不存在'),404
        item['cancel'].set()
        if item['status'] not in ('queued','running'):
            # Order results contain no downloadable PSD; DELETE owns their fresh
            # result session even if an in-flight GET has not delivered its ID.
            if item['status']=='completed' and item.get('mode')=='repair-order':SESSIONS.take(item.get('sessionId'))
            jobs.pop(ident,None)
    return jsonify(ok=True)

from web_capture import register_web_capture
register_web_capture(app)

if __name__=='__main__':
    logging.basicConfig(filename=STATE/'引擎错误.log',level=logging.ERROR,encoding='utf-8')
    server=make_server('127.0.0.1',PORT,app,threaded=True)
    record={'service':'shijie-engine','version':'0.9.0','port':PORT,'token':TOKEN,'pid':os.getpid()}
    tmp=STATE/'service.tmp';tmp.write_text(json.dumps(record),encoding='utf-8');tmp.replace(STATE/'service.json')
    try:server.serve_forever()
    finally:
        server.server_close()
        file=STATE/'service.json'
        try:
            if json.loads(file.read_text()).get('pid')==os.getpid():file.unlink()
        except (OSError,ValueError):pass
