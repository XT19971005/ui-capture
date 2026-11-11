"""Native layer contract established during annotation analysis, before generation."""
import copy
import re
from design_properties import obj, nullable, STYLE, GRADIENT, COLOR, color, number, design_fields, mask

from material_classification import material_icon

RULES = """原画标注分析阶段先确定分层方案，不得等生成PNG后再决定类型。每个对象列明：编号/名称、主体图片/原生文字/矢量、所属分组、完整范围、遮挡补全、前后层序、同款复用、独立子层排除、图层样式和待确认项。普通纯文字必须原生可编辑；纯色图标、标识、简单图形必须完整平滑矢量，保留孔洞及细笔画；艺术字先判断原生文字加样式能否还原，不能一律当图片。复杂材质和完整角色保留透明图片底稿。描边、投影、内阴影、内外发光、颜色叠加、渐变叠加按原图证据作为绑定主体的原生layerStyle，主体填色与外挂效果分开；不烘焙效果，不虚构原图没有的效果，主体材质光照不机械拆碎。容器清除另成层子项并补全；同款仅在形状、颜色、材质、方向、状态一致时复用合格底稿，位置实例独立。模糊文字、字体、隐藏形态和不支持效果必须标明待确认，不猜作合格。先用discuss展示分类、分组及样式方案，等待用户确认再执行；用户已经确认则沿用完整方案，不重复要求确认，不缩成最新一句提到的对象。方案绑定干净原图及标注，不因换图或改标注而串用。生成、保存恢复及PSD导出都沿用类型和原生样式，逐项对照验收；应用、结构通过、导出成功不代表画面合格。"""
NATIVE=obj({'text':{'type':'string'},'fontFamily':{'type':'string'},'fontSize':{'type':'number'},'fontWeight':{'type':'number'},'fill':COLOR,'d':{'type':'string'},'radius':{'type':'number'}})
FIELDS={'reuseOf':nullable({'type':'integer','minimum':0,'maximum':127}),'rotation':{'type':'number','minimum':-360,'maximum':360},'layerType':{'type':'string','enum':['image','text','rect','ellipse','path']},'native':nullable(NATIVE),'layerStyle':nullable(STYLE),'gradient':nullable(GRADIENT),'group':{'type':'string'},'reviewNote':{'type':'string'}}

def native_node(layer,ident):
 kind=layer.get('layerType','image')
 if kind not in ('image','text','rect','ellipse','path'):raise ValueError('拆层类型无效')
 for key in ('group','reviewNote'):
  if key in layer and (not isinstance(layer[key],str) or len(layer[key])>1000):raise ValueError('分组或待确认说明无效')
 fields=design_fields(layer)
 if layer.get('rotation',0) and layer.get('reuseOf') is None:raise ValueError('旋转仅用于同款位置实例，首个底稿按原画轮廓创建')
 number(layer.get('rotation',0),-360,360,'实例旋转')
 if layer.get('reuseOf') is not None:
  if layer.get('native') is not None:raise ValueError('同款实例须引用底稿，不能同时重新规划native形状')
  return None
 if kind=='image':
  if layer.get('native') is not None:raise ValueError('图片层不能带原生文字或矢量数据')
  return None
 if layer.get('assetKind')=='background':raise ValueError('场景背景不能冒充原生文字或矢量')
 n=layer.get('native')
 if not isinstance(n,dict) or set(n)-set(NATIVE['properties']):raise ValueError('缺少原生文字或矢量参数')
 out={'id':ident,'name':layer['name'],'type':kind,**layer['box'],'fill':color(n.get('fill')),**fields,'review':True,'assetReviewStatus':'NOT_REVIEWED','provenance':'annotation-native-plan'}
 if kind=='text':
  if not isinstance(n.get('text'),str) or not n['text'].strip() or len(n['text'])>12000:raise ValueError('原生文字内容无效')
  if not isinstance(n.get('fontFamily'),str) or not n['fontFamily'].strip() or len(n['fontFamily'])>200:raise ValueError('原生字体无效')
  out.update(text=n['text'],fontFamily=n['fontFamily'],fontSize=number(n.get('fontSize'),1,2000,'字号'),fontWeight=number(n.get('fontWeight'),100,1000,'字重'),strokeWidth=0,fontMatchApproximate=True)
 if kind=='rect':out['radius']=number(n.get('radius',0),0,6000,'圆角')
 if kind=='path':
  d=n.get('d');mask({'type':'path',**layer['box'],'d':d})
  out.update(d=d,fillRule='evenodd')
 if layer.get('reviewNote'):out.update(reviewIssue=layer['reviewNote'],assetReviewStatus='NEEDS_REVIEW')
 return out

def groups(layers,nodes):
 # Only contiguous members may form a group, so grouping cannot change occlusion.
 result=[];last=None
 for layer,node in zip(layers,nodes):
  name=layer.get('group','')
  if not name:last=None;continue
  if last is None or last['name']!=name:
   last={'id':'annotation-group-'+str(len(result)+1),'name':name,'children':[]};result.append(last)
  last['children'].append(node['id'])
 return result


