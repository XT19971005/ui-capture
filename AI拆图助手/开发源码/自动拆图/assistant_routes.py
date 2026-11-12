"""Free conversation shares the engine queue and cancellation lifecycle."""
import tempfile, threading, time, uuid
from pathlib import Path
from flask import request, jsonify
from runtime import TEMP
from image_wire import decode_job
from free_assistant import validate_request, plan

def register(app,jobs,lock,pool,project_store=None):
 @app.post('/assistant/generation-recovery/ack')
 def acknowledge_generation_recovery():
  from generation_recovery import acknowledge
  try:
   value=request.get_json(silent=True)
   if not isinstance(value,dict):raise ValueError('恢复确认参数无效')
   if not project_store:return jsonify(deleted=False,retained=True)
   store=project_store();answer=acknowledge(store,value.get('projectId'),value.get('recoveryId'),value.get('recoveryVersion'))
   if answer.get('deleted') and isinstance(value.get('jobId'),str):
    main=store.get(value['projectId'])
    if not main['doc'].get('_generationStages',{}).get('blocked'):
     with lock:
      item=jobs.get(value['jobId']);returned=(item.get('result') or item.get('partial') or {}) if item else {}
      if item and item.get('status') in ('completed','failed','cancelled') and returned.get('_generationRecoveryId')==value.get('recoveryId') and returned.get('_generationRecoveryVersion')==value.get('recoveryVersion'):jobs.pop(value['jobId'],None)
   return jsonify(answer)
  except Exception:return jsonify(deleted=False,retained=True)

 @app.route('/image-provider',methods=['GET','POST'])
 def image_provider():
  from image_provider import status,save
  try:
   if request.method=='GET':return jsonify(status())
   def commit(write):
    with lock:
     if any(j['status'] in ('queued','running') for j in jobs.values()):raise ValueError('请等待当前任务结束后修改图片模型')
     write()
   with lock:
    if any(j['status'] in ('queued','running') for j in jobs.values()):return jsonify(error='请等待当前任务结束后修改图片模型'),409
   return jsonify(save(request.get_json(silent=True),commit=commit))
  except ValueError as error:return jsonify(error=str(error)),400
  except Exception:return jsonify(error='图片连接未完成，请检查本人亿创配置和模型权限'),400

 @app.post('/image-provider/catalog')
 def image_catalog():
  from image_provider import refresh
  try:return jsonify(refresh(request.get_json(silent=True)))
  except ValueError as error:return jsonify(error=str(error)),400
  except Exception:return jsonify(error='亿创模型目录暂不可读取，请检查网络与本人 Key'),503

 @app.get('/assistant/models')
 def assistant_models():
  from assistant_models import status,_TygptError
  try:return jsonify(status(request.args.get('provider','codex')))
  except _TygptError as error:return jsonify(error=str(error)),503
  except Exception:return jsonify(error='模型连接不可用，请检查本人Codex账号或TYGPT PAT'),503

 @app.post('/assistant/key')
 def assistant_key():
  from assistant_models import save_key,_TygptError
  try:
   body=request.get_json(silent=True)
   if not isinstance(body,dict) or set(body)!={'key'}:raise ValueError('连接参数无效')
   def commit(write):
    with lock:
     if any(j['status'] in ('queued','running') for j in jobs.values()):raise ValueError('请等待当前任务结束后修改 TYGPT 连接')
     write()
   with lock:
    if any(j['status'] in ('queued','running') for j in jobs.values()):return jsonify(error='请等待当前任务结束后修改 TYGPT 连接'),409
   return jsonify(save_key(body['key'],commit=commit))
  except _TygptError as error:return jsonify(error=str(error)),400
  except Exception:return jsonify(error='TYGPT连接未保存，请核对本人PAT、网络及模型权限'),400

 def work(ident,body,split=False):
  item=jobs[ident]
  try:
   if item['cancel'].is_set():raise InterruptedError()
   item.update(status='running',message='正在理解画面与要求…')
   def status(message):
    with lock:item['message']=str(message)[:300]
   recovery=None
   if split and project_store:
    from generation_recovery import GenerationRecovery
    recovery=GenerationRecovery(project_store(),body['title'],body.get('projectId'))
   with tempfile.TemporaryDirectory(prefix='shijie-assistant-',dir=TEMP) as folder:
    if split:
     from assistant_split import generate
     def progress(value,message):
      with lock:item.update(progress=value,message=message)
     def checkpoint(scene):
      with lock:item.update(partial=scene,partialRevision=item.get('partialRevision',0)+1)
      if recovery:
       try:recovery.save(scene)
       except Exception:raise ValueError('已完成图层的磁盘保存失败；任务已停止，已有结果仍可取回，请检查磁盘后保存')
       scene['_generationRecoveryId']=recovery.ident
       with lock:item['recoveryId']=recovery.ident
     result=generate(body,Path(folder),item['cancel'].is_set,progress,on_scene=checkpoint)
     if recovery:
      recovery.save(result)
      result['_generationRecoveryId']=recovery.ident
    else:
     def reply(text):
      with lock:
       if not item['cancel'].is_set():item['previewText']=text
     result=plan(body,Path(folder),item['cancel'].is_set,status,reply)
   with lock:
    if item['cancel'].is_set():raise InterruptedError()
    item.update(status='completed',result=result,progress=1,message='助手已回复')
  except InterruptedError:item.update(status='cancelled',message='已停止对话，工程未修改')
  except Exception as error:
   # Do not emit HTTP request exceptions or credentials in responses/logs.
   message=str(error)[:240] if isinstance(error,ValueError) else '模型连接或回复未完成，请检查连接后重试'
   item.update(status='failed',message=message)
  finally:item['finished']=time.time()

 @app.post('/assistant/split')
 @app.post('/assistant/jobs')
 def assistant_job():
  split=request.path=='/assistant/split'
  try:
   from assistant_split import validate as validate_split
   raw=decode_job(request.get_json(silent=True))
   if split:validate_split(raw);body=raw
   else:body=validate_request(raw)
  except (ValueError,TypeError,RecursionError,KeyError):return jsonify(error='对话、图片或工程上下文无效，请检查后重试'),400
  with lock:
   for key in list(jobs):
    if jobs[key].get('finished',float('inf'))<time.time()-3600:jobs.pop(key,None)
   if sum(j['status'] in ('queued','running') for j in jobs.values())>=8:return jsonify(error='任务队列已满（2个执行、最多6个等待），请稍后提交'),409
   ident=uuid.uuid4().hex;jobs[ident]={'mode':'assistant','status':'queued','progress':0,'message':'准备对话…','cancel':threading.Event()}
  try:pool.submit(work,ident,body,split)
  except Exception:
   with lock:jobs.pop(ident,None)
   return jsonify(error='对话未能启动，工程未修改'),503
  return jsonify(id=ident),202
