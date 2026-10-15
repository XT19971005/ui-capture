"""Observed UI anatomy, independent instances and explicit reuse candidates.

Semantic structure never imposes a design-system appearance, paint grouping,
editor lock or generated-pixel reuse. IDs refer to this one visual plan.
"""
import copy
from design_properties import obj

CATEGORIES=('button','toggle','input','selection','navigation','list','list_item','card','panel','dialog','feedback','progress','badge','unknown')
STATES=('unknown','default','selected','disabled','pressed','focused','loading','error','success')
SLOTS=('container','label','icon','leading','supporting','trailing','value','indicator','media','action','decoration')
IDENT={'type':'string','minLength':1,'maxLength':160}
COMPONENT=obj({'id':IDENT,'category':{'type':'string','enum':list(CATEGORIES)},'familyId':{'type':'string','maxLength':160},'variant':{'type':'string','maxLength':160},'observedState':{'type':'string','enum':list(STATES)},'parentId':{'type':['string','null']},'evidence':{'type':'string','minLength':1,'maxLength':1200},'slots':{'type':'array','maxItems':len(SLOTS),'items':obj({'role':{'type':'string','enum':list(SLOTS)},'nodeIds':{'type':'array','minItems':1,'maxItems':700,'items':IDENT}})}})
REUSE=obj({'id':IDENT,'kind':{'type':'string','enum':['asset','text_style']},'memberIds':{'type':'array','minItems':2,'maxItems':700,'items':IDENT},'evidence':{'type':'string','minLength':1,'maxLength':1200}})
PLAN_FIELDS={'uiComponents':{'type':'array','maxItems':350,'items':COMPONENT},'uiReuseGroups':{'type':'array','maxItems':350,'items':REUSE}}
UI_COMPONENT_RULES='仅在初扫规划时，按当前图片可观测的UI解剖登记uiComponents与uiReuseGroups，和assets/texts/vectors在同一次首扫返回，不逐组件另发诊断。类别包括动作button、双态toggle、输入input、选择selection、导航navigation、列表list及独立list_item、card、panel、dialog、反馈feedback、progress、badge与unknown；独立角色、道具、前景不因在界面内就强建UI组件，没有组件证据可填空数组。不确定类别用unknown并在evidence说明证据不足，不臆造交互或看不见的状态。每个实例独立id、familyId、variant、observedState、parentId、evidence、slots；只有真实可观察状态才能填default/selected/disabled/pressed/focused/loading/error/success，否则unknown。底板container、文案label、图标icon、前置leading、辅助说明supporting、后置trailing、输入值value、状态indicator、媒体media、动作action、装饰decoration按真实槽位分别引用本次assets/texts/vectors的精确id（nodeIds）；不存在的槽位不填，不为套模板补控件。每个叶层只归一个直接组件的一个槽位；父组件通过parentId包含子组件，不重复占用子组件叶层；语义组件树不强制成为绘制groups，不能压平图标/文字/底板或改变真实遮挡。assets/texts/vectors的id在整份规划中唯一；重复按钮、卡片、列表项必须各有独立对象与文案，不把多个实例合成一个实体。相同家族可记录同一familyId，状态和variant仍按各实例保留。uiReuseGroups仅是有观察证据的asset或text_style复用候选：memberIds引用独立实例的精确源图层id，至少两项，evidence说明轮廓/材质或文字样式的相同证据；不能仅凭同名、同类别或相邻位置判断可复用，asset不能混入普通文字，text_style只关联普通原生文字且不合并其内容。它们不授权复用生成像素或覆盖各实例字体参数。这里学习的是Material/Apple HIG/Fluent/Carbon的组件结构、状态与槽位知识，不复制其现代默认字体、配色、圆角、间距、阴影或尺寸；所有外观、文字与z_index仍依据原图。后续复核仅核对本次授权范围内已提供的组件与槽位，不要求返回新的组件清单，不因模板槽位可选就判缺层。'

def install_schema(schema):
 schema['properties'].update(copy.deepcopy(PLAN_FIELDS))
 for key in PLAN_FIELDS:
  if key not in schema['required']:schema['required'].append(key)


def _id(value,label):
 if not isinstance(value,str) or not value or len(value)>160:raise ValueError(label+'标识无效')
 return value


def _entries(value,label,limit=350):
 if not isinstance(value,list) or len(value)>limit:raise ValueError(label+'数量或结构无效')
 return value


def _evidence(value,label):
 if not isinstance(value,str) or not value.strip() or len(value)>1200:raise ValueError(label+'缺少观察证据或证据不足说明')


