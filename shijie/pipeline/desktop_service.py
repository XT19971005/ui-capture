"""Authenticated outbound desktop relay. User data retains its original owner."""
import hashlib
import json
import math
import secrets
import os
import tempfile
from pathlib import Path
from uuid import UUID
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from shijie.accounts.services import is_admin, allowed
from .models import DesktopService, Job, Audit
from .storage import job_root, user_root, check_space, write_scene, read_scene, write_json

FRESH_SECONDS = 90


def current():
    return DesktopService.objects.filter(pk=1).first()


def public(service=None):
    service = service or current()
    if not service:
        return {'enabled': False, 'paired': False, 'online': False, 'ready': False, 'models': [], 'model': '', 'imageGeneration': False}
    capabilities = service.capabilities
    online = bool(service.heartbeat and (timezone.now()-service.heartbeat).total_seconds() < FRESH_SECONDS)
    return {'enabled': service.enabled, 'paired': bool(service.token_digest), 'online': online,
            'ready': online and capabilities.get('ready', False),
            'models': capabilities.get('models', []), 'model': capabilities.get('model', ''),
            'imageGeneration': online and capabilities.get('imageGeneration', False)}


def secure(request):
    return request.is_secure() or (not settings.PRODUCTION and request.get_host().split(':')[0] in ('localhost','127.0.0.1','testserver'))


def admin(request, data=None):
    if not is_admin(request.user):
        return JsonResponse({'error':'只有管理员可以配置共享服务'}, status=403)
    if request.method == 'GET':
        return JsonResponse(public())
    if request.method != 'POST':
        return JsonResponse({'error':'请求方法无效'}, status=405)
    if not secure(request):
        return JsonResponse({'error':'共享服务配对需要 HTTPS；本机调试可使用回环地址'}, status=400)
    if not isinstance(data, dict) or data.get('action') not in ('pair','enable'):
        raise ValueError('共享服务参数无效')
    if getattr(settings,'LAN_SHARED',False) and data['action']=='pair':
        raise ValueError('局域网共享由本机启动程序自动配对，无需重新生成配对码')
    with transaction.atomic():
        DesktopService.objects.get_or_create(pk=1)
        service = DesktopService.objects.select_for_update().get(pk=1)
        disabling=data.get('action')=='enable' and data.get('enabled') is False
        if not disabling and Job.objects.filter(executor='desktop', status__in=['queued','running']).exists():
            return JsonResponse({'error':'请先完成或取消共享任务，再切换服务或重新配对'}, status=409)
        if data['action']=='pair':
            if set(data)!={'action'}: raise ValueError('配对参数无效')
            token=secrets.token_urlsafe(48)
            service.token_digest=hashlib.sha256(token.encode()).hexdigest()
            service.enabled=False; service.capabilities={};service.heartbeat=None
            result={'token':token}
        else:
            if set(data)!={'action','enabled'} or type(data['enabled']) is not bool: raise ValueError('共享开关参数无效')
            if data['enabled'] and not public(service)['ready']:
                raise ValueError('请先启动已配对的本机服务，并确认本机 Codex 已连接')
            service.enabled=data['enabled'];result={}
            if not service.enabled:
                Job.objects.filter(executor='desktop',status='queued').update(status='cancelled',cancel_requested=True,message='管理员已关闭共享服务',finished_at=timezone.now())
                Job.objects.filter(executor='desktop',status='running').update(cancel_requested=True)
        service.save()
        Audit.objects.create(actor=request.user,action='desktop.'+data['action'],target='desktop-service',detail={'enabled':service.enabled})
        return JsonResponse({**public(service),**result})


def capabilities(data):
    if not isinstance(data,dict) or set(data)!={'ready','models','model','imageGeneration'}:
        raise ValueError('本机状态参数无效')
    if type(data['ready']) is not bool or type(data['imageGeneration']) is not bool:
        raise ValueError('本机状态无效')
    models=data['models']
    if not isinstance(models,list) or len(models)>200:raise ValueError('本机模型目录无效')
    clean=[]
    for model in models:
        if not isinstance(model,dict) or not isinstance(model.get('id'),str) or not 0<len(model['id'])<=120:raise ValueError('模型标识无效')
        if any(ord(c)<32 for c in model['id']):raise ValueError('模型标识无效')
        name=model.get('name',model['id'])
        if not isinstance(name,str) or len(name)>200:raise ValueError('模型名称无效')
        clean.append({'id':model['id'],'name':name})
    ids=[m['id'] for m in clean]
    if len(set(ids))!=len(ids) or data['model'] not in (ids if data['ready'] else ['']):raise ValueError('本机默认模型无效')
    return {**data,'models':clean,'imageGeneration':data['ready'] and data['imageGeneration']}


