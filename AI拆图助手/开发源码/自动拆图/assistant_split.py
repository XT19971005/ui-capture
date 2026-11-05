"""User-directed transparent layers, generated once in explicit back-to-front order."""
import copy,math,uuid,time
from datetime import datetime,timezone
from engine import load_source

def validate(body):
 if not isinstance(body,dict) or set(body)-{'image','width','height','title','layers','annotations','backgroundOnly','outpaint'} or not {'image','width','height','title','layers'}<=set(body):raise ValueError('指定拆层参数无效')
 body=copy.deepcopy(body)
 if 'outpaint' in body and (not isinstance(body['outpaint'],bool) or body['outpaint'] and not body.get('backgroundOnly')):raise ValueError('扩建模式无效')
 if 'backgroundOnly' in body and not isinstance(body['backgroundOnly'],bool):raise ValueError('背景模式无效')
 if not isinstance(body['title'],str) or len(body['title'])>160:raise ValueError('工程名称无效')
 for key in ('width','height'):
  v=body[key]
  if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or not 1<=v<=6000:raise ValueError('拆层画板尺寸无效')
 if not isinstance(body['layers'],list) or not 1<=len(body['layers'])<=20:raise ValueError('请指定1至20个实际素材层')
 from source_annotations import mark_margins
 mx,my=mark_margins(body['width'],body['height']) if isinstance(body.get('annotations'),dict) and body['annotations'].get('allowExpand') is True else (0,0)
 for layer in body['layers']:
  if not isinstance(layer,dict) or set(layer)-{'name','instruction','box','assetKind'} or not {'name','instruction','box'}<=set(layer):raise ValueError('拆层清单无效')
  if layer.get('assetKind','complete-asset') not in ('complete-asset','background'):raise ValueError('素材类型无效')
  for key,limit in (('name',100),('instruction',4000)):
   if not isinstance(layer[key],str) or not layer[key].strip() or len(layer[key])>limit:raise ValueError('拆层名称或要求无效')
  b=layer['box']
  if not isinstance(b,dict) or set(b)!={'x','y','width','height'} or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in b.values()):raise ValueError('素材范围无效')
  if not body.get('backgroundOnly'):
   if b['width']<=0 or b['height']<=0:raise ValueError('素材范围无效')
   outside=b['x']<0 or b['y']<0 or b['x']+b['width']>body['width'] or b['y']+b['height']>body['height']
   if outside:
    if max(abs(v) for v in b.values())>12000 or b['width']*b['height']>36000000:raise ValueError('素材参考范围超过安全尺寸')
    x=max(0,b['x']);y=max(0,b['y']);right=min(body['width'],b['x']+b['width']);bottom=min(body['height'],b['y']+b['height'])
    if right<=x or bottom<=y:raise ValueError('素材范围未包含任何原图参考，无法识别目标')
    # This box locates visible reference pixels, never bounds completed output.
    layer['instruction']+='；完整形体允许延伸至原画外，旧框不是裁切边界；box仅定位可见参考，不得压缩或裁去补全部分。'
    layer['box']=b={'x':x,'y':y,'width':right-x,'height':bottom-y}
   if layer.get('assetKind')=='background' and b!={'x':0,'y':0,'width':body['width'],'height':body['height']}:raise ValueError('场景底稿须覆盖完整参考画布')
 if body.get('backgroundOnly'):
  b=body['layers'][0]['box']
  if len(body['layers'])!=1 or b['x']!=0 or b['y']!=0 or any(b[k]%1 or not body[k]<=b[k]<=6000 for k in ('width','height')) or b['width']*b['height']>36000000:raise ValueError('背景扩建目标须容纳原图，宽高为安全范围内的整数；缩小画布请使用调整画布')
  if body.get('outpaint') and b['width']==body['width'] and b['height']==body['height']:raise ValueError('扩建目标与原画布相同，请指定更大的宽度或高度')
 with load_source(body['image']) as image:
  if image.size!=(body['width'],body['height']):raise ValueError('原图尺寸与拆层画板不符')
 if body.get('outpaint'):
  from image_replace import _image
  with _image(body['image']) as raw:
   if raw.getchannel('A').getextrema()[0]!=255:raise ValueError('上下扩建需要完整不透明背景，请先提取背景或导入完整背景图')
 from source_annotations import validate as validate_annotations
 validate_annotations(body.get('annotations'),body['image'],body['width'],body['height'])
 return copy.deepcopy(body)

