"""Explicit raster replacement candidates, bounded to natural image pixels."""
import base64,copy,hashlib,io,json,math,re,time
from pathlib import Path
from PIL import Image,UnidentifiedImageError


def _image(value):
 if not isinstance(value,str) or len(value)>36000000 or not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',value):raise ValueError('替换图片必须是有效内嵌图片')
 try:
  with Image.open(io.BytesIO(base64.b64decode(value.split(',',1)[1],validate=True))) as image:
   if image.width*image.height>6000000 or max(image.size)>6000:raise ValueError('替换图片尺寸超限')
   return image.convert('RGBA')
 except (OSError,UnidentifiedImageError,Image.DecompressionBombError) as error:raise ValueError('替换图片数据无法读取') from error


def _region(value,size):
 if value is None:return None
 if not isinstance(value,dict) or set(value)!={'x','y','width','height'} or any(type(v) is not int for v in value.values()):raise ValueError('替换区域必须是原图片像素整数矩形')
 x,y,w,h=(value[k] for k in ('x','y','width','height'))
 if x<0 or y<0 or w<=0 or h<=0 or x+w>size[0] or y+h>size[1]:raise ValueError('替换区域超出原图片尺寸')
 return dict(value)


def _box(region,size):
 if region is None:return (0,0,*size)
 return (region['x'],region['y'],region['x']+region['width'],region['y']+region['height'])


def _selection(value,region,size):
 if value is None:return None,None
 if not isinstance(value,dict):raise ValueError('替换套索必须是有效多边形')
 if value.get('type')=='polygon' and set(value)=={'type','points'}:polygons=[value['points']]
 elif value.get('type')=='polygons' and set(value)=={'type','polygons'}:polygons=value['polygons']
 else:raise ValueError('替换套索必须是有效多边形')
 if not isinstance(polygons,list) or not 1<=len(polygons)<=32:raise ValueError('替换套索需要 1 至 32 个选区')
 if any(not isinstance(p,list) or not 3<=len(p)<=2048 for p in polygons) or sum(len(p) for p in polygons)>2048:raise ValueError('每个替换套索至少需要 3 个点，全部选区合计最多 2048 个点')
 points=[point for polygon in polygons for point in polygon]
 for point in points:
  if not isinstance(point,list) or len(point)!=2 or any(type(v) is not int for v in point):raise ValueError('替换套索坐标必须是原图片像素整数')
  if not 0<=point[0]<=size[0] or not 0<=point[1]<=size[1]:raise ValueError('替换套索超出原图片尺寸')
 x0=min(p[0] for p in points);y0=min(p[1] for p in points);x1=max(p[0] for p in points);y1=max(p[1] for p in points)
 bounds={'x':x0,'y':y0,'width':x1-x0,'height':y1-y0}
 if x1<=x0 or y1<=y0 or region!=bounds:raise ValueError('替换区域必须与套索包围框一致且非空')
 mask=Image.new('L',(x1-x0,y1-y0),0)
 for polygon in polygons:_fill_polygon(mask,polygon,(x0,y0))
 return copy.deepcopy(value),mask


