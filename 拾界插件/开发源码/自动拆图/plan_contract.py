"""Validate model output at the scene boundary, without discarding bad objects."""
import re
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

def assemble(plan,build,repair,cancelled,progress):
 """A malformed plan gets bounded analysis repair before any image generation."""
 for attempt in range(3):
  if cancelled():raise InterruptedError('已取消')
  try:return plan,build(plan)
  except ValueError as exc:
   if attempt==2:raise ValueError('规划重分析后仍无效：'+str(exc)) from exc
   progress('正在修正规划：'+str(exc))
   if cancelled():raise InterruptedError('已取消')
   plan=repair(plan,str(exc))

def link_art_text(assets,rows,art_ids):
 for row in rows:
  if row['id'] not in art_ids:continue
  x,y,right,bottom=row['bbox'];area=(right-x)*(bottom-y);candidates=[]
  for a in assets:
   if a['kind']!='logo':continue
   ax,ay,ar,ab=a['box'];overlap=max(0,min(right,ar)-max(x,ax))*max(0,min(bottom,ab)-max(y,ay))
   if overlap/max(1,area)>=.5:candidates.append((overlap/max(1,area),a))
  if not candidates:raise ValueError('艺术字「'+row['text']+'」缺少对应完整素材')
  owner=max(candidates,key=lambda pair:pair[0])[1]
  owner.setdefault('sourceTextParts',[]).append(row['id'])
