"""Data-only contract between platform chat and the component executor."""
import hashlib,json,math
import numpy as np
try:from .knowledge_store import knowledge_prompt,verify_ack
except ImportError:from knowledge_store import knowledge_prompt,verify_ack

def build_request(rgb,knowledge,knowledge_attachment=False):
 h,w=rgb.shape[:2]
 prefix=knowledge_prompt(knowledge) if not knowledge_attachment else '请完整读取file附件中的'+str(len(knowledge['sources']))+'份QP知识正文，不删减、不以摘要代替。知识版本回执必须原样返回：'+json.dumps(knowledge['receipt'],ensure_ascii=False)+'。附件未提供或无法完整读取请明确失败，禁止假确认。'
 return prefix+f'''\n【本次实际画板】width={w},height={h}。请观察连接的原图，独立识别、分类并分配任务，禁止照抄旧案例坐标或数量。
只输出一个JSON对象：{{"width":{w},"height":{h},"knowledge_ack":版本回执,"background_prompt":"英文干净环境背景重建指令，清除全部前景UI","assets":[...] ,"warnings":[],"pending_requirements":[]}}。
执行接口components-v1：每项必须id唯一、name中文、box=[left,top,right,bottom]原图整数像素、z唯一整数从后到前、group功能分组、method。
method实际支持：source保留材质像素（须polygon/ellipse/radius明确外轮廓，不能用截图矩形冒充抠图）；edited使用已有Klein去除子层并重建容器，须prompt英文说明保留本体和清除子层；biref完整独立图片抠图；shape按color=[R,G,B]提取纯色原生矢量并保留孔洞，tolerance默认55；solid根据准确polygon/ellipse/radius重建完整规则纯色图形；text原生文字，必须text与color。
可选polygon是全局顶点，holes是全局多边形列表，ellipse布尔，radius非负像素，clear_boxes是完全位于当前box内需要清除的子区域。普通文字独立登记，容器必须清除另成层内容；纸纹、阴影和自然毛边保留。按真实层序组织连续功能组。
当前接口不支持缩放复用、任意SVG指令或代码。重复项仍独立登记并把待复用要求列pending_requirements，不能声称已经复用。形状颜色应依据原图，不把纸张纹理仅因白色强转纯色。被遮挡部分无证据则明确待核对。所有画面验收NOT_REVIEWED。一次完整覆盖本图，不能只生成背景。'''

def bind_plan(reply,rgb,knowledge):
 try:value=json.loads(reply[reply.index('{'):reply.rindex('}')+1])
 except (ValueError,TypeError) as exc:raise ValueError('智能体未返回完整JSON') from exc
 verify_ack(value,knowledge);h,w=rgb.shape[:2]
 if (value.get('width'),value.get('height'))!=(w,h):raise ValueError('智能体画板尺寸错误')
 if not isinstance(value.get('background_prompt'),str) or not value['background_prompt'].strip():raise ValueError('缺少独立背景任务')
 rows=value.get('assets')
 if not isinstance(rows,list) or not 1<=len(rows)<=256:raise ValueError('素材清单必须为1至256项')
 def box(v,bounds):
  if not isinstance(v,list) or len(v)!=4 or any(type(n)is not int for n in v):raise ValueError('坐标必须四个整数')
  x,y,r,b=v;l,t,rr,bb=bounds
  if not l<=x<r<=rr or not t<=y<b<=bb:raise ValueError('坐标越界')
 def color(v):
  if not isinstance(v,list) or len(v)!=3 or any(type(n)is not int or not 0<=n<=255 for n in v):raise ValueError('颜色必须RGB整数')
 ids=set();orders=set();pixels=w*h;adjustments=[]
 for row in rows:
  if not isinstance(row,dict):raise ValueError('素材必须为对象')
  ident=row.get('id');z=row.get('z');method=row.get('method')
  if not isinstance(ident,str) or not ident or ident in ids or type(z)is not int or z in orders:raise ValueError('素材ID/层序缺失或重复')
  ids.add(ident);orders.add(z)
  if not isinstance(row.get('name'),str) or not row['name']:raise ValueError('素材缺少名称')
  if not isinstance(row.get('group',''),str):raise ValueError('分组必须为文字')
  box(row.get('box'),[0,0,w,h]);x,y,r,b=row['box']
  # Keep the model's actual path unchanged. Only widen its crop for <=4px
  # independent box rounding errors; never clamp or reshape a silhouette.
  points=[p for poly in ([row['polygon']] if row.get('polygon') else [])+row.get('holes',[]) for p in poly]
  if points:
   if any(not isinstance(p,list) or len(p)!=2 or any(type(n)not in (int,float) or not math.isfinite(n) for n in p) for p in points):raise ValueError('无效轮廓点')
   xx=min(x,math.floor(min(p[0] for p in points)));yy=min(y,math.floor(min(p[1] for p in points)))
   rr=max(r,math.ceil(max(p[0] for p in points)));bb=max(b,math.ceil(max(p[1] for p in points)))
   if [xx,yy,rr,bb]!=[x,y,r,b]:
    if not 0<=xx<rr<=w or not 0<=yy<bb<=h or max(x-xx,y-yy,rr-r,bb-b)>4:raise ValueError('轮廓越界：'+ident)
    adjustments.append(dict(id=ident,before=[x,y,r,b],after=[xx,yy,rr,bb],reason='扩大裁图容纳原始轮廓；路径未改'))
    row['box']=[xx,yy,rr,bb];x,y,r,b=row['box']
  pixels+=(r-x)*(b-y)
  if method not in {'source','edited','biref','shape','solid','text'}:raise ValueError('不支持的执行方法')
  if method in {'text','shape','solid'}:color(row.get('color'))
  if method=='text' and (not isinstance(row.get('text'),str) or not row['text']):raise ValueError('文字内容缺失')
  if method=='edited' and (not isinstance(row.get('prompt'),str) or not row['prompt']):raise ValueError('容器任务缺少提示')
  for key,default in [('radius',0),('tolerance',55)]:
   n=row.get(key,default)
   if type(n)not in (int,float) or not math.isfinite(n) or n<0 or (key=='tolerance' and n==0):raise ValueError('无效形状参数')
  for v in row.get('clear_boxes',[]):box(v,row['box'])
  for poly in ([row['polygon']] if row.get('polygon') else [])+row.get('holes',[]):
   if not isinstance(poly,list) or len(poly)<3:raise ValueError('无效轮廓')
   for point in poly:
    if not isinstance(point,list) or len(point)!=2 or any(type(n)not in (int,float) or not math.isfinite(n) for n in point) or not x<=point[0]<=r or not y<=point[1]<=b:raise ValueError('轮廓越界')
  row['kind']='text' if method=='text' else 'image'
 if pixels>64000000:raise ValueError('素材总面积超过64M预算，须合理裁紧而非降质')
 value.update(format='qp-auto-plan-v1',pipeline='components-v1',source_sha256=hashlib.sha256(np.ascontiguousarray(rgb,dtype=np.uint8).tobytes()).hexdigest(),visual_review='NOT_REVIEWED',coordinate_adjustments=adjustments)
 return value
