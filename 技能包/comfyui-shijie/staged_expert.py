"""One-pass staged planning. No API calls, retries, model downloads or execution."""
import json,math,copy
try:
 from .component_expert import bind_plan
 from .knowledge_store import verify_ack
except ImportError:
 from component_expert import bind_plan
 from knowledge_store import verify_ack

BUCKETS=('containers','images','vectors','texts')

def read_object(text):
 """Only remove provably unmatched extra object closers, never invent values."""
 if not isinstance(text,str) or len(text)>1000000:raise ValueError('回复无效或过长')
 s=text.strip()
 if s.startswith('```'):
  lines=s.splitlines();s='\n'.join(lines[1:-1]).strip() if lines[-1].strip()=='```' else s
 try:return json.loads(s),[]
 except ValueError:pass
 stack=[];quoted=False;escape=False;out=[];changes=[]
 for i,ch in enumerate(s):
  if quoted:
   out.append(ch)
   if escape:escape=False
   elif ch=='\\':escape=True
   elif ch=='"':quoted=False
   continue
  if ch=='"':quoted=True
  elif ch in '{[':stack.append(ch)
  elif ch in '}]':
   expected='{' if ch=='}' else '['
   if not stack or stack[-1]!=expected:
    if ch=='}' and stack and stack[-1]=='[' and out and out[-1]=='}':
     changes.append(dict(operation='remove_unmatched_extra_object_closer',offset=i));continue
    raise ValueError('JSON括号不匹配；禁止猜测补值')
   stack.pop()
  out.append(ch)
 try:value=json.loads(''.join(out))
 except ValueError as exc:raise ValueError('JSON格式错误；未猜测缺失引号或内容') from exc
 return value,changes

def _inventory(reply,rgb,knowledge):
 v,changes=read_object(reply);verify_ack(v,knowledge);h,w=rgb.shape[:2]
 if (v.get('width'),v.get('height'))!=(w,h):raise ValueError('分类画板尺寸不符')
 items=v.get('items')
 if not isinstance(items,list) or not 1<=len(items)<=256:raise ValueError('分类清单应为1至256项')
 ids=set()
 for r in items:
  if not isinstance(r,dict) or not isinstance(r.get('id'),str) or not r['id'] or r['id'] in ids:raise ValueError('分类ID缺失或重复')
  ids.add(r['id'])
  if r.get('bucket') not in BUCKETS or not isinstance(r.get('name'),str) or not r['name']:raise ValueError('分类类型或名称错误')
 for r in items:
  seen={r['id']};parent=r.get('parent_id')
  while parent is not None:
   if parent not in ids:raise ValueError('分类引用未知父层')
   if parent in seen:raise ValueError('父子引用循环')
   seen.add(parent);parent=next(a for a in items if a['id']==parent).get('parent_id')
 if not isinstance(v.get('background_prompt'),str) or not v['background_prompt'].strip():raise ValueError('缺少独立环境背景指令')
 return v,changes

def _header(rgb,knowledge):
 h,w=rgb.shape[:2]
 return '读取file附件全部13份QP规范，观察本次image。实际width='+str(w)+',height='+str(h)+'。知识回执原样返回：'+json.dumps(knowledge['receipt'],ensure_ascii=False)+'。只输出严格JSON，不输出代码或解释；无自动重试。'

def inventory_request(rgb,knowledge):
 return _header(rgb,knowledge)+'''\n阶段1仅识别分类，不输出坐标、路径、字体或执行参数。输出对象 {"width":实际宽,"height":实际高,"knowledge_ack":上述回执,"background_prompt":"英文干净环境背景指令，清除全部UI","items":[{"id":"稳定英文ID","name":"中文素材名","bucket":"containers/images/vectors/texts之一","parent_id":所属父容器ID或null,"group":"中文功能分组"}]}。按原画布从后到前排列items，父容器先于子层。containers是有材质的底板/框/轨道及填充，images是完整角色/图片/纹理装饰，vectors是纯色图标与几何，texts是每处普通文字和独立数字。背景由独立分支负责，不重复登记全画布环境背景。父容器与子内容分开登记：纸张、按钮底稿、图标、文字、进度轨道、填充、数值各有明确职责；同款每处独立ID。覆盖所有区域和小项，不能只列大块，不固定层数。'''

