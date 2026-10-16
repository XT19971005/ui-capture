"""Validate model output at the scene boundary, without discarding bad objects."""
import re,copy,hashlib
from design_properties import number,mask,design_fields

def vector(row,width,height,index):
 if not isinstance(row,dict):raise ValueError('矢量第'+str(index+1)+'项不是对象')
 label=str(row.get('name') or '第'+str(index+1)+'项')+'('+str(row.get('id') or 'vector:'+str(index))+')'
 def fail(field,reason):raise ValueError('矢量「'+label+'」的 '+field+' '+reason)
 result=dict(row)
 if row.get('type') not in ('rect','ellipse','path'):fail('type','须为rect/ellipse/path')
 value=row.get('fill')
 if isinstance(value,str):
  value=value.strip()
  if re.fullmatch(r'#[0-9a-fA-F]{3}',value):value='#'+''.join(c*2 for c in value[1:])
  if re.fullmatch(r'#[0-9a-fA-F]{6}[fF]{2}',value):value=value[:7]
 if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):fail('fill','须为#RRGGBB；空心对象用完整轮廓和孔洞，不能用none/透明颜色代替')
 result['fill']=value.lower()
 for key,limit in [('x',width),('y',height),('width',width),('height',height)]:
  try:result[key]=number(row.get(key),.000001 if key in ('width','height') else 0,limit,key)
  except ValueError:fail(key,'不是画布内有效数值')
 if result['x']+result['width']>width or result['y']+result['height']>height:fail('box','超出原图')
 if 'radius' in row:
  try:result['radius']=number(row['radius'],0,6000,'radius')
  except ValueError:fail('radius','须为非负有限数值')
 if row['type']=='path':
  try:mask({'type':'path','enabled':True,'x':0,'y':0,'width':result['width'],'height':result['height'],'d':row.get('d')})
  except ValueError as exc:fail('d',str(exc))
 try:result.update(design_fields(row))
 except ValueError as exc:fail('style',str(exc))
 return result

def repair_scope(plan,error,canvas_size=None):
 """Only a failed field family may change; unrelated accepted values stay put."""
 scope={};geometry={'x','y','width','height','d'}
 for index,row in enumerate(plan.get('vectors',[])):
  if not isinstance(row,dict) or not isinstance(row.get('id'),str):continue
  label=str(row.get('name') or '第'+str(index+1)+'项')+'('+str(row.get('id') or 'vector:'+str(index))+')'
  prefix='矢量「'+label+'」的 '
  if error.startswith(prefix):
   field=error[len(prefix):].split(' ',1)[0]
   keys=geometry if field in geometry|{'box'} else ({'type','d'} if field=='type' else {field})
   if field=='style':
    keys=set()
    for key in ('gradient','layerStyle','displayMask'):
     try:design_fields({key:row.get(key)})
     except ValueError:keys.add(key)
   scope[('vectors',row['id'])]=keys
 for field in ('assets','texts','vectors'):
  for row in plan.get(field,[]):
   if error.startswith('图层 '+str(row.get('id') or row.get('name') or '')+' 的 z_index '):scope[(field,row['id'])]={'z_index'}
 if canvas_size:
  from engine import text_rows
  for row in plan.get('texts',[]):
   try:text_rows({**plan,'texts':[row]},*canvas_size)
   except ValueError:
    scope[('texts',row['id'])]={'box'} if row.get('text') else {'text','box'}
  if '素材框' in error or ('素材「' in error and '的 box ' in error):
   from planner import asset_box
   for index,row in enumerate(plan.get('assets',[])):
    try:asset_box(row,*canvas_size,canvas_size,index)
    except ValueError:scope[('assets',row['id'])]={'box'}
 for row in plan.get('groups',[]):
  if error.startswith('分组「'+str(row.get('name') or row['id'])+'」'):scope[('groups',row['id'])]={'children'}
 return scope


