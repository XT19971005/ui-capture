"""User-selected phases resume a bound plan, without repeating completed requests."""
import copy,hashlib,json,math
from design_properties import design_fields,mask

def kind(layer):
 t=layer.get('layerType','image')
 return 'vector' if t in ('path','rect','ellipse') else 'text' if t=='text' else 'image'

def token(body):
 value={'source':hashlib.sha256(str(body.get('image','')).encode()).hexdigest(),'width':body.get('width'),'height':body.get('height'),'layers':body.get('layers'),'annotations':body.get('annotations')}
 return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def validate_completed(body,stamp):
 stage=body.get('stage','all')
 if stage not in ('all','vector','text','image'):raise ValueError('请选择矢量、文字、图片或全部阶段')
 limit=body.get('imageLimit',0)
 if type(limit) is not int or not 0<=limit<=128:raise ValueError('每次生图数量无效')
 completed=body.get('completed',[])
 if not isinstance(completed,list) or len(completed)>len(body['layers']):raise ValueError('阶段已完成清单无效')
 seen=set();ids=set()
 for node in completed:
  if not isinstance(node,dict):raise ValueError('阶段结果无效')
  i=node.get('_generationPlanIndex')
  if type(i) is not int or not 0<=i<len(body['layers']) or i in seen or node.get('_generationPlanToken')!=stamp:raise ValueError('阶段结果与当前原图或分层清单不匹配，未重发生成')
  seen.add(i);layer=body['layers'][i]
  if not isinstance(node.get('id'),str) or not node['id'] or node['id'] in ids or node.get('name')!=layer['name']:raise ValueError('阶段图层身份不匹配')
  ids.add(node['id']);expected=layer.get('layerType','image')
  if node.get('type')!=expected and not (layer.get('reuseOf') is not None and kind(layer)=='vector' and node.get('type')=='path'):raise ValueError('阶段图层类型不匹配')
  for k in ('x','y','width','height'):
   v=node.get(k)
   if type(v) not in (int,float) or not math.isfinite(v) or abs(v)>12000 or k in ('width','height') and v<=0:raise ValueError('阶段图层几何无效')
  if node['width']*node['height']>36000000:raise ValueError('阶段图层超过安全尺寸')
  design_fields(node)
  if node['type']=='path':mask({'type':'path',**{k:node[k] for k in ('x','y','width','height')},'d':node.get('d')})
  if node['type']=='image':
   from image_replace import _image
   with _image(node.get('src')):pass
  if layer.get('reuseOf') is not None and layer['reuseOf'] not in seen and not any(n.get('_generationPlanIndex')==layer['reuseOf'] for n in completed):raise ValueError('阶段实例缺少对应底稿')
 return copy.deepcopy(completed)

def groups(layers,nodes):
 by_index={n['_generationPlanIndex']:n['id'] for n in nodes};result=[];last=None
 for i,layer in enumerate(layers):
  name=layer.get('group','')
  if not name:last=None;continue
  if last is None or last['name']!=name:
   last={'id':'annotation-group-'+str(i),'name':name,'children':[]};result.append(last)
  if i in by_index:last['children'].append(by_index[i])
 return [g for g in result if g['children']]
