"""Actual per-asset vision and named final acceptance gates; never auto-fill PASS."""
import base64,io,json,re,uuid
from pathlib import Path
from PIL import Image
from codex_client import CLIENT

ASSET_CRITERIA=('身份与完整实体','比例与定位','颜色与光照','透明边缘与孔洞','材质文字与标识','独立物品归属')
FINAL_CRITERIA=('拆分粒度','文字合并边界','画布与比例','位置与层级','颜色与光照','人物身份与完整实体','文字内容与字形','文字原生编辑','矢量完整与孔洞','透明边缘','背景去件与补全','渐变与图层样式','蒙版与完整底稿','来源与独立回读','PSD编辑与重组','完成状态与清理')

class AssetReviewError(RuntimeError):
 def __init__(self,name,result):
  labels={'身份与完整实体':'主体完整性','比例与定位':'比例/位置','颜色与光照':'颜色','透明边缘与孔洞':'透明边缘','材质文字与标识':'文字/标识','独立物品归属':'素材归属'}
  failed=[labels.get(c['name'],c['name']) for c in result['checks'] if c['status']!='PASS']
  super().__init__('素材「'+name+'」未通过内部复核：'+('、'.join(failed) or '存在待修正问题'))
  self.diagnostics={'stage':'asset-review','layer':name,'checks':result['checks'],'issues':result['issues']}
GRANULARITY_RULES='独立图片、人物、道具、图标、装饰各自成层；布局分组只关联图层，不能压平成一张组合图。只有确实无法独立提取的互遮完整实体才允许组合，须在warnings和验收观察注明原因；不能只因位置相近、共享底板、属于同一功能区或节省生成次数而合并。一个人物保持完整，不拆脸、手、衣物及一体持物。只合并视觉相连且属于同一文案的连续文字；不同按钮、标题与副标题、标签与数值、不同位置的独立文案分开编辑。同一连续文案可保留换行、方向及局部颜色，不能逐字碎拆；不要求字的像素必须接触。服饰印花、牌面和匾额仍属于其完整材质。'
FINAL_RULES=GRANULARITY_RULES+'\nacceptance_checks须按以下名称逐项唯一填写PASS/FAIL和非空实际观察：'+json.dumps(FINAL_CRITERIA,ensure_ascii=False)+'。比例/定位/颜色以原图为准，不拉伸、不加艳、不美白、不重新布光。文字逐字核对，检查遗漏、错字、笔画、孔洞、字体、方向、间距和裁边。图层样式以PSD存在可编辑原生属性为准，允许不影响主体的轻微渲染器差异；不能漏掉主要效果、改变主色或把效果烘焙进底稿。蒙版关闭后底稿完整；背景无前景残留；图层重组无重复轮廓/接缝。原生编辑、来源与回读按提供的真实结构证据核验；清理项检查任务执行策略，不能假称已经下载或已经打开Photoshop。未看清或无证据的硬性项不能PASS。'

def check_errors(checks,expected):
 names=[c.get('name') for c in checks];errors=[]
 if len(names)!=len(expected) or set(names)!=set(expected) or len(set(names))!=len(names):errors.append('验收项目缺失、重复或未知')
 for c in checks:
  if c.get('status')!='PASS' or not isinstance(c.get('notes'),str) or not c['notes'].strip():errors.append(str(c.get('name'))+'未通过或缺少实际观察')
 return errors

def check_schema(names):
 return {'type':'array','items':{'type':'object','properties':{'name':{'type':'string','enum':list(names)},'status':{'type':'string','enum':['PASS','FAIL']},'notes':{'type':'string'}},'required':['name','status','notes'],'additionalProperties':False}}

ASSET_REVIEW={'type':'object','properties':{'status':{'type':'string','enum':['PASS','FAIL']},'checks':check_schema(ASSET_CRITERIA),'issues':{'type':'array','items':{'type':'string'}}},'required':['status','checks','issues'],'additionalProperties':False}

def review_asset(source,node,structure,cancelled,on_status=None):
 structure=Path(structure);tag='逐件临时_'+uuid.uuid4().hex;files=[]
 try:
  original=Image.open(source).convert('RGB');x,y,w,h=(round(node[k]) for k in ('x','y','width','height'))
  # Exact assigned geometry is shown, without altering registered source bytes.
  ref=structure/(tag+'_原图.png');original.crop((x,y,x+w,y+h)).save(ref);files.append(ref)
  actual=Image.open(io.BytesIO(base64.b64decode(node['src'].split(',',1)[1]))).convert('RGBA')
  actual=actual.resize((w,h),Image.Resampling.LANCZOS)
  for name,color in [('深底',(24,25,28,255)),('浅底',(240,240,240,255))]:
   file=structure/(tag+'_'+name+'.png');bg=Image.new('RGBA',(w,h),color);bg.alpha_composite(actual);bg.save(file);files.append(file)
  prompt='逐件检查实际提取素材“'+node['name']+'”。第一张是原图对应准确坐标区域，后两张是当前完整底稿按相同位置/比例放在深浅底。必须实际对照，每项填写观察，不能仅凭生成完成PASS。'+GRANULARITY_RULES+'\n颜色检查肤色/服装/主色的色相、饱和度、明度和光照，不允许自动增强。比例检查五官、肢体、物体外形及画布定位，补全遮挡部分不改变已有可见区域。身份检查脸型、发型、神态、姿势；不是人物则检查完整物体。透明边缘排除背景/相邻物品残留、锯齿、毛刺、断笔、误透明。材质文字不能错字/变形。仅原图已有的毛边和纹理保留。'+'\n检查名称：'+json.dumps(ASSET_CRITERIA,ensure_ascii=False)
  result=CLIENT.analyze(prompt,files,ASSET_REVIEW,cancelled,on_status=on_status)
  errors=check_errors(result.get('checks',[]),ASSET_CRITERIA)
  if errors or result.get('status')!='PASS' or result.get('issues'):
   result={**result,'status':'FAIL','issues':list(result.get('issues',[]))+errors or ['实际逐件复核未通过']}
  record=structure/('逐件复核_'+re.sub(r'[^\w-]','_',node['id'])+'.json');record.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
  return result
 finally:
  for file in files:file.unlink(missing_ok=True)
