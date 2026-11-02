"""User-directed transparent layers, generated once in explicit back-to-front order."""
import copy,math,uuid,time
from datetime import datetime,timezone
from engine import load_source

def validate(body):
 if not isinstance(body,dict) or set(body)-{'image','width','height','title','layers','annotations','backgroundOnly','outpaint'} or not {'image','width','height','title','layers'}<=set(body):raise ValueError('指定拆层参数无效')
 if 'outpaint' in body and (not isinstance(body['outpaint'],bool) or body['outpaint'] and not body.get('backgroundOnly')):raise ValueError('扩建模式无效')
 if 'backgroundOnly' in body and not isinstance(body['backgroundOnly'],bool):raise ValueError('背景模式无效')
 if not isinstance(body['title'],str) or len(body['title'])>160:raise ValueError('工程名称无效')
 for key in ('width','height'):
  v=body[key]
  if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or not 1<=v<=6000:raise ValueError('拆层画板尺寸无效')
 if not isinstance(body['layers'],list) or not 1<=len(body['layers'])<=20:raise ValueError('请指定1至20个实际素材层')
 for layer in body['layers']:
  if not isinstance(layer,dict) or set(layer)!={'name','instruction','box'}:raise ValueError('拆层清单无效')
  for key,limit in (('name',100),('instruction',4000)):
   if not isinstance(layer[key],str) or not layer[key].strip() or len(layer[key])>limit:raise ValueError('拆层名称或要求无效')
  b=layer['box']
  if not isinstance(b,dict) or set(b)!={'x','y','width','height'} or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in b.values()):raise ValueError('素材范围无效')
  if not body.get('backgroundOnly') and (b['x']<0 or b['y']<0 or b['width']<=0 or b['height']<=0 or b['x']+b['width']>body['width'] or b['y']+b['height']>body['height']):raise ValueError('素材范围超出画板')
 if body.get('outpaint') and (len(body['layers'])!=1 or body['layers'][0]['box']['x']!=0 or body['layers'][0]['box']['y']!=0 or body['layers'][0]['box']['width']!=body['width'] or not body['height']<body['layers'][0]['box']['height']<=6000 or body['layers'][0]['box']['height']%1 or body['width']*body['layers'][0]['box']['height']>6000000):raise ValueError('上下扩建须保持原宽度，目标高度须大于原图且在安全尺寸内')
 if body.get('backgroundOnly'):
  b=body['layers'][0]['box']
  if len(body['layers'])!=1 or b['x']!=0 or b['y']!=0 or b['width']!=body['width'] or not body['height']<=b['height']<=6000 or b['height']%1 or b['width']*b['height']>6000000:raise ValueError('背景画布须保持原宽，可指定原高度或上下扩建高度')
 with load_source(body['image']) as image:
  if image.size!=(body['width'],body['height']):raise ValueError('原图尺寸与拆层画板不符')
 if body.get('outpaint'):
  from image_replace import _image
  with _image(body['image']) as raw:
   if raw.getchannel('A').getextrema()[0]!=255:raise ValueError('上下扩建需要完整不透明背景，请先提取背景或导入完整背景图')
 from source_annotations import validate as validate_annotations
 validate_annotations(body.get('annotations'),body['image'],body['width'],body['height'])
 return copy.deepcopy(body)