def _fill_polygon(mask,points,origin):
 # Binary pixel-center even-odd fill, matching Canvas fill('evenodd') topology.
 # Horizontal edges are ignored; each nonhorizontal edge is active on [y0,y1).
 # Do not use signed shoelace area: a useful figure-eight can sum to zero.
 # Fill each polygon separately into the same binary mask: overlap is union,
 # never XOR. No extra full-size mask is allocated per additive selection.
 x0,y0=origin;x1=x0+mask.width;filled=False
 edges=[]
 for a,b in zip(points,points[1:]+points[:1]):
  if a[1]==b[1]:continue
  if a[1]>b[1]:a,b=b,a
  edges.append((a[0],a[1],b[0]-a[0],b[1]-a[1]))
 for y in range(min(p[1] for p in points),max(p[1] for p in points)):
  intersections=[]
  for x,ey,dx,dy in edges:
   if ey<=y<ey+dy:
    numerator=2*x*dy+(2*y+1-2*ey)*dx;denominator=2*dy
    # Sort true intersections, then ceil(x_intersection - 0.5) using exact
    # integer arithmetic so a boundary through a pixel center cannot drift.
    intersections.append((numerator/denominator,-(-(numerator-dy)//denominator)))
  intersections.sort()
  for index in range(0,len(intersections)-1,2):
   left=max(x0,intersections[index][1]);right=min(x1,intersections[index+1][1])
   if right>left:mask.paste(255,(left-x0,y-y0,right-x0,y-y0+1));filled=True
 if not filled:raise ValueError('替换套索没有可替换像素，请重新圈选有效区域')


def validate_replacement(scene,replacement):
 from incremental_assets import effective_locked_ids
 if not isinstance(scene,dict) or not isinstance(scene.get('nodes'),list) or not isinstance(replacement,dict) or set(replacement)-{'targetId','region','selection','prompt','reference','intent'}:raise ValueError('替换参数无效')
 if 'intent' in replacement and replacement['intent']!='generate':raise ValueError('不支持的图片生成意图')
 intent=replacement.get('intent')
 ident=replacement.get('targetId');prompt=replacement.get('prompt','');reference=replacement.get('reference')
 if not isinstance(ident,str) or not ident or len(ident)>160:raise ValueError('请选择一个图片图层')
 matches=[n for n in scene['nodes'] if isinstance(n,dict) and n.get('id')==ident]
 if len(matches)!=1 or matches[0].get('type')!='image' or matches[0].get('versionArchived'):raise ValueError('只能替换一个当前图片图层')
 node=matches[0]
 groups=scene.get('groups',[]);entries={n['id']:n for n in [*scene['nodes'],*groups]};parents={child:g['id'] for g in groups for child in g.get('children',[])}
 current=ident;visited=set()
 while current is not None:
  if current in visited:raise ValueError('图层分组存在循环')
  visited.add(current);entry=entries[current]
  if entry.get('visible') is False or entry.get('hidden') or entry.get('versionArchived'):raise ValueError('图片图层或父组已隐藏，请先显示当前图层')
  current=parents.get(current)
 # Imported source images are locked by the importer. This exception does not
 # extend to split assets, other layers, or any inherited group lock.
 prior=node.get('imageReplacement');replaced_import=isinstance(prior,dict) and prior.get('importedSource') is True
 active=[n for n in scene['nodes'] if not n.get('versionArchived')]
 original_import=((scene.get('provenance')=='user-image' or node.get('provenance')=='imported-source' or replaced_import) and len(active)==1 and not scene.get('groups') and not scene.get('_partial') and not node.get('sourceAssetId') and not node.get('pendingGeneration') and node.get('x')==0 and node.get('y')==0 and node.get('width')==scene.get('width') and node.get('height')==scene.get('height') and (node.get('src')==scene.get('source') or replaced_import))
 if ident in effective_locked_ids(scene) and not original_import:raise ValueError('图片图层或父组已锁定，请先解锁')
 if not isinstance(prompt,str) or len(prompt)>6000:raise ValueError('替换描述无效或超过 6000 字')
 if reference is not None and (not isinstance(reference,dict) or set(reference)-{'src','region'} or not reference.get('src')):raise ValueError('替换参考图参数无效')
 if not prompt.strip() and reference is None:raise ValueError('请输入替换描述或上传参考图')
 target=_image(node.get('src'));region=_region(replacement.get('region'),target.size)
 if intent=='generate':
  # Fresh assets use only the dedicated blank canvas; never reinterpret an
  # existing source layer or partial selection as permission to generate anew.
  synthetic=(scene.get('format')=='shijie-scene' and type(scene.get('version')) is int and scene['version']==2 and scene.get('provenance')=='user-image' and original_import and len(scene['nodes'])==1 and ident=='generated-image' and scene.get('groups')==[] and scene.get('edges')==[] and node.get('provenance')=='imported-source' and not any(k in node for k in ('mask','imageReplacement','generationRecord')) and all(scene.get(k)==node['src'] for k in ('source','originalSource','comparisonSource')) and target.size==(scene.get('width'),scene.get('height')))
  if not synthetic or region is not None or replacement.get('selection') is not None:raise ValueError('独立图片生成只能使用专用空白画布，不能直接改写原图或局部选区')
  if target.size not in ((1024,1024),(1536,1024),(1024,1536)):raise ValueError('独立图片生成仅支持 1024×1024、1536×1024 或 1024×1536 画布')
  extrema=target.getextrema()
  if not (extrema[3]==(0,0) or extrema[3]==(255,255) and all(lo==hi for lo,hi in extrema[:3])):raise ValueError('独立图片生成需要完全透明或纯色不透明的空白画布')
 selection,selection_mask=_selection(replacement.get('selection'),region,target.size)
 ref=None
 if reference is not None:
  ref=_image(reference['src']);ref_region=_region(reference.get('region'),ref.size);ref=ref.crop(_box(ref_region,ref.size))
 return {'node':node,'image':target,'region':region,'selection':selection,'selectionMask':selection_mask,'intent':intent,'prompt':prompt.strip(),'reference':ref,'importedSource':original_import}


def process(source,title,progress,cancelled,original_source=None,on_scene=lambda scene:None,resume_scene=None,replacement=None):
 from session_outputs import run_temporary
 from codex_client import CLIENT
 def generate(home):
  try:return _process(source,title,progress,cancelled,original_source or source,home,resume_scene,replacement)
  finally:
   for _ in range(60):
    if CLIENT.close():break
    time.sleep(.05)
   else:raise RuntimeError('图片替换请求尚未结束，保留原工程')
 return run_temporary(generate)


def _process(source,title,progress,cancelled,original_source,home,resume_scene,replacement,*,preserve_identity=False):
 from codex_client import CLIENT
 from engine import png
 if cancelled():raise InterruptedError('已取消')
 spec=validate_replacement(resume_scene,replacement)
 if source!=(resume_scene.get('comparisonSource') or resume_scene.get('source')):raise ValueError('替换工程原图来源不一致')
 if _image(source).size!=(resume_scene.get('width'),resume_scene.get('height')):raise ValueError('替换工程原图尺寸不一致')
 # Original uploads may exceed the downsampled working image dimensions. They
 # are provenance bytes only, never sent to this selected-layer generation.
 stored=resume_scene.get('originalSource') or source
 if original_source!=stored:raise ValueError('替换工程原文件来源不一致')
 if not isinstance(original_source,str) or len(original_source)>36000000 or not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',original_source):raise ValueError('替换工程原文件无效')
 original_bytes=base64.b64decode(original_source.split(',',1)[1],validate=True)
 try:
  with Image.open(io.BytesIO(original_bytes)) as original:original.verify()
 except (OSError,UnidentifiedImageError,Image.DecompressionBombError) as error:raise ValueError('替换工程原文件无法读取') from error
 original_sha=hashlib.sha256(original_bytes).hexdigest()
 recorded=resume_scene.get('recognition',{}).get('sourceOriginalSHA256')
 if recorded and recorded!=original_sha:raise ValueError('替换工程原文件校验不一致')
 if cancelled():raise InterruptedError('已取消')
 before=spec['image'];region=spec['region'];selection=spec['selection'];home=Path(home)
 model_image=before;model_region=region;left=top=0;right,bottom=before.size
 if region is not None:
  # A close context view keeps small edits legible to the model. The padding
  # is context only; only the requested selection is pasted back.
  px=max(8,math.ceil(region['width']*.3));py=max(8,math.ceil(region['height']*.3))
  left=max(0,region['x']-px);top=max(0,region['y']-py)
  right=min(before.width,region['x']+region['width']+px);bottom=min(before.height,region['y']+region['height']+py)
  model_image=before.crop((left,top,right,bottom))
  model_region={**region,'x':region['x']-left,'y':region['y']-top}
 # Model output uses canonical aspect ratios. Preserve native context geometry
 # by centering it in a square, never stretching or cropping the selected area.
 # Whole layers already at 1:1, 3:2 or 2:3 need no padding.
 context_size=model_image.size;pad_x=pad_y=0
 transparent=model_image.getchannel('A').getextrema()[0]<255
 canonical_whole=region is None and (model_image.width==model_image.height or model_image.width*2==model_image.height*3 or model_image.width*3==model_image.height*2)
 if not canonical_whole:
  side=max(context_size);pad_x=(side-context_size[0])//2;pad_y=(side-context_size[1])//2
  canvas=Image.new('RGBA',(side,side),(0,0,0,0) if transparent else (127,127,127,255))
  canvas.paste(model_image,(pad_x,pad_y));model_image=canvas
  if model_region is not None:model_region={**model_region,'x':model_region['x']+pad_x,'y':model_region['y']+pad_y}
 content_box=(pad_x,pad_y,pad_x+context_size[0],pad_y+context_size[1])
 requested_size=(1024,1024) if model_image.width==model_image.height else (1536,1024) if model_image.width>model_image.height else (1024,1536)
 if preserve_identity and spec['reference'] is not None and model_region is not None:
  # The original is stronger evidence than a damaged generated patch. Transparent
  # off-canvas reference pixels retain the existing inferred continuation.
  reference=spec['reference'].resize((model_region['width'],model_region['height']),Image.Resampling.LANCZOS)
  model_image=model_image.copy();model_image.alpha_composite(reference,(model_region['x'],model_region['y']))
 source_path=home/'target.png';model_image.save(source_path);images=[source_path]
 if spec['reference'] is not None:
  ref_path=home/'reference.png';spec['reference'].save(ref_path);images.append(ref_path)
 full_context_index=None
 if preserve_identity and region is not None:
  context_path=home/'complete-context.png';before.save(context_path);images.append(context_path)
  full_context_index=len(images)
 target=home/'candidate.png'
 scope=('第一张附件是原图局部及周围衔接上下文。仅替换附件内的矩形区域（坐标相对于第一张附件左上角，单位为附件像素）：'+json.dumps(model_region,ensure_ascii=False)+'。替换主体必须完整落在此矩形原范围内，头发、额头等轮廓不能上移或越过矩形边界；沿用原对象位置、大小和朝向。矩形外仅用于理解周围衔接，保持不变。') if region else '第一张附件是当前图层完整图片。替换第一张图的整层图片内容。'
 if selection is not None:
  polygons=[selection['points']] if selection['type']=='polygon' else selection['polygons']
  model_polygons=[[[x-left+pad_x,y-top+pad_y] for x,y in points] for points in polygons]
  mask=Image.new('L',model_image.size,0);mask.paste(spec['selectionMask'],(model_region['x'],model_region['y']))
  mask_path=home/'selection-mask.png';mask.save(mask_path);images.append(mask_path)
  scope='第一张附件是原图局部及周围衔接上下文。仅替换以下闭合多边形选区的并集，每个多边形内部按奇偶规则填充，各选区重叠部分仍须替换（坐标相对于第一张附件左上角，单位为附件像素）：'+json.dumps(model_polygons,ensure_ascii=False)+'。最后一张附件是与第一张完全对齐的黑白选区蒙版，白色可替换，黑色必须保留；蒙版仅作范围参考，不能画进输出图。包围框不是替换范围，黑色凹口、自交空洞及套索外全部保持不变。替换主体必须完整落在白色选区内，沿用原对象位置、大小和朝向。'
 layout=f'第一张附件画布为 {model_image.width}×{model_image.height}。原图内容区域为 '+json.dumps({'x':pad_x,'y':pad_y,'width':context_size[0],'height':context_size[1]},ensure_ascii=False)+'；内容区域外是适配画幅的补边，不属于原图内容，不要在补边内生成对象。完整保留附件构图和补边位置，不能把内容放大铺满画布，也不能重排或裁切主体。'
 fresh=spec['intent']=='generate'
 if fresh:
  prompt='用户明确请求从零创作一张全新独立图片。第一张附件是空白画布，仅用于指定输出尺寸和透明背景选项。请按创作描述自由安排主体和构图，充分使用完整画布。'
  if spec['reference'] is not None:prompt+='第二张附件是用户提供的参考素材；仅参考其主体、风格与细节，创作新的独立素材。'
  prompt+=f'输出尺寸 {requested_size[0]}×{requested_size[1]}，交付单张完整图片。'
  prompt+=('输出透明背景 PNG，主体之外保持透明通道。' if transparent else '根据创作描述设计完整背景；未指定时使用协调的背景。')
  prompt+='用户创作描述：'+(spec['prompt'] or '参照参考素材创作新图片。')
 else:
  prompt=('按原图证据修复已有素材，主体身份和原有姿态不得改写。' if preserve_identity else '用户明确请求图片替换，可以依描述和参考图更换指定对象的主体身份；保持其他内容。')+scope+layout+f'输出第一张附件的完整画幅，输出尺寸 {requested_size[0]}×{requested_size[1]}，全部内容与坐标统一等比缩放，不要额外裁切、添加边框或生成对比图。保持原透明背景。'
  if spec['reference'] is not None:prompt+=('第二张附件是该区域的原图证据，必须恢复其中已露出的轮廓、姿态、纹理和明暗，不只是风格参考；第一张中的错误部分必须改正。遮挡物须移除，遮挡后的部分自然补全。' if preserve_identity else '第二张附件是用户参考图已裁选的部分；仅参考该部分的对象与细节，按目标图风格、视角、光照融入指定范围。')
  if preserve_identity and spec['reference'] is not None and model_region is not None:prompt+='第一张附件的修复矩形内已放入原图证据：保留目标对象的真实边线和材质，移除其中的背景及其他遮挡对象；原图画幅之外已有的补全部分保持连续。矩形外保持不变。'
  if full_context_index is not None:prompt+=f'第{full_context_index}张附件是同一物体的完整素材参照，尺寸{before.width}×{before.height}，本次修复在该整图的像素范围为'+json.dumps(region,ensure_ascii=False)+'。仅用于理解整体弧度、透视及连续边线；修复处必须与完整形体自然相接。仍然只输出第一张附件的局部画幅，不能输出或重新设计整件素材。'
  prompt+='用户替换描述：'+(spec['prompt'] or '按参考图替换指定对象。')
 progress(.1,'正在生成独立图片候选…' if fresh else '正在生成图片替换候选…')
 record=CLIENT.generate(prompt,images,target,transparent=transparent,cancelled=cancelled,on_status=lambda message:progress(.2,message),allow_identity_change=not preserve_identity)
 if cancelled():raise InterruptedError('已取消')
 if not isinstance(record,dict) or record.get('actualImageGeneration') is not True:raise ValueError('替换未完成实际图像生成，原工程已保留')
 with Image.open(target) as generated:
  if generated.width*generated.height>36000000 or max(generated.size)>12000:raise ValueError('生成图片尺寸超限')
  candidate=generated.convert('RGBA')
 generated_size=candidate.size
 if candidate.size!=model_image.size:
  # Require the requested aspect ratio. At most one generated pixel (and
  # 0.1% relative ratio error) is permitted for integer-size rounding. Even
  # there, use one shared scale and trim only the fractional outer margin.
  # A normal resize with independent X/Y scales would stretch the subject.
  scale=min(candidate.width/model_image.width,candidate.height/model_image.height)
  crop_width,crop_height=model_image.width*scale,model_image.height*scale
  dx,dy=candidate.width-crop_width,candidate.height-crop_height
  ratio_error=abs(candidate.width*model_image.height-candidate.height*model_image.width)/max(candidate.width*model_image.height,candidate.height*model_image.width)
  if ratio_error>.001 or max(dx,dy)>1.000001:raise ValueError(f'生成图片比例不符合请求：实际 {candidate.width}×{candidate.height}，要求 {requested_size[0]}×{requested_size[1]}（输入画布 {model_image.width}×{model_image.height}，原图内容 {context_size[0]}×{context_size[1]}）。原图已保留；请重试并要求保留完整画布及补边。')
  candidate=candidate.resize(model_image.size,Image.Resampling.LANCZOS,box=(dx/2,dy/2,dx/2+crop_width,dy/2+crop_height))
 patch_alignment=None
 if preserve_identity and region is not None and candidate.width*candidate.height<=6000000:
  from asset_geometry import align_to_source
  aligned=align_to_source(source_path,dict(type='image',x=0,y=0,width=candidate.width,height=candidate.height,src=png(candidate)))
  if aligned is not None:
   ax,ay,aw,ah=(aligned[k] for k in ('x','y','width','height'))
   # ponytail: reuse the full-asset feature matcher for small patch drift only.
   # Actual edits can shear by ~3 degrees. Bound corner movement to 8%;
   # larger redesigns cannot be registered safely and remain subject to QA.
   limit=max(4,min(candidate.size)*.08)
   if max(abs(ax),abs(ay),abs(ax+aw-candidate.width),abs(ay+ah-candidate.height))<=limit:
    im=_image(aligned['src']);sx,sy=aw/im.width,ah/im.height
    candidate=im.transform(model_image.size,Image.Transform.AFFINE,(1/sx,0,-ax/sx,0,1/sy,-ay/sy),Image.Resampling.BICUBIC)
    patch_alignment=aligned['sourceAlignment']
 # The optional binary selection mask copies all four generated channels;
 # never use generated alpha as a paste mask. All exterior RGBA bytes survive.
 if region is not None:
  result=before.copy();box=_box(model_region,model_image.size);patch_image=candidate.crop(box)
  if preserve_identity:
   import numpy as np
   old=np.asarray(before.crop(_box(region,before.size)));new=np.array(patch_image)
   h,w=new.shape[:2];yy,xx=np.indices((h,w));band=min(16,max(1,min(w,h)//8))
   weight=np.minimum.reduce([xx,yy,w-1-xx,h-1-yy])/band;weight=np.clip(weight,0,1)
   # Blend colour only where both surfaces are opaque. Keep generated alpha
   # intact so repaired holes/contours cannot acquire a ghost of the old edge.
   weight[(old[:,:,3]<250)|(new[:,:,3]<250)]=1
   new[:,:,:3]=np.rint(old[:,:,:3]*(1-weight[:,:,None])+new[:,:,:3]*weight[:,:,None]).astype('uint8')
   patch_image=Image.fromarray(new)
  result.paste(patch_image,(region['x'],region['y']),spec['selectionMask']);candidate=result
 else:candidate=candidate.crop(content_box)
 encoded=png(candidate);digest=hashlib.sha256(base64.b64decode(encoded.split(',',1)[1])).hexdigest()
 scene=copy.deepcopy(resume_scene);node=next(n for n in scene['nodes'] if n['id']==spec['node']['id'])
 for key in ('completionBase','completionPlan','sourceFidelity','sourceAlignment','assetReviewChecks','assetReviewAttempts','targetedRepair','colorCorrectionReview','colorCorrectionAttempt','automaticLocalRepair'):node.pop(key,None)
 node.update(src=encoded,provenance=record.get('provider','codex')+'-image-generation',review=True,assetReviewStatus='NOT_REVIEWED',pendingGeneration=False)
 node.pop('reviewIssue',None)
 node['generationRecord']={'actualImageGeneration':True,'provider':record.get('provider','codex'),'transparent':candidate.getchannel('A').getextrema()[0]<255,'sourceOriginalSHA256':original_sha,'generatedAssetSHA256':digest}
 node['generationRecord']['replacementGeometry']={'contextBox':[left,top,right,bottom],'modelCanvasSize':list(model_image.size),'modelContentBox':list(content_box),'requestedSize':list(requested_size),'generatedSize':list(generated_size)}
 if patch_alignment:node['generationRecord']['replacementGeometry']['alignment']=patch_alignment
 if full_context_index is not None:node['generationRecord']['replacementGeometry']['fullAssetContextSize']=list(before.size)
 node['imageReplacement']={'version':1,'region':copy.deepcopy(region),'selection':copy.deepcopy(selection),'inputAssetSHA256':hashlib.sha256(base64.b64decode(spec['node']['src'].split(',',1)[1])).hexdigest(),'importedSource':spec['importedSource']}
 for key in ('delivery','_sessionId','_projectId'):scene.pop(key,None)
 recognition=scene.setdefault('recognition',{})
 recognition['imageReplacement']={'targetId':node['id'],'region':copy.deepcopy(region),'selection':copy.deepcopy(selection),'status':'NOT_REVIEWED','candidate':True}
 if fresh:
  node['imageReplacement']['intent']='generate';recognition['imageReplacement']['intent']='generate'
 for key in ('reviewStatus','status'):
  if recognition.get(key) in ('PASS','MANUAL_CONFIRMED'):recognition[key]='NOT_REVIEWED'
 if cancelled():raise InterruptedError('已取消')
 progress(1,'独立图片候选已生成，请预览后应用' if fresh else '替换候选已生成，请预览后应用')
 return scene