def reuse_node(layer,source,master,ident,require_approved=True):
 """Clone a resource into an independent instance; never generate another image."""
 import json,subprocess,shutil
 from pathlib import Path
 out=copy.deepcopy(source);out.update(id=ident,name=layer['name'],review=True,assetReviewStatus='NEEDS_REVIEW',reviewIssue='同款位置实例待逐处校对',sourceResourceId=source.get('sourceResourceId') or source['id'],resourceMaster=False,provenance='annotation-resource-instance')
 b=layer['box'];rotation=layer.get('rotation',0)-master.get('rotation',0)
 if source['type']=='image':
  if require_approved and source.get('assetReviewStatus')!='PASS':raise ValueError('同款图片底稿尚未验收通过，保留已有结果，不重复生成')
  import math
  angle=math.radians(rotation);c=abs(math.cos(angle));sn=abs(math.sin(angle));reference=master['box']
  scale=min(b['width']/(reference['width']*c+reference['height']*sn),b['height']/(reference['width']*sn+reference['height']*c))
  dx=source['x']+source['width']/2-reference['x']-reference['width']/2;dy=source['y']+source['height']/2-reference['y']-reference['height']/2
  width=(source['width']*c+source['height']*sn)*scale;height=(source['width']*sn+source['height']*c)*scale
  out.update(x=b['x']+b['width']/2+(dx*math.cos(angle)-dy*math.sin(angle))*scale-width/2,y=b['y']+b['height']/2+(dx*math.sin(angle)+dy*math.cos(angle))*scale-height/2,width=width,height=height)
  if rotation:
   from image_replace import _image
   from engine import png
   from PIL import Image
   with _image(source['src']) as image:
    rotated=image.rotate(-rotation,resample=Image.Resampling.BICUBIC,expand=True)
    out['src']=png(rotated);rotated.close()
 elif source['type'] in ('path','rect','ellipse'):
  node=shutil.which('node')
  if not node:raise ValueError('矢量实例变换模块未就绪，未改为图片生成')
  tool=Path(__file__).with_name('resource_instance.cjs')
  done=subprocess.run([node,str(tool)],input=json.dumps({'node':source,'box':b,'rotation':rotation,'master':master['box']}),text=True,encoding='utf8',capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if done.returncode:raise ValueError('矢量实例变换失败，保留已有结果，不启动图片生成')
  transformed=json.loads(done.stdout);out.update(type='path',d=transformed['d'],**transformed.get('box',b));scale=transformed['scale']
 else:raise ValueError('仅同款图片和矢量可引用底稿，文字须保留各自准确内容')
 for effect in (out.get('layerStyle') or {}).values():
  if isinstance(effect,dict):
   for key in ('size','distance'):
    if key in effect:effect[key]*=scale
 out.update(design_fields(layer))
 return out

RULES+='\n自动标注阶段须标出生图image/矢量vector/文字text/待确认auto。带reuseKey的同色多圈是同款资源的独立位置，必须按每个圈分别建立图层，严禁以总包围框生成一群。不同姿态另分款；只同类不能复用。矢量按reuseOf引用首个底稿并变换位置/尺寸/旋转，不调用图片生成。图片底稿通过实际复核才复制，失败保留已有结果，不重发生图；所有复用位置仍待逐处校对。执行清单统计独立生图底稿数，不把位置数当付费次数。'

VECTOR_QUALITY_RULES='矢量判定不以只有一种颜色为条件。两种或多种纯色拼成的简单图标、标识、剪影仍优先矢量；例如深色蝙蝠身体加橙色眼睛，不能因有第二种颜色、抗锯齿过渡、轻微渐变或阴影就归为生图。主体、眼睛等色块按实际结构成为同一对象分组内的原生矢量子层，渐变、描边、阴影用原生填充或图层样式；同款多色实例应对应复用全部组件，不能只复制身体漏掉眼睛。复杂照片式纹理、真实材质或复杂立体光照才使用图片；完整实体不等于必定生图。矢量外缘须依据原造型拟合连续顺滑的贝塞尔曲线，以尽量少的合理锚点保持自然曲率；禁止沿低清像素台阶、压缩毛刺或锯齿逐点描成碎折线。翅膀尖角、凹口、孔洞、细笔画和眼睛位置必须保留，不能为顺滑而磨圆尖角、合并孔洞或改变比例。逐层放大检查外缘、内孔和曲线连接，不以文件后缀为SVG或存在path就认定合格。原图有意的像素风、笔刷毛边或纸纹除外，不能强行抹平。'
RULES+="\n"+VECTOR_QUALITY_RULES

STRICT_CLASSIFICATION_RULES='严格按原图视觉证据分类：图标是用途而非矢量类型。货币、徽章、宝石等带金属边、浮雕、折射和复杂立体光照时，完整主体必须image；例如金边紫蓝圆币及其星形内纹整体提取透明图片，不能用圆环、渐变圆和几块浅色碎片冒充。只有真正平面纯色或少量可准确还原形状才vector。标注ellipse/rect/envelope只表示定位圈形，绝不是生成图层类型。模糊看不清标auto并说明，不按名称猜矢量。逐项核对完整范围、细部、类别、同款姿态和层序，内部材质纹样不拆独立控件。分类与材质证据冲突时停止该对象，明确纠正分类，不自动付费。'
RULES+='\n'+STRICT_CLASSIFICATION_RULES
VECTOR_QUALITY_RULES+='\n'+STRICT_CLASSIFICATION_RULES
