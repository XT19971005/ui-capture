"""Explicit, atomic occlusion-order repair; never changes layer content or exports PSD."""
import base64,copy,hashlib,heapq,json,math,time
from pathlib import Path

CONFIDENCE=.9
SCHEMA={'type':'object','additionalProperties':False,'required':['relations','uncertain','notes'],'properties':{
 'relations':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['aboveId','belowId','confidence','evidence'],'properties':{'aboveId':{'type':'string'},'belowId':{'type':'string'},'confidence':{'type':'number','minimum':0,'maximum':1},'evidence':{'type':'string'}}}},
 'uncertain':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['firstId','secondId','reason'],'properties':{'firstId':{'type':'string'},'secondId':{'type':'string'},'reason':{'type':'string'}}}},
 'notes':{'type':'array','items':{'type':'string'}}}}


def hierarchy(scene):
 """Validate single ownership and an already contiguous bottom-to-top tree."""
 if not isinstance(scene,dict) or not isinstance(scene.get('nodes'),list) or not 1<=len(scene['nodes'])<=700:raise ValueError('当前工程没有可修复层级的图层')
 nodes=scene['nodes'];groups=scene.get('groups',[])
 if not isinstance(groups,list) or len(groups)>1400:raise ValueError('分组结构无效')
 entries={};owner={}
 for entry in [*nodes,*groups]:
  if not isinstance(entry,dict):raise ValueError('图层结构无效')
  ident=entry.get('id')
  if not isinstance(ident,str) or not ident or len(ident)>160 or ident in entries:raise ValueError('图层标识重复或无效')
  entries[ident]=entry
 group_map={g['id']:g for g in groups}
 for group in groups:
  children=group.get('children')
  if not isinstance(children,list) or not children or len(children)>2100:raise ValueError('分组成员无效')
  for ident in children:
   if not isinstance(ident,str) or ident not in entries or ident in owner or ident==group['id']:raise ValueError('分组归属重复或无效')
   owner[ident]=group['id']
 for ident in entries:
  seen=set();current=ident
  while current in owner:
   if current in seen:raise ValueError('分组循环引用')
   seen.add(current);current=owner[current]
 roots=[]
 for node in nodes:
  root=node['id']
  while root in owner:root=owner[root]
  if root not in roots:roots.append(root)
 children={None:roots,**{g['id']:list(g['children']) for g in groups}}
 def flatten(ident):
  if ident not in group_map:return [ident]
  return [leaf for child in children[ident] for leaf in flatten(child)]
 canonical=[leaf for root in roots for leaf in flatten(root)]
 if canonical!=[n['id'] for n in nodes]:raise ValueError('现有分组图层顺序不连续或与成员顺序不一致，请先整理分组')
 return entries,owner,children


def _validated_analysis(analysis,ids):
 if not isinstance(analysis,dict) or set(analysis)!={'relations','uncertain','notes'}:raise ValueError('层级分析返回结构无效')
 if any(not isinstance(analysis[k],list) or len(analysis[k])>10000 for k in ('relations','uncertain','notes')):raise ValueError('层级分析条目无效')
 if any(not isinstance(n,str) or not n.strip() or len(n)>1000 for n in analysis['notes']):raise ValueError('层级分析说明无效')
 seen=set()
 def pair(item,a,b,fields):
  if not isinstance(item,dict) or set(item)!=fields:raise ValueError('层级关系字段无效')
  left,right=item[a],item[b]
  if not isinstance(left,str) or not isinstance(right,str) or left not in ids or right not in ids or left==right:raise ValueError('层级关系包含未知或重复图层')
  key=(a,left,right)
  if key in seen:raise ValueError('层级关系重复')
  seen.add(key)
 for item in analysis['relations']:
  pair(item,'aboveId','belowId',{'aboveId','belowId','confidence','evidence'})
  score=item['confidence']
  if isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=1:raise ValueError('层级关系置信度无效')
  if not isinstance(item['evidence'],str) or not item['evidence'].strip() or len(item['evidence'])>2000:raise ValueError('层级关系缺少可核对的遮挡依据')
 for item in analysis['uncertain']:
  pair(item,'firstId','secondId',{'firstId','secondId','reason'})
  if not isinstance(item['reason'],str) or not item['reason'].strip() or len(item['reason'])>2000:raise ValueError('不确定层级缺少说明')


