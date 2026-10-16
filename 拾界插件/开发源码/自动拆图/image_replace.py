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


def validate_replacement(scene,replacement):
 from incremental_assets import effective_locked_ids
 if not isinstance(scene,dict) or not isinstance(scene.get('nodes'),list) or not isinstance(replacement,dict) or set(replacement)-{'targetId','region','prompt','reference'}:raise ValueError('替换参数无效')
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
 ref=None
 if reference is not None:
  ref=_image(reference['src']);ref_region=_region(reference.get('region'),ref.size);ref=ref.crop(_box(ref_region,ref.size))
 return {'node':node,'image':target,'region':region,'prompt':prompt.strip(),'reference':ref,'importedSource':original_import}


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


def _process(source,title,progress,cancelled,original_source,home,resume_scene,replacement):
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
 before=spec['image'];region=spec['region'];home=Path(home)
 model_image=before;model_region=region
 if region is not None:
  # A close context view keeps small edits legible to the model. The padding
  # is context only; only the original requested rectangle is pasted back.
  px=max(8,math.ceil(region['width']*.3));py=max(8,math.ceil(region['height']*.3))
  left=max(0,region['x']-px);top=max(0,region['y']-py)
  right=min(before.width,region['x']+region['width']+px);bottom=min(before.height,region['y']+region['height']+py)
  model_image=before.crop((left,top,right,bottom))
  model_region={**region,'x':region['x']-left,'y':region['y']-top}
 source_path=home/'target.png';model_image.save(source_path);images=[source_path]
 if spec['reference'] is not None:
  ref_path=home/'reference.png';spec['reference'].save(ref_path);images.append(ref_path)
 target=home/'candidate.png'
 scope=('第一张附件是原图局部及周围衔接上下文。仅替换附件内的矩形区域（坐标相对于第一张附件左上角，单位为附件像素）：'+json.dumps(model_region,ensure_ascii=False)+'。替换主体必须完整落在此矩形原范围内，头发、额头等轮廓不能上移或越过矩形边界；沿用原对象位置、大小和朝向。矩形外仅用于理解周围衔接，保持不变。') if region else '第一张附件是当前图层完整图片。替换第一张图的整层图片内容。'
 prompt='用户明确请求图片替换，可以依描述和参考图更换指定对象的主体身份；保持其他内容。'+scope+f'输出第一张附件的完整画幅，尺寸 {model_image.width}×{model_image.height}，不要额外裁切、添加边框或生成对比图。保持原透明背景和画幅。'
 if spec['reference'] is not None:prompt+='第二张附件是用户参考图已裁选的部分；仅参考该部分的对象与细节，按目标图风格、视角、光照融入指定范围。'
 prompt+='用户替换描述：'+(spec['prompt'] or '按参考图替换指定对象。')
 transparent=model_image.getchannel('A').getextrema()[0]<255
 progress(.1,'正在生成图片替换候选…')
 record=CLIENT.generate(prompt,images,target,transparent=transparent,cancelled=cancelled,on_status=lambda message:progress(.2,message),allow_identity_change=True)
 if cancelled():raise InterruptedError('已取消')
 if not isinstance(record,dict) or record.get('actualImageGeneration') is not True:raise ValueError('替换未完成实际图像生成，原工程已保留')
 with Image.open(target) as generated:
  if generated.width*generated.height>36000000 or max(generated.size)>12000:raise ValueError('生成图片尺寸超限')
  candidate=generated.convert('RGBA')
 if candidate.size!=model_image.size:
  # Require the requested aspect ratio. At most one generated pixel (and
  # 0.1% relative ratio error) is permitted for integer-size rounding. Even
  # there, use one shared scale and trim only the fractional outer margin.
  # A normal resize with independent X/Y scales would stretch the subject.
  scale=min(candidate.width/model_image.width,candidate.height/model_image.height)
  crop_width,crop_height=model_image.width*scale,model_image.height*scale
  dx,dy=candidate.width-crop_width,candidate.height-crop_height
  ratio_error=abs(candidate.width*model_image.height-candidate.height*model_image.width)/max(candidate.width*model_image.height,candidate.height*model_image.width)
  if ratio_error>.001 or max(dx,dy)>1.000001:raise ValueError('生成图片比例与原图不一致，已保留原图；请重试并要求保持原图宽高比')
  candidate=candidate.resize(model_image.size,Image.Resampling.LANCZOS,box=(dx/2,dy/2,dx/2+crop_width,dy/2+crop_height))
 # Paste without an alpha mask: preserve generated RGBA inside the rectangle,
 # and every original RGBA byte outside, including RGB under transparent pixels.
 if region is not None:
  result=before.copy();box=_box(model_region,model_image.size);result.paste(candidate.crop(box),(region['x'],region['y']));candidate=result
 encoded=png(candidate);digest=hashlib.sha256(base64.b64decode(encoded.split(',',1)[1])).hexdigest()
 scene=copy.deepcopy(resume_scene);node=next(n for n in scene['nodes'] if n['id']==spec['node']['id'])
 node.update(src=encoded,provenance='codex-image-generation',review=True,assetReviewStatus='NOT_REVIEWED',pendingGeneration=False)
 node.pop('reviewIssue',None)
 node['generationRecord']={'actualImageGeneration':True,'transparent':candidate.getchannel('A').getextrema()[0]<255,'sourceOriginalSHA256':original_sha,'generatedAssetSHA256':digest}
 node['imageReplacement']={'version':1,'region':copy.deepcopy(region),'inputAssetSHA256':hashlib.sha256(base64.b64decode(spec['node']['src'].split(',',1)[1])).hexdigest(),'importedSource':spec['importedSource']}
 for key in ('delivery','_sessionId','_projectId'):scene.pop(key,None)
 recognition=scene.setdefault('recognition',{})
 recognition['imageReplacement']={'targetId':node['id'],'region':copy.deepcopy(region),'status':'NOT_REVIEWED','candidate':True}
 for key in ('reviewStatus','status'):
  if recognition.get(key) in ('PASS','MANUAL_CONFIRMED'):recognition[key]='NOT_REVIEWED'
 if cancelled():raise InterruptedError('已取消')
 progress(1,'替换候选已生成，请预览后应用')
 return scene
