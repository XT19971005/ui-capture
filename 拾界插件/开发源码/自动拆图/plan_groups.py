"""Safe normalization of newly planned organizational groups only."""
import copy,hashlib
from design_properties import design_fields
from layer_order import hierarchy


def normalize(plan,scene):
 from plan_contract import PlanAssemblyError
 raw=plan.get('groups',[])
 if not isinstance(raw,list) or len(raw)>350:raise ValueError('分组规划数量无效')
 if not raw:return plan,scene
 nodes=scene['nodes'];positions={n['id']:i for i,n in enumerate(nodes)};aliases={}
 for n in nodes:
  for key in [n['id'],n.get('sourceAssetId'),n.get('sourceVectorId'),n.get('sourceTextId'),*n.get('sourceEntityParts',[]),*n.get('sourceTextParts',[])]:
   if key and n['id'] not in aliases.setdefault(key,[]):aliases[key].append(n['id'])
 groups={};order={}
 for index,g in enumerate(raw):
  if not isinstance(g,dict) or not isinstance(g.get('id'),str) or not g['id'] or len(g['id'])>160 or g['id'] in groups or g['id'] in aliases or not isinstance(g.get('children'),list) or not g['children']:raise ValueError('分组规划结构无效')
  groups[g['id']]=g;order[g['id']]=index
 resolved={};owner={}
 for ident,g in groups.items():
  children=[]
  for key in g['children']:
   if not isinstance(key,str) or key not in groups and key not in aliases:raise ValueError('分组「'+str(g.get('name') or ident)+'」包含未知成员 '+str(key))
   values=[key] if key in groups else aliases[key]
   for value in values:
    if value not in children:children.append(value)
  for value in children:
   if value==ident or value in owner:raise ValueError('分组归属重复或循环')
   owner[value]=ident
  resolved[ident]=children
 for ident in groups:
  seen=set();current=ident
  while current in owner:
   if current in seen:raise ValueError('分组循环引用')
   seen.add(current);current=owner[current]
 def pure(g):
  return g.get('layerStyle') is None and g.get('displayMask') is None and g.get('opacity',1)==1 and g.get('visible',True) is True and not g.get('hidden',False) and not g.get('locked',False) and g.get('blendMode','normal')=='normal' and not any(key in g for key in ('transform','x','y','width','height','rotation','mask','clipPath'))
 occupied=set(groups)|set(positions)|set(aliases);outputs=[];fragments={};bounds={};splits=[]
 def walk(ident):
  if ident not in groups:return [ident]
  if ident in fragments:return fragments[ident]
  g=groups[ident];design_fields(g);items=[]
  for child in resolved[ident]:items.extend(walk(child))
  items.sort(key=lambda child:bounds[child][0] if child in bounds else positions[child]);runs=[]
  for child in items:
   low,high=bounds[child] if child in bounds else (positions[child],positions[child])
   if not runs or low!=runs[-1][-1][2]+1:runs.append([])
   runs[-1].append((child,low,high))
  if len(runs)>1 and not pure(g):raise PlanAssemblyError('分组「'+str(g.get('name') or ident)+'」跨越交错图层且带有效果、蒙版或状态，不能自动拆开；原图层与清单已保留',plan)
  result=[]
  for index,run in enumerate(runs):
   key=ident
   if index:
    base='plan-group-'+hashlib.sha256(ident.encode('utf8')).hexdigest()[:24]+'-part-'+str(index+1);key=base;counter=2
    while key in occupied:key=base+'-'+str(counter);counter+=1
   occupied.add(key);children=[item[0] for item in run];group={**copy.deepcopy(g),'id':key,'children':children}
   if index:group['name']=str(g.get('name') or '分组')+' · '+str(index+1)
   outputs.append((order[ident],index,group));bounds[key]=(run[0][1],run[-1][2]);result.append(key)
  fragments[ident]=result
  if len(result)>1:splits.append({'sourceGroupId':ident,'groupIds':list(result),'originalChildren':copy.deepcopy(g['children'])})
  return result
 for ident in groups:walk(ident)
 actual=[group for _,_,group in sorted(outputs,key=lambda item:(item[0],item[1]))]
 if len(actual)>350:raise PlanAssemblyError('连续区段拆组后超过350组容量，不能截断原成员',plan)
 scene['groups']=actual;hierarchy(scene)
 # Source-based references keep the normalized plan reusable across fresh UUIDs.
 node_map={n['id']:n for n in nodes}
 def source(ident):
  if ident not in node_map:return ident
  n=node_map[ident]
  return n.get('sourceAssetId') or n.get('sourceVectorId') or n.get('sourceTextId') or ident
 result=copy.deepcopy(plan);result['groups']=[]
 for g in actual:
  source_children=list(dict.fromkeys(source(child) for child in g['children']))
  direct_nodes={child for child in g['children'] if child in node_map}
  expanded={ident for child in source_children if child in aliases for ident in aliases[child]}
  if expanded!=direct_nodes:raise PlanAssemblyError('连续拆组的源图层别名跨越区段，不能建立有歧义的续拆引用',plan)
  result['groups'].append({**copy.deepcopy(g),'children':source_children})
 if splits:
  note='自动规划中的纯组织组已按真实绘制顺序拆成连续区段；所有原图层、内容及层序保持不变。'
  if note not in result.setdefault('warnings',[]):result['warnings'].append(note)
  scene.setdefault('recognition',{})['autoGroupNormalization']={'status':'SPLIT_WITHOUT_PAINT_CHANGE','originalGroups':copy.deepcopy(raw),'splits':splits}
 return result,scene