def model_state(service=None):
    value=public(service)
    return {**value,'ok':True,'provider':'codex','configured':value['paired'],'shared':True,
            'error':None if value['ready'] else '共享电脑离线或 Codex 未连接，请联系管理员'}


def enqueue(owner, value, validated, root, size, service):
    """Called with desktop singleton and user rows locked in that order."""
    state=public(service)
    if not state['enabled']:
        return JsonResponse({'error':'共享服务已暂停，请联系本机管理员启用','code':'DESKTOP_PAUSED'},status=503)
    if not state['ready']:
        return JsonResponse({'error':'共享电脑离线或 Codex 未连接，任务未提交，请联系管理员','code':'DESKTOP_OFFLINE'},status=503)
    from .validation import requires_generation
    if requires_generation(validated) and not state['imageGeneration']:
        return JsonResponse({'error':'共享 Codex 当前未提供生图能力，任务未提交','code':'DESKTOP_IMAGES_UNAVAILABLE'},status=422)
    if Job.objects.filter(owner=owner,status__in=['queued','running']).count()>=settings.MAX_QUEUED_PER_USER or Job.objects.filter(executor='desktop',status__in=['queued','running']).count()>=50:
        return JsonResponse({'error':'共享任务队列已满，请稍后提交'},status=429)
    ids=[m['id'] for m in state['models']]
    requested=value.get('model') if validated['mode']=='assistant-plan' else owner.codex_model
    model=requested if requested in ids else state['model']
    if validated['mode']=='assistant-plan':value={**value,'provider':'codex','model':model}
    check_space(root,size)
    job=Job.objects.create(owner=owner,title=validated['title'],mode=validated['mode'],executor='desktop',message='等待共享电脑处理')
    write_scene(job_root(job)/'input.json',value)
    write_json(job_root(job)/'connection.json',{'provider':'codex','analysisProvider':'codex','imageProvider':'codex','imageModel':'gpt-image-2','needsCodex':True,'codexModel':model})
    if validated.get('resume'):
        write_scene(job_root(job)/'partial.json',validated['resume'])
        Job.objects.filter(pk=job.pk).update(partial_revision=1)
    return JsonResponse({'id':str(job.pk)},status=202)


def claim(service):
    # Returning the same lease after an ambiguous HTTP response never creates a new execution.
    job=Job.objects.select_for_update().filter(executor='desktop',status='running').order_by('created_at').first()
    if job is None:
        if not service.enabled or not public(service)['ready']:return {'job':None}
        for candidate in Job.objects.select_for_update().select_related('owner').filter(executor='desktop',status='queued').order_by('created_at'):
            if candidate.cancel_requested or not allowed(candidate.owner):
                candidate.status='cancelled';candidate.message='已取消';candidate.finished_at=timezone.now();candidate.save();continue
            job=candidate;job.status='running';job.started_at=job.heartbeat=timezone.now()
            job.relay_lease=secrets.token_urlsafe(32);job.message='共享电脑已接单';job.save();break
    if job is None:return {'job':None}
    snapshot=json.loads((job_root(job)/'connection.json').read_text())
    return {'job':{'id':str(job.pk),'lease':job.relay_lease,'mode':job.mode,'model':snapshot['codexModel'],
                   'input':read_scene(job_root(job)/'input.json'),'cancel':job.cancel_requested or not allowed(job.owner)}}