def generate(body,home,cancelled,progress,on_scene=None):
 started=time.monotonic()
 body=validate(body)
 source=home/'原图.png'
 from image_replace import _image
 with _image(body['image']) as image:image.save(source)
 assets=home/'1_过程/01_素材';assets.mkdir(parents=True)
 structure=home/'1_过程/02_结构';structure.mkdir(parents=True)
 from source_annotations import install
 install(body.get('annotations'),source,structure)
 from incremental_assets import extract_once
 nodes=[]
 def partial_scene():
  return {'format':'shijie-scene','version':2,'title':body['title'],'width':body['width'],'height':body['height'],'source':body['image'],'originalSource':body['image'],'comparisonSource':body['image'],'background':None,'nodes':copy.deepcopy(nodes),'groups':[],'edges':[],'_partial':True,'recognition':{'extractionStatus':'INCOMPLETE','reviewStatus':'NOT_REVIEWED','assistantDirected':True,'requestedLayers':copy.deepcopy(body['layers']),'pendingLayers':copy.deepcopy(body['layers'][len(nodes):]),'timing':{'completedAt':datetime.now(timezone.utc).isoformat(),'elapsedMs':round((time.monotonic()-started)*1000)}}}
 try:
  for index,layer in enumerate(body['layers']):
   if cancelled():raise InterruptedError('已停止指定拆层')
   b=layer['box'];ident='assistant-'+uuid.uuid4().hex
   brief=layer['instruction']+'；用户明确指定的独立层，仅提取本层对象，其他对象和整图背景必须透明；补全被遮挡的完整形体，保持原图尺寸、位置、朝向与风格。艺术文字按原字形保留描边及自带阴影，不拆成普通文字。'
   node={'id':ident,'type':'image','name':layer['name'],**b,'sourceAssetId':ident,'assetKind':'complete-asset','extractionBrief':brief,'_repairNotes':[brief]}
   progress(index/len(body['layers']),'正在提取第 '+str(index+1)+'/'+str(len(body['layers']))+' 层：'+layer['name'])
   if body.get('backgroundOnly') or layer.get('assetKind')=='background':
    from image_provider import CLIENT
    from reference_fidelity import BACKGROUND_PRESERVATION
    from PIL import Image
    from engine import png
    target=assets/'完整背景.png'
    prefix='从附件原图去掉全部UI并补全遮挡的自然场景背景。' if body.get('backgroundOnly') else '生成整套分层的纯净场景底稿，移除本次清单中另成层的全部对象并补齐遮挡；不能把独立对象残留在底稿中。本轮另成层对象清单：'+ '；'.join(item['name']+'：'+item['instruction'] for item in body['layers'] if item is not layer and item.get('assetKind')!='background')+'。'
    policy=BACKGROUND_PRESERVATION if body.get('backgroundOnly') else '场景底稿以原图配色、亮度和笔触为准，仅保留未另成层的环境；本轮独立清单中的自然对象也必须去掉并补齐其后的环境，不能因其是自然对象而重复留在底稿。禁止提亮、增艳、锐化、增加反光或重排环境。'
    prompt=prefix+layer['instruction']+'。保留原横竖构图、未另成层场景对象的原位置和大小，完整画布宽高比例 '+str(body['width'])+':'+str(body['height'])+'，铺满四角的不透明背景，无透明孔洞、羽化边缘、棋盘格、边框，不裁切或重排。'+policy
    refs=[source]
    if b['width']>body['width'] or b['height']>body['height']:
     with Image.open(source) as im:original=im.convert('RGBA')
     offset_x=(int(b['width'])-original.width)//2;offset_y=(int(b['height'])-original.height)//2
     canvas=Image.new('RGB',(int(b['width']),int(b['height'])),(127,127,127));canvas.paste(original,(offset_x,offset_y));guide=assets/'扩建画布.png';canvas.save(guide);canvas.close();refs=[guide]
     prompt='仅在第一张画布灰色新增区域向四周扩建（原宽不变时为上下扩建），不拉伸或重排已有内容。原图位于x='+str(offset_x)+',y='+str(offset_y)+'，原尺寸'+str(original.width)+'×'+str(original.height)+'；灰色不是成品。输出完整不透明画布 '+str(int(b['width']))+'×'+str(int(b['height']))+'。用户要求：'+layer['instruction']+'。'+BACKGROUND_PRESERVATION
     if not body.get('outpaint'):
      prompt='一次生成同时完成去掉全部UI、补全遮挡背景及四周扩建。原截图位于x='+str(offset_x)+',y='+str(offset_y)+'，原尺寸'+str(original.width)+'×'+str(original.height)+'；保持未删除场景内容的位置、大小和朝向，新增区域续画自然背景，不粘回含UI原图，不重排。完整不透明目标尺寸 '+str(int(b['width']))+'×'+str(int(b['height']))+'。用户要求：'+layer['instruction']+'。'+BACKGROUND_PRESERVATION
    record=CLIENT.generate(prompt,refs,target,transparent=False,cancelled=cancelled,on_status=lambda m:progress(0,m))
    if cancelled():raise InterruptedError('已停止背景提取')
    if not isinstance(record,dict) or not record.get('actualImageGeneration'):raise ValueError('背景未完成实际生成')
    with Image.open(target) as output:
     if max(output.size)>6000 or output.width*output.height>36000000:raise ValueError('生成背景超过安全解码尺寸')
     mismatch=abs(output.width/output.height-b['width']/b['height'])/(b['width']/b['height'])>.001
     rgba=output.convert('RGBA')
     if rgba.getchannel('A').getextrema()[0]!=255:raise ValueError('完整背景出现透明区域，未应用；没有自动重试')
     # Outpaint normalizes newly generated margins only: original center is restored byte-for-byte below.
     if not mismatch and rgba.size!=(b['width'],b['height']):rgba=rgba.resize((int(b['width']),int(b['height'])),Image.Resampling.LANCZOS)
     if body.get('outpaint') and not mismatch:rgba.paste(original,(offset_x,offset_y))
     candidate={'id':ident,'type':'image','name':layer['name'],**b,'src':png(rgba),'assetKind':'background','provenance':'aimake-image-generation' if record.get('provider')=='aimake' else 'codex-image-generation','generationRecord':{k:record[k] for k in ('actualImageGeneration','transparent','provider','model','genId','postprocessing') if k in record},'review':True,'assetReviewStatus':'NOT_REVIEWED'}
     if mismatch:
      scale=min(b['width']/rgba.width,b['height']/rgba.height);width=rgba.width*scale;height=rgba.height*scale
      candidate.update(x=b['x']+(b['width']-width)/2,y=b['y']+(b['height']-height)/2,width=width,height=height,positionReviewRequired=True,boundaryReviewRequired=True,assetReviewStatus='NEEDS_REVIEW',reviewIssue='背景返回画幅与目标不同，已完整保留原比例和生成像素，未拉伸或裁切；需校对后再作为完整底稿。'+('上下扩建原中间区域尚未回贴，原始图保留供对照。' if body.get('outpaint') else ''))
   else:
    if (body.get('annotations') or {}).get('allowExpand') is True:
     from expanded_assets import extract
     candidate=extract(source,node,assets,cancelled,lambda m:progress(index/len(body['layers']),m),annotations=body.get('annotations'))
    else:candidate=extract_once(source,node,assets,structure,cancelled,source,lambda m:progress(index/len(body['layers']),m))
   if candidate.get('provenance')=='source-crop-fallback' or not candidate.get('generationRecord',{}).get('actualImageGeneration'):raise ValueError(layer['name']+'未完整提取，未应用本轮结果；没有自动重试')
   candidate.pop('_repairNotes',None);nodes.append(candidate)
   if on_scene:on_scene(partial_scene())
 except Exception as error:
  if nodes:error.partial=partial_scene()
  raise
 if cancelled():raise InterruptedError('已停止指定拆层')
 result={'format':'shijie-scene','version':2,'title':body['title'],'width':body['width'],'height':body['height'],'source':body['image'],'originalSource':body['image'],'comparisonSource':body['image'],'background':None,'nodes':nodes,'groups':[],'edges':[],'recognition':{'extractionStatus':'COMPLETED','reviewStatus':'NOT_REVIEWED','assistantDirected':True,'requestedLayers':body['layers']}}
 if body.get('backgroundOnly') and not nodes[0].get('positionReviewRequired'):
  result.update(width=nodes[0]['width'],height=nodes[0]['height'],source=nodes[0]['src'],comparisonSource=nodes[0]['src'],originalSource=nodes[0]['src'],originalSize={'width':nodes[0]['width'],'height':nodes[0]['height']})
 if any(n.get('boundaryReviewRequired') or n.get('positionReviewRequired') for n in nodes):
  result['recognition']['reviewStatus']='NEEDS_REVIEW'
  for n in nodes:
   if n.get('boundaryReviewRequired') or n.get('positionReviewRequired'):n.update(review=True,assetReviewStatus='NEEDS_REVIEW')
 # Outpaint must preserve source pixels; a different returned aspect leaves this unfinished.
 if body.get('outpaint') and nodes[0].get('positionReviewRequired'):
  result['_partial']=True;result['recognition'].update(extractionStatus='INCOMPLETE',pendingLayers=copy.deepcopy(body['layers']))
 result['recognition']['timing']={'completedAt':datetime.now(timezone.utc).isoformat(),'elapsedMs':round((time.monotonic()-started)*1000)}
 progress(1,'指定素材层已生成，等待预览确认')
 return result