def validate_sources(plan):
 """Source namespaces belong to drawable planning, not optional UI metadata."""
 if 'uiComponents' not in plan and 'uiReuseGroups' not in plan:return None
 sources={};kinds={}
 for field in ('assets','texts','vectors'):
  for row in _entries(plan.get(field,[]),'源图层',700):
   if not isinstance(row,dict):raise ValueError('UI源图层结构无效')
   ident=_id(row.get('id'),'UI源图层')
   if ident in sources:raise ValueError('UI源图层ID命名空间重复：'+ident)
   sources[ident]=row;kinds[ident]=field
 return sources,kinds


def validate_plan(plan):
 """Strict validator: callers can reject unsafe auxiliary metadata explicitly."""
 source_plan=validate_sources(plan)
 if source_plan is None:return None
 sources,kinds=source_plan
 if not all(key in plan for key in PLAN_FIELDS):raise ValueError('UI组件规划须同时包含实例与复用候选数组')
 components=_entries(plan['uiComponents'],'UI组件');families={};by_id={};owned={}
 for component in components:
  if not isinstance(component,dict) or set(component)!=set(COMPONENT['properties']):raise ValueError('UI组件字段无效')
  ident=_id(component['id'],'UI组件')
  if ident in by_id:raise ValueError('UI组件实例ID重复')
  if component['category'] not in CATEGORIES or component['observedState'] not in STATES:raise ValueError('UI组件类别或可观察状态无效')
  for key in ('familyId','variant'):
   if not isinstance(component[key],str) or len(component[key])>160:raise ValueError('UI组件'+key+'无效')
  family=component['familyId']
  if family:
   if family in families and families[family]!=component['category']:raise ValueError('UI组件家族混用不同类别')
   families[family]=component['category']
  if component['parentId'] is not None:_id(component['parentId'],'UI父组件')
  _evidence(component['evidence'],'UI组件');seen_roles=set()
  for slot in _entries(component['slots'],'UI槽位',len(SLOTS)):
   if not isinstance(slot,dict) or set(slot)!={'role','nodeIds'} or slot['role'] not in SLOTS or slot['role'] in seen_roles:raise ValueError('UI槽位类别无效或重复')
   seen_roles.add(slot['role']);refs=_entries(slot['nodeIds'],'UI槽位引用',700)
   if not refs:raise ValueError('UI槽位引用为空')
   for ref in refs:
    _id(ref,'UI槽位引用')
    if ref not in sources:raise ValueError('UI槽位引用不存在的源图层：'+ref)
    if ref in owned:raise ValueError('UI槽位图层重复归属：'+ref)
    owned[ref]=(ident,slot['role'])
  by_id[ident]=component
 for ident,component in by_id.items():
  current=ident;seen=set()
  while current is not None:
   if current in seen:raise ValueError('UI父组件循环引用')
   if current not in by_id:raise ValueError('UI父组件引用不存在')
   seen.add(current);current=by_id[current]['parentId']
  if not component['slots'] and not any(c['parentId']==ident for c in components):raise ValueError('UI组件实例缺少可观察槽位或子组件')
 reuse=_entries(plan['uiReuseGroups'],'UI复用候选');seen=set();art=set(plan.get('art_text_ids',[]))
 for group in reuse:
  if not isinstance(group,dict) or set(group)!=set(REUSE['properties']):raise ValueError('UI复用候选字段无效')
  ident=_id(group['id'],'UI复用候选')
  if ident in seen or group['kind'] not in ('asset','text_style'):raise ValueError('UI复用候选ID重复或类型无效')
  seen.add(ident);_evidence(group['evidence'],'UI复用候选');members=_entries(group['memberIds'],'UI复用成员',700);unique=set()
  if len(members)<2:raise ValueError('UI复用候选至少需要两个独立成员')
  for ref in members:
   _id(ref,'UI复用成员')
   if ref in unique or ref not in sources:raise ValueError('UI复用成员重复或引用不存在')
   unique.add(ref)
   if group['kind']=='text_style' and (kinds[ref]!='texts' or ref in art):raise ValueError('文字style候选只能关联普通原生文字')
   if group['kind']=='asset' and kinds[ref]=='texts':raise ValueError('资产候选不能混入普通文字')
 return {'components':copy.deepcopy(components),'reuseGroups':copy.deepcopy(reuse),'sourceKinds':kinds,'sources':sources}