def start(data):
    if not isinstance(data,dict) or set(data)!={'id','lease','run'}:raise ValueError('执行许可参数无效')
    ident=UUID(data['id']);run=str(UUID(data['run']))
    job=Job.objects.select_for_update().filter(pk=ident,executor='desktop').first()
    # An owner can purge a terminal task while its last ACK is in flight.
    if job is None:return JsonResponse({'execute':False,'owned':False,'discard':True})
    if not secrets.compare_digest(job.relay_lease,str(data['lease'])):return JsonResponse({'error':'任务接单凭证不匹配'},status=409)
    if job.relay_run:return JsonResponse({'execute':False,'owned':secrets.compare_digest(job.relay_run,run)})
    if job.status!='running' or job.cancel_requested or not allowed(job.owner):return JsonResponse({'execute':False,'owned':False})
    job.relay_run=run;job.save(update_fields=['relay_run'])
    return JsonResponse({'execute':True,'owned':True})


def update(data):
    if not isinstance(data,dict) or set(data)-{'id','lease','run','status','progress','message','partial','result','previewText','elapsedSeconds'}:
        raise ValueError('任务回传参数无效')
    ident=UUID(data['id']);job=Job.objects.select_for_update().select_related('owner').filter(pk=ident,executor='desktop').first()
    if job is None or not secrets.compare_digest(job.relay_lease,str(data.get('lease',''))):
        return JsonResponse({'error':'任务接单凭证不匹配'},status=409)
    if job.relay_run and not secrets.compare_digest(job.relay_run,str(data.get('run',''))):return JsonResponse({'error':'任务执行许可不匹配'},status=409)
    if job.status in ('completed','failed','cancelled'):
        return JsonResponse({'ok':True,'ack':True,'cancel':True})
    state=data.get('status')
    if state=='delivery-pending':
        if set(data)!={'id','lease','run','status'} or not job.relay_run:
            raise ValueError('待回传状态参数无效')
        # Model execution is over. Release the global running slot, but do not ACK
        # delivery or require more user disk space to record this metadata.
        job.status='delivery-pending';job.heartbeat=timezone.now()
        job.message='生成结果保存在共享电脑，等待回传；请稍后刷新任务记录，无需重新生成'
        job.save(update_fields=['status','heartbeat','message'])
        return JsonResponse({'ok':True,'ack':False,'deferred':True})
    if state not in ('running','completed','failed','cancelled'):raise ValueError('任务状态无效')
    progress=data.get('progress',job.progress)
    if type(progress) not in (int,float) or not math.isfinite(progress) or not 0<=progress<=1:raise ValueError('进度无效')
    cancel=job.cancel_requested or not allowed(job.owner)
    elapsed=data.get('elapsedSeconds')
    if elapsed is not None and (type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0):raise ValueError('任务执行耗时无效')
    # The paired worker times actual execution. Offline result delivery is not model execution.
    duration=elapsed if state!='running' and elapsed is not None else (timezone.now()-job.started_at).total_seconds() if job.started_at else 0
    expired=duration>settings.JOB_TIMEOUT
    folder=job_root(job)
    if any(field in data for field in ('partial','result','previewText')):
        check_space(user_root(job.owner_id),len(json.dumps(data).encode()))
    for field in ('partial','result'):
        if field not in data:continue
        scene=data[field]
        if not isinstance(scene,dict):raise ValueError('任务结果无效')
        if field=='partial' or job.mode!='assistant-plan':
            from .validation import validate_resume
            scene=validate_resume(scene)
            scene.pop('_generationRecoveryId',None)
            scene['_sessionId']=str(job.pk)
            if (folder/'result.psd').exists():scene['delivery']={'storage':'server','sessionId':str(job.pk),'filename':job.title+'.psd'}
        # Cancelled work can retain a candidate; it is never reported as applied or completed.
        target='partial' if cancel or expired else field
        write_scene(folder/(target+'.json'),scene)
        if target=='partial':job.partial_revision+=1
    preview=data.get('previewText')
    if preview is not None:
        if not isinstance(preview,str) or len(preview)>4000:raise ValueError('回复预览过长')
        write_json(folder/'reply.json',{'text':preview})
    job.progress=max(job.progress,progress);job.heartbeat=timezone.now()
    # Messages from a remote process cannot leak local paths or provider diagnostics.
    job.message={'running':'共享电脑正在处理','completed':'处理完成，请核对结果','failed':'共享电脑处理未完成，已有结果保留；请联系管理员检查','cancelled':'已取消，已有结果保留'}[state]
    if state!='running':
        if state=='completed' and 'result' not in data:raise ValueError('完成任务缺少结果')
        job.status='failed' if expired else 'cancelled' if cancel else state
        job.finished_at=timezone.now()
        if expired:job.message='任务超时，已有结果保留'
    job.save()
    return JsonResponse({'ok':True,'ack':state!='running','cancel':cancel or expired})


