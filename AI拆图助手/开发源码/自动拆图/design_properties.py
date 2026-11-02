"""Validated visual planning fields shared by all automatic scene stages."""
import copy,math,re,uuid

def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
def nullable(value):return {'anyOf':[value,{'type':'null'}]}
NUMBER={'type':'number'};BOOL={'type':'boolean'};COLOR={'type':'string','pattern':'^#[0-9a-fA-F]{6}$'}
GRADIENT=obj({'kind':{'type':'string','enum':['linear','radial']},'angle':NUMBER,'scale':NUMBER,'stops':{'type':'array','minItems':2,'maxItems':8,'items':{'type':'array','minItems':2,'maxItems':2,'items':{'anyOf':[NUMBER,COLOR]}}}})
FX={'enabled':BOOL,'opacity':NUMBER,'color':COLOR}
STYLE=obj({'enabled':BOOL,'blendMode':{'type':'string','enum':['normal','multiply','screen','overlay']},
 'stroke':nullable(obj({**FX,'size':NUMBER,'position':{'type':'string','enum':['outside','inside','center']}})),
 **{k:nullable(obj({**FX,'size':NUMBER,'angle':NUMBER,'distance':NUMBER})) for k in ['dropShadow','innerShadow']},
 **{k:nullable(obj({**FX,'size':NUMBER})) for k in ['outerGlow','innerGlow']},
 'colorOverlay':nullable(obj(FX)),
 'gradientOverlay':nullable(obj({**GRADIENT['properties'],'enabled':BOOL,'opacity':NUMBER}))})
MASK=obj({'enabled':BOOL,'type':{'type':'string','enum':['rect','ellipse','path']},'x':NUMBER,'y':NUMBER,'width':NUMBER,'height':NUMBER,'d':{'type':'string'}})
FIELDS={'gradient':nullable(GRADIENT),'layerStyle':nullable(STYLE),'displayMask':nullable(MASK)}
GROUP=obj({'id':{'type':'string'},'name':{'type':'string'},'children':{'type':'array','maxItems':700,'items':{'type':'string'}},'layerStyle':nullable(STYLE),'displayMask':nullable(MASK)})

def number(value,low,high,label):
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError(label+'数值无效')
 return value
def color(value):
 if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):raise ValueError('样式颜色无效')
 return value.lower()
def switch(value,label):
 if not isinstance(value,bool):raise ValueError(label+'开关无效')
 return value
def gradient(g):
 if not isinstance(g,dict) or g.get('kind','linear') not in ['linear','radial']:raise ValueError('渐变类型无效')
 stops=g.get('stops');last=-1;out=[]
 if not isinstance(stops,list) or not 2<=len(stops)<=8:raise ValueError('渐变色标无效')
 for s in stops:
  if not isinstance(s,list) or len(s)!=2:raise ValueError('渐变色标无效')
  t=number(s[0],0,1,'渐变色标')
  if t<last:raise ValueError('渐变色标顺序无效')
  last=t;out.append([t,color(s[1])])
 return {'kind':g.get('kind','linear'),'angle':number(g.get('angle',0),-360,360,'渐变角度'),'scale':number(g.get('scale',1),.01,10,'渐变缩放'),'stops':out}
def style(s):
 if not isinstance(s,dict) or s.get('blendMode','normal') not in ['normal','multiply','screen','overlay']:raise ValueError('图层样式无效')
 result={'enabled':switch(s.get('enabled',True),'图层样式'),'blendMode':s.get('blendMode','normal')}
 for k in ['stroke','dropShadow','innerShadow','outerGlow','innerGlow','colorOverlay','gradientOverlay']:
  if s.get(k) is None:continue
  fx=s[k]
  if not isinstance(fx,dict):raise ValueError(k+'数据无效')
  v={'enabled':switch(fx.get('enabled',True),k),'opacity':number(fx.get('opacity',1),0,1,k)}
  if k=='gradientOverlay':v.update(gradient(fx))
  else:v['color']=color(fx.get('color','#ffffff' if 'Glow' in k else '#000000'))
  if k in ['stroke','dropShadow','innerShadow','outerGlow','innerGlow']:v['size']=number(fx.get('size',2 if k=='stroke' else 8),0,200,k)
  if 'Shadow' in k:v.update(angle=number(fx.get('angle',120),-360,360,k),distance=number(fx.get('distance',8),0,500,k))
  if k=='stroke':
   if fx.get('position','outside') not in ['outside','inside','center']:raise ValueError('描边位置无效')
   v['position']=fx.get('position','outside')
  result[k]=v
 return result