def _link_scene(scene,plan,strict=True):
 """Resolve semantic source IDs; preserve each actual node, state and appearance.

Continuation is allowed to carry intentionally deleted native objects. Their
links are marked unresolved; this function never recreates or regenerates them.
"""
 validated=validate_plan(plan)
 if validated is None:return scene
 current=[n for n in scene.get('nodes',[]) if not n.get('versionArchived')]
 by_id={n['id']:n for n in current};aliases={}
 for node in current:
  for key in ('sourceAssetId','sourceVectorId','sourceTextId'):
   if node.get(key):aliases.setdefault(node[key],set()).add(node['id'])
  for key in ('sourceEntityParts','sourceTextParts'):
   for source in node.get(key,[]):aliases.setdefault(source,set()).add(node['id'])
 positions={n['id']:i for i,n in enumerate(current)};partial=False
 def resolve(ref):
  nonlocal partial
  ids=sorted(aliases.get(ref,set()),key=positions.__getitem__)
  # Multicolour ink is the intentional one-to-many source mapping. Copies of
  # an ordinary bitmap or native text do not silently become the same instance.
  if len(ids)>1:
   rows=[by_id[i] for i in ids];colors=[n.get('sourceInkColor') or n.get('fill') for n in rows]
   ink_source=(validated['sourceKinds'][ref]=='assets' and validated['sources'][ref].get('kind')=='logo') or (validated['sourceKinds'][ref]=='texts' and ref in plan.get('art_text_ids',[]))
   multiple_ink=ink_source and all(n.get('type')=='path' for n in rows) and all(colors) and len(set(colors))==len(colors)
   if not multiple_ink:
    if strict:raise ValueError('UI源图层引用解析到多个非派生实例：'+ref)
    ids=[]
  if not ids:
   if strict:raise ValueError('UI源图层引用未对应实际图层：'+ref)
   partial=True
  return ids
 components=validated['components'];claimed={};ambiguous=set()
 for component in components:
  for slot in component['slots']:
   linked=[];missing=[]
   for ref in slot['nodeIds']:
    ids=resolve(ref)
    if not ids:missing.append(ref)
    for ident in ids:
     owner=(component['id'],slot['role'])
     if ident in claimed and claimed[ident]!=owner:
      if strict:raise ValueError('不同UI组件实例或槽位解析到同一图层，不能合并实例')
      ambiguous.add(ident);partial=True
     claimed[ident]=owner
     if ident not in linked:linked.append(ident)
   slot.update(sceneNodeIds=linked,unresolvedSourceIds=missing)
 if ambiguous:
  for component in components:
   for slot in component['slots']:
    slot['sceneNodeIds']=[ident for ident in slot['sceneNodeIds'] if ident not in ambiguous]
    slot['unresolvedSourceIds']=list(dict.fromkeys([*slot['unresolvedSourceIds'],*[ref for ref in slot['nodeIds'] if aliases.get(ref,set())&ambiguous]]))
 groups=validated['reuseGroups']
 for group in groups:
  linked=[];missing=[];members={};collisions=set()
  for ref in group['memberIds']:
   ids=[ident for ident in resolve(ref) if ident not in ambiguous]
   if group['kind']=='text_style' and any(by_id[i].get('type')!='text' for i in ids):
    if strict:raise ValueError('文字style候选未对应原生文字图层')
    ids=[];partial=True
   if not ids:missing.append(ref)
   for ident in ids:
    if ident in members and members[ident]!=ref:collisions.add(ident)
    members[ident]=ref
    if ident not in linked:linked.append(ident)
  if collisions:
   if strict:raise ValueError('UI复用候选成员未保留独立图层，不能把同一实体当重复实例')
   partial=True;linked=[ident for ident in linked if ident not in collisions]
   missing=list(dict.fromkeys([*missing,*[ref for ref in group['memberIds'] if aliases.get(ref,set())&collisions]]))
  group.update(sceneNodeIds=linked,unresolvedSourceIds=missing,status='CANDIDATE_NOT_APPLIED')
 scene.setdefault('recognition',{})['uiStructure']={'version':1,'basis':'single_visual_plan','linkStatus':'PARTIAL' if partial else 'RESOLVED','reuseStatus':'PLANNED_NOT_APPLIED','components':components,'reuseGroups':groups}
 return scene


def link_scene(scene,plan,strict=True):
 """Quarantine invalid optional semantics without retrying paid drawing plans.

 Source namespace errors still propagate to the bounded drawing-plan repair.
 The strict validator remains available; no rejected slot or hierarchy is used.
 """
 validate_sources(plan)
 try:return _link_scene(scene,plan,strict)
 except ValueError as exc:
  warning='UI组件/复用元数据未应用，需复核：'+str(exc)
  warnings=plan.setdefault('warnings',[])
  if warning not in warnings:warnings.append(warning)
  recognition=scene.setdefault('recognition',{})
  notes=recognition.setdefault('warnings',[])
  if warning not in notes:notes.append(warning)
  recognition['uiStructure']={'version':1,'basis':'single_visual_plan','linkStatus':'NEEDS_REVIEW','metadataStatus':'INVALID_METADATA','reuseStatus':'PLANNED_NOT_APPLIED','components':[],'reuseGroups':[],'warnings':[warning],'invalidMetadata':{key:copy.deepcopy(plan[key]) for key in PLAN_FIELDS if key in plan}}
  return scene