def generate(body,home,cancelled,progress):
 started=time.monotonic()
 body=validate(body)
 source=home/'原图.png'
 with load_source(body['image']) as image:image.save(source)
 assets=home/'1_过程/01_素材';assets.mkdir(parents=True)
 structure=home/'1_过程/02_结构';structure.mkdir(parents=True)
 from source_annotations import install
 install(body.get('annotations'),source,structure)
 from incremental_assets import extract_once
 nodes=[]
 for index,layer in enumerate(body['layers']):
  if cancelled():raise InterruptedError('已停止指定拆层')
  b=layer['box'];ident='assistant-'+uuid.uuid4().hex
  brief=layer['instruction']+'；用户明确指定的独立层，仅提取本层对象，其他对象和整图背景必须透明；补全被遮挡的完整形体，保持原图尺寸、位置、朝向与风格。艺术文字按原字形保留描边及自带阴影，不拆成普通文字。'
  node={'id':ident,'type':'image','name':layer['name'],**b,'sourceAssetId':ident,'assetKind':'complete-asset','extractionBrief':brief,'_repairNotes':[brief]}
  progress(index/len(body['layers']),'正在提取第 '+str(index+1)+'/'+str(len(body['layers']))+' 层：'+layer['name'])
  if body.get('backgroundOnly'):
   from image_provider import CLIENT
   from reference_fidelity import BACKGROUND_PRESERVATION
   from PIL import Image
   from engine import png
   target=assets/'完整背景.png'
   prompt='从附件原图去掉全部UI并补全遮挡的自然场景背景。'+layer['instruction']+'。保留原横竖构图、场景对象原位置和大小，完整画布宽高比例 '+str(body['width'])+':'+str(body['height'])+'，铺满四角的不透明背景，无透明孔洞、羽化边缘、棋盘格、边框，不裁切或重排。'+BACKGROUND_PRESERVATION
   refs=[source]
   if b['height']>body['height']:
    with Image.open(source) as im:original=im.convert('RGBA')
    offset=(int(b['height'])-original.height)//2
    canvas=Image.new('RGB',(int(b['width']),int(b['height'])),(127,127,127));canvas.paste(original,(0,offset));guide=assets/'扩建画布.png';canvas.save(guide);refs=[guide]
    prompt='只对第一张画布上下灰色新增区域进行上下扩建，灰色必须全部被匹配的自然水面/背景替代，原有中间区域左右不动，不移动或重绘已有物体。原图内容位于y='+str(offset)+'到'+str(offset+original.height)+'。输出完整不透明画布 '+str(int(b['width']))+'×'+str(int(b['height']))+'。用户要求：'+layer['instruction']+'。'+BACKGROUND_PRESERVATION
   if not body.get('outpaint') and b['height']>body['height']:
    prompt='一次生成同时完成去掉全部UI、补全遮挡背景及上下扩建，不分两次。第一张参考为目标尺寸画布，中间原截图从y='+str(offset)+'开始，高度'+str(body['height'])+'；上下灰色只是新增区域，不是成品。保留自然场景原位置与原宽，不拉伸、不移动鱼与荷花；移除原截图全部UI和文字及其阴影，补齐遮挡，新增区域续画水面，不得粘回含UI原图。目标完整不透明尺寸 '+str(int(b['width']))+'×'+str(int(b['height']))+'。用户要求：'+layer['instruction']+'。'+BACKGROUND_PRESERVATION
   record=CLIENT.generate(prompt,refs,target,transparent=False,cancelled=cancelled,on_status=lambda m:progress(0,m))
   if cancelled():raise InterruptedError('已停止背景提取')
   if not isinstance(record,dict) or not record.get('actualImageGeneration'):raise ValueError('背景未完成实际生成')
   with Image.open(target) as output:
    if b['height']==body['height'] and abs(output.width/output.height-b['width']/b['height'])/(b['width']/b['height'])>.01:raise ValueError('背景生成比例与原图不符，未应用；没有自动重试')
    rgba=output.convert('RGBA')
    if rgba.getchannel('A').getextrema()[0]!=255:raise ValueError('完整背景出现透明区域，未应用；没有自动重试')
    # Outpaint normalizes newly generated margins only: original center is restored byte-for-byte below.
    if rgba.size!=(b['width'],b['height']):rgba=rgba.resize((int(b['width']),int(b['height'])),Image.Resampling.LANCZOS)
    if body.get('outpaint'):rgba.paste(original,(0,offset))
    candidate={'id':ident,'type':'image','name':layer['name'],**b,'src':png(rgba),'assetKind':'background','provenance':'aimake-image-generation' if record.get('provider')=='aimake' else 'codex-image-generation','generationRecord':record,'review':True,'assetReviewStatus':'NOT_REVIEWED'}
  else:
   if (body.get('annotations') or {}).get('allowExpand') is True:
    from expanded_assets import extract
    candidate=extract(source,node,assets,cancelled,lambda m:progress(index/len(body['layers']),m))
   else:candidate=extract_once(source,node,assets,structure,cancelled,source,lambda m:progress(index/len(body['layers']),m))
  if candidate.get('provenance')=='source-crop-fallback' or not candidate.get('generationRecord',{}).get('actualImageGeneration'):raise ValueError(layer['name']+'未完整提取，未应用本轮结果；没有自动重试')
  candidate.pop('_repairNotes',None);nodes.append(candidate)
 if cancelled():raise InterruptedError('已停止指定拆层')
 result={'format':'shijie-scene','version':2,'title':body['title'],'width':body['width'],'height':body['height'],'source':body['image'],'originalSource':body['image'],'comparisonSource':body['image'],'background':None,'nodes':nodes,'groups':[],'edges':[],'recognition':{'extractionStatus':'COMPLETED','reviewStatus':'NOT_REVIEWED','assistantDirected':True,'requestedLayers':body['layers']}}
 if body.get('backgroundOnly'):
  result.update(width=nodes[0]['width'],height=nodes[0]['height'],source=nodes[0]['src'],comparisonSource=nodes[0]['src'],originalSource=nodes[0]['src'],originalSize={'width':nodes[0]['width'],'height':nodes[0]['height']})
 result['recognition']['timing']={'completedAt':datetime.now(timezone.utc).isoformat(),'elapsedMs':round((time.monotonic()-started)*1000)}
 progress(1,'指定素材层已生成，等待预览确认')
 return result