def apply_relations(original,analysis):
 """Constrain sibling branches at their common parent, then stable-sort each group."""
 from incremental_assets import effective_locked_ids
 entries,owner,children=hierarchy(original)
 ids=[n['id'] for n in original['nodes']];positions={ident:i for i,ident in enumerate(ids)}
 _validated_analysis(analysis,set(ids))
 scene=copy.deepcopy(original);notes=list(analysis['notes']);constraints={key:set() for key in children}
 def path(ident):
  result=[ident]
  while ident in owner:ident=owner[ident];result.append(ident)
  return list(reversed(result))
 def constrain(below,above):
  a,b=path(below),path(above);index=0
  while index<min(len(a),len(b)) and a[index]==b[index]:index+=1
  parent=a[index-1] if index else None
  constraints[parent].add((a[index],b[index]))
 def preserve(a,b):
  if positions[a]<positions[b]:constrain(a,b)
  else:constrain(b,a)
 for relation in analysis['relations']:
  above,below=relation['aboveId'],relation['belowId']
  a,b=entries[above],entries[below]
  overlap=max(a['x'],b['x'])<min(a['x']+a['width'],b['x']+b['width']) and max(a['y'],b['y'])<min(a['y']+a['height'],b['y']+b['height'])
  if not overlap:
   preserve(above,below);notes.append(above+' / '+below+'：图层边界无交叠，无法核实遮挡依据，保留原顺序。')
  elif relation['confidence']<CONFIDENCE:
   preserve(above,below);notes.append(above+' / '+below+'：遮挡置信度不足，保留原顺序。'+relation['evidence'])
  else:constrain(below,above)
 for relation in analysis['uncertain']:
  preserve(relation['firstId'],relation['secondId']);notes.append(relation['firstId']+' / '+relation['secondId']+'：保留原顺序。'+relation['reason'])
 locked=effective_locked_ids(original)
 for ident in ids:
  if ident in locked:
   for other in ids:
    if other!=ident:preserve(ident,other)
 sorted_children={};conflict=False
 for parent,siblings in children.items():
  rank={ident:index for index,ident in enumerate(siblings)};outgoing={ident:set() for ident in siblings};indegree={ident:0 for ident in siblings}
  for below,above in constraints[parent]:
   outgoing[below].add(above);indegree[above]+=1
  ready=[rank[ident] for ident in siblings if not indegree[ident]];heapq.heapify(ready);ordered=[]
  while ready:
   ident=siblings[heapq.heappop(ready)];ordered.append(ident)
   for above in outgoing[ident]:
    indegree[above]-=1
    if not indegree[above]:heapq.heappush(ready,rank[above])
  if len(ordered)!=len(siblings):conflict=True;break
  sorted_children[parent]=ordered
 changed=[];changed_groups=[]
 if conflict:notes.append('遮挡关系与其他关系、锁定图层或分组连续性存在冲突；本次未应用任何顺序修改，请人工核对。')
 else:
  groups={g['id']:g for g in scene.get('groups',[])}
  def flatten(ident):
   if ident not in groups:return [ident]
   return [leaf for child in sorted_children[ident] for leaf in flatten(child)]
  ordered=[leaf for root in sorted_children[None] for leaf in flatten(root)]
  by_id={n['id']:n for n in scene['nodes']};scene['nodes']=[by_id[ident] for ident in ordered]
  changed=[ident for ident in ids if positions[ident]!=ordered.index(ident)]
  for ident,group in groups.items():
   if group['children']!=sorted_children[ident]:group['children']=sorted_children[ident];changed_groups.append(ident)
 for key in ('delivery','_sessionId','_projectId'):scene.pop(key,None)
 report={'status':'NEEDS_REVIEW' if notes else 'COMPLETED','changedIds':changed,'changedGroupIds':changed_groups,'notes':notes,'relations':copy.deepcopy(analysis['relations']),'uncertain':copy.deepcopy(analysis['uncertain']),'applied':not conflict}
 scene.setdefault('recognition',{})['orderRepair']=report
 # Layer order analysis never certifies content or the whole document.
 if changed or changed_groups or notes:
  for key in ('reviewStatus','status'):
   if scene['recognition'].get(key) in ('PASS','MANUAL_CONFIRMED'):scene['recognition'][key]='NEEDS_REVIEW' if notes else 'NOT_REVIEWED'
 return scene