def artifact(request):
    if request.content_type!='application/octet-stream':raise ValueError('PSD 上传格式无效')
    ident=UUID(request.headers.get('X-Shijie-Job',''));lease=request.headers.get('X-Shijie-Lease','');expected=request.headers.get('X-Content-SHA256','')
    if len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected):raise ValueError('PSD 校验值无效')
    job=Job.objects.select_for_update().filter(pk=ident,executor='desktop').first()
    if not job or not secrets.compare_digest(job.relay_lease,lease):return JsonResponse({'error':'任务接单凭证不匹配'},status=409)
    if job.relay_run and not secrets.compare_digest(job.relay_run,request.headers.get('X-Shijie-Run','')):return JsonResponse({'error':'任务执行许可不匹配'},status=409)
    if job.status not in ('running','delivery-pending','completed'):return JsonResponse({'ok':True,'ack':True,'cancel':True})
    size=int(request.headers.get('Content-Length','0'))
    if not 26<=size<=276*1024**2:raise ValueError('PSD 文件大小无效')
    check_space(user_root(job.owner_id),size)
    folder=job_root(job);folder.mkdir(parents=True,exist_ok=True);temporary=None
    try:
        digest=hashlib.sha256();count=0
        with tempfile.NamedTemporaryFile(dir=folder,delete=False) as output:
            temporary=Path(output.name)
            for part in request:
                if count==0 and not (part.startswith(b'8BPS\x00\x01') or part.startswith(b'8BPS\x00\x02')):raise ValueError('PSD 标识无效')
                count+=len(part)
                if count>size:raise ValueError('PSD 文件超过声明大小')
                output.write(part);digest.update(part)
            output.flush();os.fsync(output.fileno())
        if count!=size or digest.hexdigest()!=expected:raise ValueError('PSD 文件校验未通过')
        target=folder/'result.psd'
        if job.status=='completed' and target.exists():
            with target.open('rb') as stream:old=hashlib.file_digest(stream,'sha256').hexdigest()
            if old!=expected:raise ValueError('已完成任务的 PSD 不可替换')
        else:os.replace(temporary,target)
    finally:
        if temporary:temporary.unlink(missing_ok=True)
    return JsonResponse({'ok':True,'ack':True})


@csrf_exempt
@require_POST
def relay(request, action):
    if not secure(request):return JsonResponse({'error':'本机接单通道需要 HTTPS'},status=403)
    token=request.headers.get('Authorization','').removeprefix('Bearer ')
    if not 32<=len(token)<=256:return JsonResponse({'error':'接单凭证无效'},status=401)
    if action!='artifact' and request.content_type!='application/json':return JsonResponse({'error':'请使用 JSON 请求'},status=400)
    try:
        with transaction.atomic():
            service=DesktopService.objects.select_for_update().filter(pk=1).first()
            if not service or not service.token_digest or not secrets.compare_digest(service.token_digest,hashlib.sha256(token.encode()).hexdigest()):
                return JsonResponse({'error':'接单凭证无效或已撤销'},status=401)
            if action=='artifact':return artifact(request)
            from image_wire import decode_job
            data=decode_job(json.loads(request.body))
            if action=='heartbeat':
                if len(request.body)>64*1024:raise ValueError('本机状态过大')
                service.capabilities=capabilities(data);service.heartbeat=timezone.now();service.save()
                response=JsonResponse({'ok':True,'enabled':service.enabled})
            elif action=='claim':
                if data!={}:raise ValueError('接单参数无效')
                from local_project_store import pack_record
                response=JsonResponse(pack_record(claim(service)))
            elif action=='start':response=start(data)
            elif action=='update':response=update(data)
            else:return JsonResponse({'error':'接口不存在'},status=404)
            response['Cache-Control']='no-store'
            return response
    except (ValueError,TypeError,KeyError,RecursionError,UnicodeError):
        return JsonResponse({'error':'本机接单请求或结果无效'},status=400)
    except OSError:
        return JsonResponse({'error':'结果暂未保存，请保留本机结果并重试回传'},status=507)