def merge_repair(plan,candidate,error,canvas_size=None):
 """Treat full-schema repair responses as ID-addressed patches, never snapshots."""
 if not isinstance(candidate,dict):raise ValueError('修正规划不是对象；原清单已保留')
 result=copy.deepcopy(plan);scope=repair_scope(plan,error,canvas_size)
 fields=('assets','texts','vectors','groups','text_corrections')
 for field in fields:
  old=plan.get(field,[]);rows=candidate.get(field,[])
  if not isinstance(old,list) or not isinstance(rows,list):raise ValueError('修正规划清单结构无效：'+field)
  original={};seen=set()
  for row in old:
   if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or row['id'] in original:raise ValueError('原规划ID命名空间无效，不能自动改写标识：'+field)
   original[row['id']]=row
  for row in rows:
   if not isinstance(row,dict) or row.get('id') not in original or row.get('id') in seen:raise ValueError('修正规划新增、重复或改写ID，原清单已保留：'+field)
   seen.add(row['id']);keys=scope.get((field,row['id']),set())
   target=next(item for item in result.get(field,[]) if item['id']==row['id'])
   for key in keys:
    if key in row:
     if key=='children':
      known={item.get('id') for field_name in fields for item in plan.get(field_name,[]) if isinstance(item,dict)}
      accepted=[ident for ident in target.get('children',[]) if ident in known]
      if not isinstance(row[key],list) or [ident for ident in row[key] if ident in accepted]!=accepted:raise ValueError('修正规划删除或重排了原分组有效引用')
     target[key]=copy.deepcopy(row[key])
 # Identity, ordering, inventory, semantic metadata and accepted values never
 # disappear just because the local correction used empty schema placeholders.
 warnings=result.setdefault('warnings',[])
 if any(key in candidate and candidate[key]!=plan.get(key,[]) for key in ('uiComponents','uiReuseGroups')):
  warning='局部规划修正中的辅助组件/复用重编未应用，保留原规划元数据。'
  if warning not in warnings:warnings.append(warning)
 proposal_warnings=candidate.get('warnings',[])
 if not isinstance(proposal_warnings,list):raise ValueError('修正规划warnings结构无效')
 for warning in proposal_warnings:
  if isinstance(warning,str) and warning not in warnings:warnings.append(warning)
 return result


class PlanAssemblyError(ValueError):
 def __init__(self,message,plan):
  super().__init__(message);self.plan=copy.deepcopy(plan)