def process(source,title,progress,cancelled,original_source=None,on_scene=lambda scene:None,resume_scene=None):
 from session_outputs import run_temporary
 from codex_client import CLIENT
 def analyze(home):
  try:return _process(source,title,progress,cancelled,original_source or source,home,resume_scene)
  finally:
   for _ in range(60):
    if CLIENT.close():break
    time.sleep(.05)
   else:raise RuntimeError('层级分析尚未结束，保留原工程')
 return run_temporary(analyze)


def _process(source,title,progress,cancelled,original_source,home,resume_scene):
 from engine import load_source
 from codex_client import CLIENT
 hierarchy(resume_scene)
 if cancelled():raise InterruptedError('已取消')
 image=load_source(source)
 if image.size!=(resume_scene.get('width'),resume_scene.get('height')):raise ValueError('修复层级原图尺寸不一致')
 if source!=(resume_scene.get('comparisonSource') or resume_scene.get('source')):raise ValueError('修复层级原图来源不一致')
 load_source(original_source)
 raw=base64.b64decode(original_source.split(',',1)[1],validate=True);source_sha=hashlib.sha256(raw).hexdigest()
 recorded=resume_scene.get('recognition',{}).get('sourceOriginalSHA256')
 if recorded and recorded!=source_sha:raise ValueError('修复层级原文件来源不一致')
 stored_original=resume_scene.get('originalSource')
 if stored_original and stored_original!=original_source:raise ValueError('修复层级原文件来源不一致')
 if not recorded and not stored_original and original_source!=source:raise ValueError('旧工程缺少原文件校验信息，请使用工程中保存的原图修复层级')
 source_path=Path(home)/'层级原图.png';source_path.write_bytes(raw)
 fields=('id','name','type','x','y','width','height','text','sourceTextId','sourceAssetId','assetKind','visible','locked')
 manifest={'width':resume_scene['width'],'height':resume_scene['height'],'order':'bottom-to-top','nodes':[{key:n[key] for key in fields if key in n} for n in resume_scene['nodes']],'groups':[{key:g[key] for key in ('id','name','children','locked') if key in g} for g in resume_scene.get('groups',[])]}
 prompt='''依据附件原始图片的实际遮挡关系检查当前工程层级。只返回JSON，禁止生成或修改图片、文字、几何、蒙版、分组归属。工程清单的 nodes 和 groups.children 均为从底到顶。原图可能大于工程画布，请按比例识别清单中的位置。仅对原图中能明确判断交叠前后的图层对返回 relations；aboveId 为在上方遮住别人的图层，belowId 为被遮住的图层，confidence 为0到1，evidence 必须描述可核对的具体遮挡边缘。无交叠、单凭名称或常识不能推断，不要全量排列。不确定的候选关系放 uncertain（firstId、secondId、reason），保留原顺序。只引用 nodes 中的精确 id，不能引用分组id。锁定节点及锁定祖先下的图层不得跨越其他图层。分组必须整体连续，无法同时满足时在 notes 说明。此操作仅检查层级，不能声称工程或素材整体验收PASS。清单如下：\n'''+json.dumps(manifest,ensure_ascii=False)
 progress(.12,'正在依据原图分析遮挡关系…')
 analysis=CLIENT.analyze(prompt,[source_path],SCHEMA,cancelled=cancelled,on_status=lambda message:progress(.2,message))
 if cancelled():raise InterruptedError('已取消')
 result=apply_relations(resume_scene,analysis)
 if cancelled():raise InterruptedError('已取消')
 progress(1,'层级修复完成'+('，有关系需人工核对' if result['recognition']['orderRepair']['notes'] else ''))
 return result
