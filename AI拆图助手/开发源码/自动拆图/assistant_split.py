"""User-directed transparent layers, generated once in explicit back-to-front order."""
import copy,math,uuid,time
from datetime import datetime,timezone
from engine import load_source

class SceneDeliveryError(Exception):
 """A failed save/delivery stops the task rather than skipping an object."""

def validate(body):
 if not isinstance(body,dict) or set(body)-{'image','width','height','title','layers','annotations','backgroundOnly','outpaint','projectId','stage','completed','imageLimit','previousPlan'} or not {'image','width','height','title','layers'}<=set(body):raise ValueError('指定拆层参数无效')
 from generation_stages import token as plan_token,validate_completed
 stamp=plan_token(body)
 body=copy.deepcopy(body)
 if 'projectId' in body and (not isinstance(body['projectId'],str) or not __import__('re').fullmatch(r'[A-Za-z0-9_-]{1,160}',body['projectId'])):raise ValueError('来源工程标识无效')
 if 'outpaint' in body and (not isinstance(body['outpaint'],bool) or body['outpaint'] and not body.get('backgroundOnly')):raise ValueError('扩建模式无效')
 if 'backgroundOnly' in body and not isinstance(body['backgroundOnly'],bool):raise ValueError('背景模式无效')
 if not isinstance(body['title'],str) or len(body['title'])>160:raise ValueError('工程名称无效')
 for key in ('width','height'):
  v=body[key]
  if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or not 1<=v<=6000:raise ValueError('拆层画板尺寸无效')
 if not isinstance(body['layers'],list) or not 1<=len(body['layers'])<=128:raise ValueError('请指定1至128个实际位置图层')
 previous=body.get('previousPlan')
 if previous is not None:
  mapped=isinstance(previous,dict) and 'mapping' in previous
  if not isinstance(previous,dict) or set(previous)-{'layers','completed','mapping','annotations','source'} or not {'layers','completed'}<=set(previous) or not isinstance(previous['layers'],list) or not mapped and body['layers'][:len(previous['layers'])]!=previous['layers']:raise ValueError('旧方案与补齐清单不匹配，未重复生成')
  prior={k:copy.deepcopy(body[k]) for k in ('image','width','height','title','annotations') if k in body};prior.update(layers=copy.deepcopy(previous['layers']),completed=copy.deepcopy(previous['completed']))
  frame=previous.get('source');dx=dy=0
  if frame is not None:
   if not mapped or not isinstance(frame,dict) or set(frame)!={'image','width','height','dx','dy'} or any(type(frame[k]) is not int for k in ('width','height','dx','dy')):raise ValueError('旧来源画幅无效')
   dx,dy=frame['dx'],frame['dy']
   if dx<0 or dy<0 or dx+frame['width']>body['width'] or dy+frame['height']>body['height']:raise ValueError('旧来源不在当前扩展画幅内')
   from image_replace import _image
   from PIL import Image
   with _image(frame['image']) as old_image,_image(body['image']) as current_image:
    expected=Image.new('RGBA',current_image.size);expected.paste(old_image.convert('RGBA'),(dx,dy))
    if old_image.size!=(frame['width'],frame['height']) or current_image.size!=(body['width'],body['height']) or expected.tobytes()!=current_image.convert('RGBA').tobytes():raise ValueError('参考像素已改变，保留已有结果，未重新生成')
   prior.update({k:frame[k] for k in ('image','width','height')})
  if 'annotations' in previous:prior['annotations']=copy.deepcopy(previous['annotations'])
  prior=validate(prior)
  if mapped:
   mapping=previous['mapping']
   if not isinstance(mapping,list) or len(mapping)>len(body['layers']) or len(set(i for i in mapping if type(i) is int))!=len(mapping) or any(type(i) is not int or not 0<=i<len(previous['layers']) for i in mapping):raise ValueError('旧图层对应关系无效，未重复生成')
   for j,i in enumerate(mapping):
    expected=copy.deepcopy(previous['layers'][i])
    expected['box']['x']+=dx;expected['box']['y']+=dy
    if expected.get('reuseOf') is not None:
     if expected['reuseOf'] not in mapping:raise ValueError('保留实例缺少原底稿，未重复生成')
     expected['reuseOf']=mapping.index(expected['reuseOf'])
    if body['layers'][j]!=expected:raise ValueError('旧图层内容已改变，未重复生成')
   translated=[]
   for node in prior.get('completed',[]):
    if node['_generationPlanIndex'] in mapping:
     node=copy.deepcopy(node);node['_generationPlanIndex']=mapping.index(node['_generationPlanIndex']);node['x']+=dx;node['y']+=dy;translated.append(node)
   prior['completed']=translated
  if not body.get('completed'):
   body['completed']=copy.deepcopy(prior.get('completed',[]))
   for node in body['completed']:node['_generationPlanToken']=stamp
 validate_completed(body,stamp)
 from source_annotations import mark_margins
 mx,my=mark_margins(body['width'],body['height']) if isinstance(body.get('annotations'),dict) and body['annotations'].get('allowExpand') is True else (0,0)
 seen_layers=set()
 for index,layer in enumerate(body['layers']):
  if not isinstance(layer,dict) or set(layer)-{'name','instruction','box','assetKind','layerType','native','layerStyle','gradient','group','reviewNote','reuseOf','rotation'} or not {'name','instruction','box'}<=set(layer):raise ValueError('拆层清单无效')
  if layer.get('assetKind','complete-asset') not in ('complete-asset','background'):raise ValueError('素材类型无效')
  for key,limit in (('name',100),('instruction',4000)):
   if not isinstance(layer[key],str) or not layer[key].strip() or len(layer[key])>limit:raise ValueError('拆层名称或要求无效')
  b=layer['box']
  if not isinstance(b,dict) or set(b)!={'x','y','width','height'} or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in b.values()):raise ValueError('素材范围无效')
  ref=layer.get('reuseOf')
  if ref is not None:
   if type(ref) is not int or not 0<=ref<index:raise ValueError('同款实例只能引用此前已列出的底稿位置')
   if layer.get('layerType','image') not in ('image','rect','ellipse','path') or body['layers'][ref].get('layerType','image') not in ('image','rect','ellipse','path'):raise ValueError('复用类型无效')
   if (layer.get('layerType','image')=='image')!=(body['layers'][ref].get('layerType','image')=='image'):raise ValueError('不能把矢量底稿复用为图片，或反向转换')
   if body['layers'][ref].get('reuseOf') is not None:raise ValueError('同款实例须直接引用首个底稿，不允许循环或引用实例')
   if layer.get('assetKind')=='background' or body['layers'][ref].get('assetKind')=='background' or body.get('backgroundOnly'):raise ValueError('完整场景背景不能复用为位置实例')
  from annotation_plan import native_node
  try:native_node(layer,'validation')
  except ValueError:pass  # Per-object semantic failures are reported by generate, not by transport validation.
  if body.get('backgroundOnly') and layer.get('layerType','image')!='image':raise ValueError('背景提取只能生成图片底稿')
  signature=(layer['name'],*(b[k] for k in ('x','y','width','height')))
  if signature in seen_layers:raise ValueError('拆层清单包含重复的同名同位置对象')
  seen_layers.add(signature)
  if not body.get('backgroundOnly'):
   if b['width']<=0 or b['height']<=0:raise ValueError('素材范围无效')
   outside=b['x']<0 or b['y']<0 or b['x']+b['width']>body['width'] or b['y']+b['height']>body['height']
   if outside:
    if max(abs(v) for v in b.values())>12000 or b['width']*b['height']>36000000:raise ValueError('素材参考范围超过安全尺寸')
    x=max(0,b['x']);y=max(0,b['y']);right=min(body['width'],b['x']+b['width']);bottom=min(body['height'],b['y']+b['height'])
    if right<=x or bottom<=y:raise ValueError('素材范围未包含任何原图参考，无法识别目标')
    # This box locates visible reference pixels, never bounds completed output.
    layer['instruction']+='；完整形体允许延伸至原画外，旧框不是裁切边界；box仅定位可见参考，不得压缩或裁去补全部分。'
    if layer.get('layerType','image')=='image' and layer.get('reuseOf') is None:layer['box']=b={'x':x,'y':y,'width':right-x,'height':bottom-y}
   if layer.get('assetKind')=='background' and b!={'x':0,'y':0,'width':body['width'],'height':body['height']} and not (previous and previous.get('source') and any(n['_generationPlanIndex']==index for n in body.get('completed',[]))):raise ValueError('场景底稿须覆盖完整参考画布')
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
 import threading
 from concurrent.futures import ThreadPoolExecutor,as_completed
 stop=threading.Event();original_cancelled=cancelled;progress_lock=threading.RLock();report=progress
 cancelled=lambda:stop.is_set() or original_cancelled()
 def progress(value,message):
  with progress_lock:report(value,message)
 pool=None;futures={}
 started=time.monotonic()
 from generation_stages import token as plan_token,kind as phase_kind,groups as phase_groups
 stamp=plan_token(body)
 body=validate(body)
 source=home/'原图.png'
 from image_replace import _image
 with _image(body['image']) as image:image.save(source)
 assets=home/'1_过程/01_素材';assets.mkdir(parents=True)
 structure=home/'1_过程/02_结构';structure.mkdir(parents=True)
 from source_annotations import install
 install(body.get('annotations'),source,structure)
 from incremental_assets import extract_once
 nodes=copy.deepcopy(body.get('completed',[]));by_index={n['_generationPlanIndex']:n for n in nodes};nodes.sort(key=lambda n:n['_generationPlanIndex']);image_requests=0;vector_warnings=[]
 from resource_reuse import image_links,statistics as reuse_statistics
 image_refs,image_sources,image_groups=image_links(body['layers'],body.get('annotations'))
 # Prefer any already-completed same resource, even if its first listed slot is missing.
 for root_index,members in image_groups.items():
  available=[i for i in members if i in by_index]
  if available:
   preferred=max(available,key=lambda i:(by_index[i].get('assetReviewStatus')=='PASS',body['layers'][i]['box']['width']*body['layers'][i]['box']['height']))
   for i in members:
    if i not in by_index:image_refs[i]=preferred
 def register_node(node,index):
  import re
  layer=body['layers'][index]
  number=re.search(r'标注\s*[：:]?\s*0*(\d+)',layer.get('reviewNote','')) or re.match(r'^\s*0*(\d+)[\s·、._]',layer['name'])
  if number:node['annotationNumber']=int(number.group(1))
  node['_generationPlanIndex']=index;node['_generationPlanToken']=stamp;by_index[index]=node;nodes[:]=[by_index[i] for i in sorted(by_index)]
 def partial_scene():
  return {'format':'shijie-scene','version':2,'title':body['title'],'width':body['width'],'height':body['height'],'source':body['image'],'originalSource':body['image'],'comparisonSource':body['image'],'background':None,'nodes':copy.deepcopy(nodes),'groups':phase_groups(body['layers'],nodes),'edges':[],'_partial':True,'_generationStage':{'imageRequests':image_requests,'reuseStats':reuse_statistics(body['layers'],nodes,body.get('annotations'))},'recognition':{'extractionStatus':'INCOMPLETE','reviewStatus':'NOT_REVIEWED','assistantDirected':True,'requestedLayers':copy.deepcopy(body['layers']),'vectorReviewWarnings':copy.deepcopy(vector_warnings),'pendingLayers':copy.deepcopy([layer for i,layer in enumerate(body['layers']) if i not in by_index]),'timing':{'completedAt':datetime.now(timezone.utc).isoformat(),'elapsedMs':round((time.monotonic()-started)*1000)}}}
 def create_image(index,ident):
  layer=body['layers'][index];b=layer['box']
  brief=layer['instruction']+'；用户明确指定的独立层，仅提取本层对象，其他对象和整图背景必须透明；补全被遮挡的完整形体，保持原图尺寸、位置、朝向与风格。本层仅保留主体材质；清除另成层子项并补全表面。已规划的外挂描边、投影与发光不烘焙进底稿，另挂原生样式。'
  creation_index=image_sources.get(index,index);creation_layer=body['layers'][creation_index]
  if creation_index!=index:brief=creation_layer['instruction']+'；'+brief+'；同款只制作一个完整透明素材，以本次指定最大参考位置为准，其他位置由程序复制，不生成一群，不带数量文字。'
  node={'id':ident,'type':'image','name':creation_layer['name'],**creation_layer['box'],'sourceAssetId':ident,'assetKind':'complete-asset','extractionBrief':brief,'_repairNotes':[brief]}
  progress(index/len(body['layers']),'正在提取第 '+str(index+1)+'/'+str(len(body['layers']))+' 层：'+layer['name'])
  if body.get('backgroundOnly') or layer.get('assetKind')=='background':
   from image_provider import CLIENT
   from reference_fidelity import BACKGROUND_PRESERVATION
   from PIL import Image
   from engine import png
   target=assets/('完整背景_'+str(index)+'.png')
   prefix='从附件原图去掉全部UI并补全遮挡的自然场景背景。' if body.get('backgroundOnly') else '生成整套分层的纯净场景底稿，移除本次清单中另成层的全部对象并补齐遮挡；不能把独立对象残留在底稿中。本轮另成层对象清单：'+ '；'.join(item['name']+'：'+item['instruction'] for item in body['layers'] if item is not layer and item.get('assetKind')!='background')+'。'
   policy=BACKGROUND_PRESERVATION if body.get('backgroundOnly') else '场景底稿以原图配色、亮度和笔触为准，仅保留未另成层的环境；本轮独立清单中的自然对象也必须去掉并补齐其后的环境，不能因其是自然对象而重复留在底稿。禁止提亮、增艳、锐化、增加反光或重排环境。'
   prompt=prefix+layer['instruction']+'。保留原横竖构图、未另成层场景对象的原位置和大小，完整画布宽高比例 '+str(body['width'])+':'+str(body['height'])+'，铺满四角的不透明背景，无透明孔洞、羽化边缘、棋盘格、边框，不裁切或重排。'+policy
   refs=[source]
   if b['width']>body['width'] or b['height']>body['height']:
    with Image.open(source) as im:original=im.convert('RGBA')
    offset_x=(int(b['width'])-original.width)//2;offset_y=(int(b['height'])-original.height)//2
    canvas=Image.new('RGB',(int(b['width']),int(b['height'])),(127,127,127));canvas.paste(original,(offset_x,offset_y));guide=assets/('扩建画布_'+str(index)+'.png');canvas.save(guide);canvas.close();refs=[guide]
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
   if not body.get('outpaint'):
    with Image.open(source) as source_frame:
     frame=source_frame.convert('RGBA').getchannel('A').point(lambda v:255 if v>=128 else 0).getbbox()
    if frame and frame!=(0,0,body['width'],body['height']) and b['width']<=body['width'] and b['height']<=body['height']:
     from asset_registration import background_frame
     l,t,r,bottom=frame
     candidate=background_frame(rgba,(l,t,r-l,bottom-t),candidate)
  else:
   if (body.get('annotations') or {}).get('allowExpand') is True:
    from expanded_assets import extract
    candidate=extract(source,node,assets,cancelled,lambda m:progress(index/len(body['layers']),m),annotations=body.get('annotations'))
   else:candidate=extract_once(source,node,assets,structure,cancelled,source,lambda m:progress(index/len(body['layers']),m))
  if creation_index!=index:
   from annotation_plan import reuse_node
   original_provenance=candidate.get('provenance');original_issue=candidate.get('reviewIssue','')
   candidate=reuse_node(layer,candidate,creation_layer,ident,require_approved=False)
   candidate.update(provenance=original_provenance,reviewIssue=original_issue)
  candidate['sourceResourceId']=ident;candidate['resourceMaster']=True;candidate['resourceReferenceIndex']=creation_index
  if candidate.get('provenance')=='source-crop-fallback' or not candidate.get('generationRecord',{}).get('actualImageGeneration'):raise ValueError(layer['name']+'未完整提取，未应用本轮结果；没有自动重试')
  from design_properties import design_fields
  candidate.update(design_fields(layer))
  if layer.get('reviewNote'):candidate.update(reviewIssue=layer['reviewNote'],review=True,assetReviewStatus='NEEDS_REVIEW')
  import re
  annotation_number=re.search(r'标注\s*[：:]?\s*0*(\d+)',layer.get('reviewNote',''))
  if annotation_number:candidate['annotationNumber']=int(annotation_number.group(1))
  candidate.pop('_repairNotes',None)
  return candidate
 if on_scene:
  callback=on_scene
  def on_scene(scene):
   try:callback(scene)
   except InterruptedError:raise
   except Exception as error:raise SceneDeliveryError('已完成图层保存或回传失败，任务已停止；请先取回已有结果') from error
 try:
  # Inspect all requested source paths before publishing any multi-colour object.
  # A body without its failed eye/mark must not appear as a finished object.
  from source_vector import reconstruct,SourceVectorError
  from annotation_plan import native_node
  from PIL import Image
  prepared_native={};native_errors={}
  from material_classification import material_icon
  from source_annotations import summary as annotation_summary
  wrong={m['number'] for m in annotation_summary(body.get('annotations')) if m['layerType']=='vector' and material_icon(m['name'],m.get('planNote',''))} if body.get('annotations') else set()
  import re
  for i,l in enumerate(body['layers']):
   if i in by_index or body.get('stage','all') not in ('all',phase_kind(l)):continue
   try:native_node(l,'validation')
   except ValueError as error:native_errors[i]=str(error)
  for i,l in enumerate(body['layers']):
   if body.get('stage','all') not in ('all','vector'):continue
   number=re.match(r'^\s*0*(\d+)[\s·、._]',l['name'])
   if phase_kind(l)=='vector' and i not in by_index and (material_icon(l['name'],l['instruction']) or number and int(number.group(1)) in wrong):native_errors[i]='材质图标分类冲突：应完整提取图片，未发布近似矢量；请先修正图标分类，不会自动生图'
  with Image.open(source) as original:
   for index,layer in enumerate(body['layers']):
    if cancelled():raise InterruptedError('已停止指定拆层')
    if index in native_errors or index in by_index or layer.get('layerType')!='path' or layer.get('reuseOf') is not None or body.get('stage','all') not in ('all','vector'):continue
    progress(0,'正在按原图检查矢量轮廓：'+layer['name'])
    companions=[];component=False;b=layer['box']
    for other_index,part in enumerate(body['layers']):
     q=part['box']
     if not layer.get('group') or part.get('group')!=layer['group'] or part.get('layerType') not in ('path','rect','ellipse') or part.get('reuseOf') is not None or other_index==index:continue
     overlap=max(0,min(b['x']+b['width'],q['x']+q['width'])-max(b['x'],q['x']))*max(0,min(b['y']+b['height'],q['y']+q['height'])-max(b['y'],q['y']))
     if other_index>index and q['width']*q['height']<b['width']*b['height']*.25 and overlap/max(1,q['width']*q['height'])>.5:companions.append(part)
     if other_index<index and b['width']*b['height']<q['width']*q['height']*.25 and overlap/max(1,b['width']*b['height'])>.5:component=True
    try:prepared_native[index]=reconstruct(original,layer,native_node(layer,'source-native-'+str(index)),companions,not component)
    except (SourceVectorError,ValueError) as error:native_errors[index]=str(error)
  def linked_parts(a,b):
   if not a.get('group') or a.get('group')!=b.get('group'):return False
   a,b=a['box'],b['box'];overlap=max(0,min(a['x']+a['width'],b['x']+b['width'])-max(a['x'],b['x']))*max(0,min(a['y']+a['height'],b['y']+b['height'])-max(a['y'],b['y']))
   return overlap/max(1,min(a['width']*a['height'],b['width']*b['height']))>.5
  changed=True
  while changed:
   changed=False
   for index,part in enumerate(body['layers']):
    if index in native_errors or index in by_index or part.get('layerType') not in ('path','rect','ellipse') or body.get('stage','all') not in ('all','vector'):continue
    failed=next((j for j in native_errors if linked_parts(part,body['layers'][j]) or part.get('reuseOf')==j),None)
    if failed is not None:
     native_errors[index]='同一对象的另一色块“'+body['layers'][failed]['name']+'”未通过原图检查，暂不发布残缺对象'
     prepared_native.pop(index,None);changed=True
  vector_warnings[:]=[{'index':i,'name':body['layers'][i]['name'],'reason':reason} for i,reason in sorted(native_errors.items())]
  from image_provider import settings
  roots=[i for i,l in enumerate(body['layers']) if i not in by_index and i not in native_errors and phase_kind(l)=='image' and body.get('stage','all') in ('all','image') and image_refs.get(i,l.get('reuseOf')) is None]
  if body.get('imageLimit',0):roots=roots[:body['imageLimit']]
  if len(roots)>1 and settings()['provider']=='aimake':
   progress(0,'同时处理本次选择的'+str(len(roots))+'款亿创素材；各自提交、独立回传，同款只制作一次')
   pool=ThreadPoolExecutor(max_workers=len(roots),thread_name_prefix='aimake-object')
   for i in roots:
    if cancelled():raise InterruptedError('已停止提交；已有亿创任务号保留')
    futures[i]=pool.submit(create_image,i,'assistant-'+uuid.uuid4().hex)
    image_requests+=1
  def selected_indices():
   if not futures:
    yield from range(len(body['layers']));return
   yield from (i for i,l in enumerate(body['layers']) if phase_kind(l)!='image')
   lookup={future:i for i,future in futures.items()}
   for future in as_completed(lookup):yield lookup[future]
   yield from (i for i,l in enumerate(body['layers']) if phase_kind(l)=='image' and i not in futures)
  for index in selected_indices():
   layer=body['layers'][index]
   if cancelled():raise InterruptedError('已停止指定拆层')
   if index in native_errors:continue
   if index in by_index or body.get('stage','all')!='all' and phase_kind(layer)!=body['stage']:continue
   if index not in futures and phase_kind(layer)=='image' and layer.get('reuseOf') is None and index not in image_refs and body.get('imageLimit',0) and image_requests>=body['imageLimit']:continue
   try:
    ref=image_refs.get(index,layer.get('reuseOf'))
    if ref is not None and ref not in by_index:raise ValueError('同款底稿未完成，保留实例待修复')
    if phase_kind(layer)=='image' and ref is None and index not in futures:image_requests+=1
    b=layer['box'];ident='assistant-'+uuid.uuid4().hex
    from annotation_plan import native_node
    if ref is not None:
     base=by_index[ref]
     if base['type']=='image' and base.get('assetReviewStatus')!='PASS':
      from acceptance import review_asset
      check=review_asset(source,base,structure,cancelled,lambda message:progress(index/len(body['layers']),message))
      if check.get('status')!='PASS':raise ValueError('同款图片底稿尚未通过验收，保留已有结果与待办，不重复生图')
      base.update(assetReviewStatus='PASS',assetReview=check)
     from annotation_plan import reuse_node
     candidate=reuse_node(layer,base,body['layers'][ref],ident)
    else:candidate=native_node(layer,ident)
    if index in prepared_native:candidate=copy.deepcopy(prepared_native[index]);candidate['id']=ident
    if candidate is not None:
     register_node(candidate,index)
     progress((index+1)/len(body['layers']),('已复制同款到独立位置：' if ref is not None and candidate['type']=='image' else '已创建原生层：')+layer['name'])
     if on_scene:on_scene(partial_scene())
     continue
    candidate=futures[index].result() if index in futures else create_image(index,ident)
    if cancelled():raise InterruptedError('已停止指定拆层')
    register_node(candidate,index)
    if on_scene:on_scene(partial_scene())
   except InterruptedError:raise
   except (ValueError,RuntimeError,OSError) as error:
    vector_warnings.append({'index':index,'name':layer['name'],'reason':str(error)[:240]})
    progress((index+1)/len(body['layers']),'本项待修复，继续其他对象：'+layer['name'])
    if on_scene:on_scene(partial_scene())
 except Exception as error:
  if nodes:error.partial=partial_scene()
  raise
 finally:
  if pool:
   stop.set();pool.shutdown(wait=True,cancel_futures=True)
 if original_cancelled():raise InterruptedError('已停止指定拆层')
 result={'format':'shijie-scene','version':2,'title':body['title'],'width':body['width'],'height':body['height'],'source':body['image'],'originalSource':body['image'],'comparisonSource':body['image'],'background':None,'nodes':nodes,'groups':phase_groups(body['layers'],nodes),'edges':[],'recognition':{'extractionStatus':'COMPLETED','reviewStatus':'NOT_REVIEWED','assistantDirected':True,'requestedLayers':body['layers']}}
 if vector_warnings:result['recognition'].update(vectorReviewWarnings=vector_warnings,reviewStatus='NEEDS_REVIEW')
 if len(nodes)<len(body['layers']):
  result['_partial']=True;result['recognition'].update(extractionStatus='INCOMPLETE',pendingLayers=copy.deepcopy([layer for i,layer in enumerate(body['layers']) if i not in by_index]))
 result['_generationStage']={'stage':body.get('stage','all'),'completed':len(nodes),'total':len(body['layers']),'imageRequests':image_requests,'reuseStats':reuse_statistics(body['layers'],nodes,body.get('annotations')),'token':stamp}
 if body.get('backgroundOnly') and nodes and not nodes[0].get('positionReviewRequired'):
  result.update(width=nodes[0]['width'],height=nodes[0]['height'],source=nodes[0]['src'],comparisonSource=nodes[0]['src'],originalSource=nodes[0]['src'],originalSize={'width':nodes[0]['width'],'height':nodes[0]['height']})
 if any(n.get('boundaryReviewRequired') or n.get('positionReviewRequired') for n in nodes):
  result['recognition']['reviewStatus']='NEEDS_REVIEW'
  for n in nodes:
   if n.get('boundaryReviewRequired') or n.get('positionReviewRequired'):n.update(review=True,assetReviewStatus='NEEDS_REVIEW')
 # Outpaint must preserve source pixels; a different returned aspect leaves this unfinished.
 if body.get('outpaint') and nodes and nodes[0].get('positionReviewRequired'):
  result['_partial']=True;result['recognition'].update(extractionStatus='INCOMPLETE',pendingLayers=copy.deepcopy(body['layers']))
 result['recognition']['timing']={'completedAt':datetime.now(timezone.utc).isoformat(),'elapsedMs':round((time.monotonic()-started)*1000)}
 progress(1,'部分对象待修复：参数、提取或分类检查失败，已保留完成层，请核对分类和范围' if vector_warnings else '所选阶段已完成，等待继续下一阶段' if result.get('_partial') else '指定素材层已生成，等待预览确认')
 return result