def mask(m):
 if not isinstance(m,dict) or m.get('type','rect') not in ['rect','ellipse','path']:raise ValueError('显示蒙版类型无效')
 result={'enabled':switch(m.get('enabled',True),'显示蒙版'),'type':m.get('type','rect')}
 for k in ['x','y','width','height']:result[k]=number(m.get(k),.01 if k in ['width','height'] else -100000,100000,'显示蒙版'+k)
 if result['type']=='path':
  d=m.get('d')
  if not isinstance(d,str) or not d.strip() or len(d)>1000000 or not re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz\s\d.eE,+\-]+',d):raise ValueError('显示蒙版路径无效')
  token=r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
  if re.sub(token,'',d).strip(' \t\r\n,'):raise ValueError('显示蒙版路径语义无效')
  parts=re.findall(token,d)
  if not parts or parts[0] not in ['M','m']:raise ValueError('显示蒙版必须从移动命令开始')
  arity={'M':2,'L':2,'H':1,'V':1,'C':6,'S':4,'Q':4,'T':2,'A':7,'Z':0};i=0
  while i<len(parts):
   cmd=parts[i].upper();i+=1
   if cmd not in arity:raise ValueError('显示蒙版路径命令无效')
   if cmd=='Z':continue
   args=[]
   while i<len(parts) and parts[i].upper() not in arity:
    args.append(number(float(parts[i]),-100000,100000,'显示蒙版路径'));i+=1
   if not args or len(args)%arity[cmd]:raise ValueError('显示蒙版路径参数不足')
   if cmd=='A' and any(args[j] not in [0,1] for start in range(0,len(args),7) for j in [start+3,start+4]):raise ValueError('弧形蒙版标志无效')
  result['d']=d
 return result
def design_fields(row):
 result={}
 for k,fn in [('gradient',gradient),('layerStyle',style),('displayMask',mask)]:
  if row.get(k) is not None:result[k]=fn(row[k])
 return result
def attach_groups(scene,groups):
 if not isinstance(groups,list) or len(groups)>350:raise ValueError('分组规划数量无效')
 aliases={};ids={n['id'] for n in scene['nodes']};owned=set();seen=set();result=[]
 for n in scene['nodes']:
  for key in [n['id'],n.get('sourceAssetId'),n.get('sourceVectorId'),n.get('sourceTextId'),*n.get('sourceEntityParts',[]),*n.get('sourceTextParts',[])]:
   if key:aliases.setdefault(key,[]).append(n['id'])
 for g in groups:
  if not isinstance(g,dict) or not isinstance(g.get('id'),str) or not g['id'] or g['id'] in ids|seen or not isinstance(g.get('children'),list) or not g['children']:raise ValueError('分组规划结构无效')
  children=[]
  for key in g['children']:
   if not isinstance(key,str) or key not in aliases:raise ValueError('分组「'+str(g.get('name') or g['id'])+'」包含未知成员 '+str(key))
   children.extend(aliases[key])
  children=list(dict.fromkeys(children))
  if owned.intersection(children):raise ValueError('一个图层不能归属两个父组')
  seen.add(g['id']);owned.update(children)
  result.append({'id':g['id'],'name':str(g.get('name') or '分组')[:80],'children':children,**design_fields(g)})
 scene['groups']=result
 return scene
