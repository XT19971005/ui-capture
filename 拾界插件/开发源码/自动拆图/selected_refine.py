"""Explicit selected-layer check and bounded repair. No automatic PSD export."""
import base64,copy,hashlib,time
from pathlib import Path

def validate_selection(scene,ids):
 if not isinstance(scene,dict) or not isinstance(ids,list) or not ids or len(ids)>700 or any(not isinstance(i,str) or not i or len(i)>160 for i in ids) or len(set(ids))!=len(ids):raise ValueError('请选择要检查的图层')
 known={n['id'] for n in scene.get('nodes',[])}
 if not set(ids)<=known:raise ValueError('选中图层不存在')
 return set(ids)

def process(source,title,progress,cancelled,original_source=None,on_scene=lambda scene:None,resume_scene=None,selected_ids=None):
 from session_outputs import run_temporary
 from codex_client import CLIENT
 def generate(home):
  try:return _process(source,title,progress,cancelled,original_source or source,home,resume_scene,selected_ids)
  finally:
   for _ in range(60):
    if CLIENT.close():break
    time.sleep(.05)
   else:raise RuntimeError('选中项请求尚未结束，保留原工程')
 return run_temporary(generate)

def _process(source,title,progress,cancelled,original_source,home,resume_scene,selected_ids):
 from engine import load_source
 from acceptance import review_asset
 from incremental_assets import extract_once,check_resume_native,effective_locked_ids
 ids=validate_selection(resume_scene,selected_ids)
 scene=copy.deepcopy(resume_scene);original_scene=copy.deepcopy(scene);im=load_source(source)
 if im.size!=(scene.get('width'),scene.get('height')):raise ValueError('选中项原图尺寸不一致')
 if source!=(scene.get('comparisonSource') or scene.get('source')):raise ValueError('选中项原图来源不一致')
 load_source(original_source)
 raw=base64.b64decode(original_source.split(',',1)[1],validate=True);source_sha=hashlib.sha256(raw).hexdigest()
 recorded=scene.get('recognition',{}).get('sourceOriginalSHA256')
 if recorded and recorded!=source_sha:raise ValueError('选中项原文件来源不一致')
 folder=Path(home)/'选中项修正';assets=folder/'素材';structure=folder/'结构'
 assets.mkdir(parents=True);structure.mkdir()
 work=structure/'工作原图.png';work.write_bytes(base64.b64decode(source.split(',',1)[1],validate=True))
 original=structure/'原文件.png';original.write_bytes(raw)
 inherited_locked=effective_locked_ids(scene)
 selected=[n for n in scene['nodes'] if n['id'] in ids and n['id'] not in inherited_locked]
 if not selected:raise ValueError('选中图层已锁定，请先解锁')
 total=len(selected);notes=[];changed=[];checked=[]
 for index,n in enumerate(selected):
  if cancelled():raise InterruptedError('已取消')
  progress(.05+.75*index/total,'正在检查选中项：'+n['name'])
  if n['type']!='image':continue
  try:quality=review_asset(work,n,structure,cancelled,on_status=lambda m:progress(.05+.75*index/total,m))
  except InterruptedError:raise
  except Exception as error:
   n.update(assetReviewStatus='NEEDS_REVIEW',review=True,reviewIssue='检查未完成，保留原素材：'+str(error)[:200]);notes.append(n['name']+'：'+n['reviewIssue']);continue
  checked.append(n['id'])
  if quality.get('status')=='PASS':
   n.update(assetReviewStatus='PASS',review=False);n.pop('reviewIssue',None);continue
  issues=quality.get('issues',[]) or ['选中素材存在需要修正的问题'];n['_repairNotes']=issues
  progress(.1+.75*index/total,'正在修正选中项：'+n['name'])
  if n.get('assetKind')=='background':
   from workflow_assets import complete_background
   holder={**scene,'nodes':[copy.deepcopy(n),*[copy.deepcopy(x) for x in scene['nodes'] if x['id']!=n['id']]]}
   try:
    complete_background(work,holder,assets,structure,cancelled,original_source=original,force_repair=True,on_status=lambda m:progress(.1+.75*index/total,m))
    candidate={**holder['nodes'][0],'id':n['id'],'assetReviewStatus':'NOT_REVIEWED','review':True}
    from incremental_assets import remember_record
    remember_record(candidate,structure,True)
   except InterruptedError:raise
   except Exception as error:candidate={**n,'provenance':'source-crop-fallback','reviewIssue':str(error)[:200]}
  else:candidate=extract_once(work,n,assets,structure,cancelled,original,lambda m:progress(.1+.75*index/total,m))
  n.pop('_repairNotes',None)
  if candidate.get('provenance')=='source-crop-fallback':
   n.update(assetReviewStatus='NEEDS_REVIEW',review=True,reviewIssue='修正未完成，保留原素材：'+candidate.get('reviewIssue',''));notes.append(n['name']+'：'+n['reviewIssue']);continue
  candidate.pop('_repairNotes',None);scene['nodes'][scene['nodes'].index(n)]=candidate;changed.append(n['id'])
 native=[copy.deepcopy(n) for n in selected if n['type'] in ('text','rect','ellipse','path')]
 if native:
  progress(.82,'正在校正选中文字与简单图形…')
  subset={**scene,'nodes':native,'groups':[],'edges':[]}
  result=check_resume_native(work,subset,cancelled,lambda m:progress(.82,m))
  replacements={n['id']:n for n in result['nodes']}
  for index,n in enumerate(scene['nodes']):
   if n['id'] in replacements:
    if n!=replacements[n['id']]:changed.append(n['id'])
    scene['nodes'][index]=replacements[n['id']]
  notes.extend(result.get('recognition',{}).get('warnings',[]))
 if cancelled():raise InterruptedError('已取消')
 # Enforce the scope server-side as well as in the browser.
 for before,after in zip(original_scene['nodes'],scene['nodes']):
  if before['id']!=after['id'] or (before['id'] not in ids and before!=after):raise ValueError('选中修正触及了其他图层')
 for key in ('width','height','source','comparisonSource','originalSource','background','groups','edges','_partial'):
  if original_scene.get(key)!=scene.get(key):raise ValueError('选中修正更改了工程结构')
 for key in ('delivery','_sessionId','_projectId'):scene.pop(key,None)
 scene.setdefault('recognition',{})['selectedRefine']={'selectedIds':list(selected_ids),'checkedIds':checked,'changedIds':changed,'notes':notes,'status':'NEEDS_REVIEW' if notes else 'COMPLETED','repairedAssetsNotRechecked':bool(changed)}
 # A partial or previously unchecked whole document never becomes PASS.
 if changed or notes:
  for field in ('reviewStatus','status'):
   if scene['recognition'].get(field) in ('PASS','MANUAL_CONFIRMED'):scene['recognition'][field]='NEEDS_REVIEW' if notes else 'NOT_REVIEWED'
 progress(1,'选中项处理完成'+('，有项目需校对' if notes else ''))
 return scene