def complete_art_text_assets(plan,canvas_size):
 """Materialize only an explicitly observed art-text object's missing asset."""
 art=plan.get('art_text_ids',[])
 if not art:return plan
 from engine import text_rows
 from planner import parse_plan,asset_box,layer_order
 import json
 rows=text_rows(plan,*canvas_size);by_id={row['id']:row for row in rows}
 if not isinstance(art,list) or len(art)>100 or len(set(art))!=len(art):raise PlanAssemblyError('艺术字来源ID结构无效，不能自动改变文字类型',plan)
 # Existing normalized owners follow exactly the same overlap contract as
 # link_art_text; no alternate grouping or logo-merging rule is introduced.
 assets=parse_plan(json.dumps(plan),*canvas_size,canvas_size)['assets']
 result=copy.deepcopy(plan);source_rows={row['id']:row for row in plan.get('texts',[])}
 occupied={row.get('id') for field in ('assets','texts','vectors','groups') for row in plan.get(field,[]) if isinstance(row,dict)}
 for ident in art:
  if ident not in by_id or ident not in source_rows:raise PlanAssemblyError('艺术字引用缺少精确有效原文案：'+str(ident),plan)
  row=by_id[ident];x,y,right,bottom=row['bbox'];area=(right-x)*(bottom-y)
  if any(a['kind']=='logo' and a.get('derivedFromArtTextId',ident)==ident and max(0,min(right,a['box'][2])-max(x,a['box'][0]))*max(0,min(bottom,a['box'][3])-max(y,a['box'][1]))/max(1,area)>=.5 for a in assets):continue
  original=source_rows[ident]
  if 'z_index' not in original:raise PlanAssemblyError('艺术字「'+row['text']+'」缺少已确认层序，不能自动建立素材',plan)
  style=design_fields(original);order=layer_order(original)
  base='art-text-'+hashlib.sha256(ident.encode('utf8')).hexdigest()[:24];asset_id=base;suffix=2
  while asset_id in occupied:asset_id=base+'-'+str(suffix);suffix+=1
  asset={'id':asset_id,'name':'艺术字「'+row['text']+'」','kind':'logo','entity_id':'','parent':None,'box':{'left':x,'top':y,'right':right,'bottom':bottom},'sourceTextParts':[ident],'derivedFromArtTextId':ident,**style,**order}
  try:box=asset_box(asset,*canvas_size,canvas_size)
  except ValueError as error:raise PlanAssemblyError('已识别艺术字无法安全补齐素材表示：'+str(error),plan) from error
  if len(result.get('assets',[]))>=120:raise PlanAssemblyError('艺术字补齐后独立素材超过120项，原清单已保留',plan)
  result.setdefault('assets',[]).append(asset);occupied.add(asset_id)
  assets.append({**asset,'box':box})
  warning='已依据明确艺术字来源「'+row['text']+'」补齐独立完整素材表示；保留原文案关联，尚须检查字形。'
  if warning not in result.setdefault('warnings',[]):result['warnings'].append(warning)
 return result


def assemble(plan,build,repair,cancelled,progress,canvas_size=None,normalize_groups=False):
 """Bounded repair preserves every inventoried item and unrelated valid value."""
 from ui_components import validate_sources,link_scene
 for attempt in range(3):
  if cancelled():raise InterruptedError('已取消')
  try:
   validate_sources(plan)
   if canvas_size is not None:plan=complete_art_text_assets(plan,canvas_size)
   if normalize_groups and plan.get('groups'):
    from plan_groups import normalize
    drawing_plan={**plan,'groups':[]}
    plan,scene=normalize(plan,build(drawing_plan))
   else:scene=build(plan)
   from group_quality import validate_planned_groups
   try:validate_planned_groups(plan,scene)
   except ValueError as error:raise PlanAssemblyError(str(error),plan) from error
   return plan,link_scene(scene,plan)
  except PlanAssemblyError:raise
  except ValueError as exc:
   if attempt==2:raise PlanAssemblyError('规划重分析后仍无效：'+str(exc),plan) from exc
   progress('正在修正规划：'+str(exc))
   if cancelled():raise InterruptedError('已取消')
   try:candidate=repair(copy.deepcopy(plan),str(exc))
   except InterruptedError:raise
   except Exception as repair_error:raise PlanAssemblyError('规划修正未完成：'+str(repair_error),plan) from repair_error
   try:plan=merge_repair(plan,candidate,str(exc),canvas_size)
   except ValueError as merge_error:raise PlanAssemblyError(str(merge_error)+'；原问题：'+str(exc),plan) from merge_error

def link_art_text(assets,rows,art_ids):
 for row in rows:
  if row['id'] not in art_ids:continue
  x,y,right,bottom=row['bbox'];area=(right-x)*(bottom-y);candidates=[]
  for a in assets:
   if a['kind']!='logo' or a.get('derivedFromArtTextId',row['id'])!=row['id']:continue
   ax,ay,ar,ab=a['box'];overlap=max(0,min(right,ar)-max(x,ax))*max(0,min(bottom,ab)-max(y,ay))
   if overlap/max(1,area)>=.5:candidates.append((overlap/max(1,area),a))
  if not candidates:raise ValueError('艺术字「'+row['text']+'」缺少对应完整素材')
  owner=max(candidates,key=lambda pair:pair[0])[1]
  owner.setdefault('sourceTextParts',[]).append(row['id'])
