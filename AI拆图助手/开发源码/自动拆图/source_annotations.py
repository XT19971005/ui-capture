"""Vector guide marks bound to a clean source. Never used as output pixels/masks."""
import copy,hashlib,math,json,re
from PIL import Image,ImageDraw

COLORS=('#ffdf24','#ff5c87','#39d8ff','#a78bfa','#ff9838','#6bf08c')

def validate(state,source,width,height):
 if state is None:return None
 if not isinstance(state,dict) or set(state)-{'version','width','height','sourceHash','items','order','preserve','allowExpand'} or state.get('version')!=1:raise ValueError('原画标注格式无效')
 if state.get('width')!=width or state.get('height')!=height or state.get('sourceHash')!=hashlib.sha256(source.encode('utf8')).hexdigest():raise ValueError('原图已变化，请重新确认原画标注')
 if 'preserve' in state and (not isinstance(state['preserve'],str) or len(state['preserve'])>2000):raise ValueError('保留要求无效或超过2000字')
 if 'allowExpand' in state and not isinstance(state['allowExpand'],bool):raise ValueError('向外补全选项无效')
 items=state.get('items');colors=set();strokes=points=0;counts={}
 if not isinstance(items,list) or len(items)>32:raise ValueError('原画标注最多32个标注对象')
 for item in items:
  if not isinstance(item,dict) or (set(item)-{'color','label','strokes','purpose'} or not {'color','label','strokes'}<=set(item)) or not isinstance(item['color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',item['color']) or item['color'] in colors:raise ValueError('原画标注颜色无效')
  if item.get('purpose','keep') not in ('keep','remove'):raise ValueError('标注用途仅支持保留或删除')
  colors.add(item['color'])
  if not isinstance(item['label'],str) or len(item['label'])>100:raise ValueError('原画标注名称超过100字')
  if not isinstance(item['strokes'],list):raise ValueError('原画笔迹无效')
  counts[item['color']]=len(item['strokes'])
  for stroke in item['strokes']:
   strokes+=1
   if not isinstance(stroke,list) or not 2<=len(stroke)<=512:raise ValueError('每笔需要2至512个有效坐标')
   for p in stroke:
    points+=1
    if not isinstance(p,list) or len(p)!=2 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in p) or not 0<=p[0]<=width or not 0<=p[1]<=height:raise ValueError('原画标注坐标超出原图')
 if strokes>64 or points>12000:raise ValueError('原画标注过多，请简化到64笔以内')
 if 'order' in state:
  order=state['order']
  if not isinstance(order,list) or len(order)!=strokes or any(not isinstance(c,str) or c not in colors for c in order) or any(order.count(c)!=n for c,n in counts.items()):raise ValueError('原画笔迹历史无效')
 return copy.deepcopy(state)

def render(state,source,target):
 with Image.open(source) as original:canvas=original.convert('RGB').resize((int(state['width']),int(state['height'])))
 draw=ImageDraw.Draw(canvas);width=max(2,round(max(canvas.size)*.009))
 for item in state['items']:
  for stroke in item['strokes']:
   pts=[tuple(p) for p in stroke];draw.line(pts,fill=item['color'],width=width,joint='curve')
   for x,y in (pts[0],pts[-1]):draw.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=item['color'])
 canvas.save(target);canvas.close();return target

def summary(state):
 return [{'color':i['color'],'name':i['label'] or '未命名标注','purpose':i.get('purpose','keep'),'strokes':i['strokes']} for i in state['items'] if i['strokes']]

def install(state,source,structure):
 if state and any(i['strokes'] for i in state['items']):
  render(state,source,structure/'用户原画标注.png')
  (structure/'用户原画标注.json').write_text(json.dumps(summary(state),ensure_ascii=False),'utf8')

def append_reference(prompt,images,structure):
 guide=structure/'用户原画标注.png';info=structure/'用户原画标注.json'
 if guide.is_file() and info.is_file():
  return prompt+'\n新增最后一张是完整原图的用户彩笔标注。'+RULES+'\n颜色说明：'+info.read_text('utf8')[:24000],[*images,guide]
 return prompt,images

RULES='标注purpose=remove表示要删除，keep表示保留；未指定用途默认保留。'+ '彩色笔迹是用户在原画上大致标出的对象/遮挡后轮廓示意，不是原画内容、不是需要生成的线、不是硬裁剪蒙版。结合颜色名称及用户说明区分对象，保持用户明确指出的尖角、凹口、完整轮廓和遮挡关系；不要把星形/异形底稿简化成普通菱形。不要将笔迹颜色、标签或彩边画入最终素材。不同颜色通常表示不同实体，未标区域仍以干净原图为准；含糊时先澄清。'

REMOVAL_RULES='每个颜色的purpose明确指定keep保留或remove删除；颜色本身不代表用途。删除对象全部去掉，保留对象完整保留，只补真正遮挡区域；交叠手指和袖口必须按实体归属区分。空白处透明，禁止涂背景、残留删除对象或标线；提示词不代表像素锁定已经实现。'