def branch_request(rgb,knowledge,bucket,inventory_reply):
 if bucket not in BUCKETS:raise ValueError('未知规划分支')
 inv,_=_inventory(inventory_reply,rgb,knowledge)
 assigned=[r for r in inv['items'] if r['bucket']==bucket]
 instructions={
  'containers':'材质容器必须edited，用英文prompt明确保留本体纸纹/光照/自然边缘并清除全部已登记子层。含数字的徽章去数字，轨道清除填充及数值，按钮去图标文字。独立填充可source且clear_boxes去数字，不能重复留轨道。',
  'images':'只处理完整图片或装饰，优先biref完整抠图，或source配精确polygon/radius/ellipse。不能将纸底与图标一块截图。遮挡缺失明确warnings，不谎称恢复。',
  'vectors':'只用shape或solid。shape须color RGB数组及tolerance建议35—60，按原图提取完整孔洞和细笔画；solid用于明确规则纯色圆/圆角/多边形。保留原风格，不把手绘纹理抹平。',
  'texts':'只用text，text为实际准确文字，color为RGB数组。按原图框布局，不自行编文案，不返回当前执行器不支持的字体样式字段。'
 }[bucket]
 return _header(rgb,knowledge)+'\n阶段2仅规划'+bucket+'，不重新做分类、不规划其他分支。'+instructions+'''\n只输出 {"assets":[...],"warnings":[]}。逐项严格沿用以下assigned的id，不增删。每项扁平字段：{"id":"原ID","box":[left,top,right,bottom],"method":"text","text":"实际文字","color":[255,255,255]}（示例只表示格式，method必须字符串，按本分支选择）。method实际允许edited/source/biref/shape/solid/text；edited需prompt英文，shape/solid/text需color整数数组；text需text。可选polygon/holes使用原图全局像素点，ellipse布尔，radius非负，clear_boxes只在本box内。禁止method嵌套对象、RGB对象或可执行代码。程序负责统一层序、父子关系、功能组及轮廓裁图框，无需返回z或group。有polygon时程序根据完整原始轮廓计算box，不改路径；全部点须在原画布内。\nassigned='''+json.dumps(assigned,ensure_ascii=False)+'\n必要关系上下文='+json.dumps([r for r in inv['items'] if r['id'] in {a.get('parent_id') for a in assigned} or r.get('parent_id') in {a['id'] for a in assigned}],ensure_ascii=False)

def merge_stages(rgb,knowledge,inventory_reply,**replies):
 inv,changes=_inventory(inventory_reply,rgb,knowledge);h,w=rgb.shape[:2];allrows={};diagnostics=[dict(stage='inventory',changes=changes)]
 warnings=[]
 for bucket in BUCKETS:
  v,fixes=read_object(replies[bucket]);diagnostics.append(dict(stage=bucket,changes=fixes))
  rows=v.get('assets')
  if not isinstance(rows,list):raise ValueError('分支缺少assets：'+bucket)
  allowed={r['id'] for r in inv['items'] if r['bucket']==bucket}
  for source in rows:
   r=copy.deepcopy(source)
   if not isinstance(r,dict) or r.get('id') not in allowed or r['id'] in allrows:raise ValueError('跨分支、未知或重复素材ID')
   m=r.get('method')
   if isinstance(m,dict):
    for k,val in m.items():
     if k=='type':continue
     if k in r and r[k]!=val:raise ValueError('嵌套方法字段冲突')
     r[k]=val
    r['method']=m.get('type');diagnostics.append(dict(id=r['id'],operation='flatten_explicit_method_fields'))
   if isinstance(r.get('color'),dict) and set(r['color'])=={'r','g','b'}:
    r['color']=[r['color'][k] for k in ('r','g','b')];diagnostics.append(dict(id=r['id'],operation='RGB_object_to_array'))
   if bucket=='texts' and r['method']!='text':raise ValueError('文字分支方法错误')
   if bucket=='vectors' and r['method'] not in ('shape','solid'):raise ValueError('纯色分支必须原生矢量')
   points=r.get('polygon')
   if points:
    if not isinstance(points,list) or len(points)<3 or any(not isinstance(p,list) or len(p)!=2 or any(type(n)not in (int,float) or not math.isfinite(n) for n in p) for p in points):raise ValueError('无效路径')
    if any(not 0<=a<=w or not 0<=b<=h for a,b in points):raise ValueError('路径越画板；拒绝钳制')
    box=[math.floor(min(p[0] for p in points)),math.floor(min(p[1] for p in points)),math.ceil(max(p[0] for p in points)),math.ceil(max(p[1] for p in points))]
    if r.get('box')!=box:diagnostics.append(dict(id=r['id'],operation='derive_crop_from_unchanged_polygon',before=r.get('box'),after=box))
    r['box']=box
   allrows[r['id']]=r
  warnings.extend(v.get('warnings',[]))
 if set(allrows)!={r['id'] for r in inv['items']}:raise ValueError('分支素材缺失；不允许丢件后执行')
 result=[]
 for z,item in enumerate(inv['items']):
  r=allrows[item['id']];children=[c['name'] for c in inv['items'] if c.get('parent_id')==item['id']]
  if children:
   if r['method']=='solid':
    # Solid is rendered afresh from geometry, so no source child pixels survive.
    diagnostics.append(dict(id=item['id'],operation='solid_parent_rebuilt_without_source_children'))
   elif r['method']=='edited':
    r['prompt']=r.get('prompt','')+' Remove every separately registered child; keep only the clean parent surface. Child inventory: '+', '.join(children)+'. No duplicate text, icon, fill or control remains.'
   else:raise ValueError('父容器含独立子层但未使用去子层任务：'+item['id'])
  r.update(name=item['name'],group=item.get('group',''),z=z,parent_id=item.get('parent_id'));result.append(r)
 plan=dict(width=w,height=h,knowledge_ack=inv['knowledge_ack'],background_prompt=inv['background_prompt'],assets=result,warnings=warnings,pending_requirements=['所有素材及整图视觉验收尚未完成；不自动重试或返修'])
 plan=bind_plan(json.dumps(plan,ensure_ascii=False),rgb,knowledge)
 plan.update(staged_diagnostics=diagnostics,run_policy=dict(maximum_generation_runs=1,automatic_retry=False),planning_architecture='inventory_then_four_specialists_then_merge')
 return plan
