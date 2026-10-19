"""Complete asset stage and independently inspectable review sheets for the shared workflow."""
import base64,hashlib,io,json,re,uuid
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from codex_client import CLIENT
from layer_review import approved_asset_names
from design_properties import design_fields

COLOR_PRESERVATION='本任务是保真分层提取，不是重新设计、重新渲染或增强画质。保持原图的色相、饱和度、明度、色温、柔和度、阴影和高光强度；禁止自动提亮、美白、加深阴影、提高对比度/饱和度、锐化或改变材质。原图纯色背景保持原纯色，不能新增渐变或摄影棚照明。已完整可见区域尽量原样保留，只有真实缺失区域才补绘。优先颜色与身份准确，不追求比原图更艳或更锐。'

def review_reference_files(qa,checklist):
 qa=Path(qa).resolve();files=[];seen=set()
 for check in checklist['checks']:
  relative=check['file'].replace('\\','/')
  path=(qa.parent/relative).resolve()
  if not path.is_relative_to(qa):raise ValueError('检查图片超出当前检查目录')
  if re.search(r'(?:^|/)独立图层/\d+_',relative):continue  # These exact layers are shown in the atlas.
  if not path.is_file():raise ValueError('缺少实际复核图片：'+check['name'])
  if path not in seen:seen.add(path);files.append(path)
 return files

def append_group_checks(qa,checklist):
 """Bind each actual parent on/off image to the current PSD before vision."""
 proof_file=Path(qa)/'独立回读图层来源.json'
 if not proof_file.is_file():return
 proof=json.loads(proof_file.read_text('utf8'))
 if proof.get('psdSHA256')!=checklist.get('psdSHA256'):raise ValueError('父组检查不对应当前PSD')
 known={c['file'] for c in checklist['checks']}
 for group in proof.get('groups',[]):
  for mode,data in group.get('files',{}).items():
   rel=data['file'];target=(Path(qa)/rel).resolve()
   if not target.is_relative_to(Path(qa).resolve()) or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=data['sha256']:raise ValueError('父组实际检查文件缺失或已变化')
   check_rel=Path(qa).name+'/'+rel
   if check_rel not in known:
    checklist['checks'].append({'name':group['name']+(' · 蒙版样式关闭' if mode=='maskAndEffectsDisabled' else ' · 蒙版样式开启'),'file':check_rel,'status':'PENDING','notes':''})
    known.add(check_rel)
 return [{'name':g['name'],'unsupportedEffects':g.get('unsupportedEffects',[])} for g in proof.get('groups',[])]

def reuse_current_asset(cached,current,structure=None):
 result={**cached,'id':current['id'],'name':current['name']}
 for k in ['gradient','layerStyle','displayMask']:result.pop(k,None)
 result.update(design_fields(current))
 result.update({k:current[k] for k in ['sourceAssetId','sourceEntityId','sourceEntityParts','sourceTextParts'] if k in current})
 if structure is not None and cached['id']!=current['id']:
  folder=Path(structure);prior=folder/('补全_'+cached['id']+'.json')
  if prior.is_file():
   record=json.loads(prior.read_text('utf8'));file=Path(record['file'])
   if not file.resolve().is_relative_to(folder.parent.resolve()) or not file.is_file() or hashlib.sha256(file.read_bytes()).digest()!=hashlib.sha256(base64.b64decode(result['src'].split(',',1)[1])).digest():raise ValueError('复用素材来源记录与当前底稿不一致')
   record['reusedCurrentAttemptFromId']=cached['id']
   (folder/('补全_'+current['id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf8')
 return result

def image_node(file,name,box,background=False,preserve_canvas=False):
 x,y,w,h=box
 with Image.open(file) as generated:
  iw,ih=generated.size
  alpha=generated.convert('RGBA').getchannel('A').getbbox()
  visible=(0,0,iw,ih) if background or preserve_canvas else alpha
  if not background and not alpha:raise ValueError('生成素材「'+name+'」完全透明，不能作为成功素材')
 if not visible:raise ValueError('生成素材「'+name+'」完全透明，不能作为成功素材')
 # ImageGen can return a different canvas ratio. Preserve the complete RGBA,
 # use one scale for both axes, and keep the requested crop centre fixed.
 left,top,right,bottom=visible;vw,vh=right-left,bottom-top
 scale=(max if background else min)(w/vw,h/vh)
 x+=(w-vw*scale)/2-left*scale;y+=(h-vh*scale)/2-top*scale;w,h=iw*scale,ih*scale
 if min(w,h)<1 or max(w,h)>6000 or w*h>6000000:raise ValueError('生成素材「'+name+'」的比例与画布不兼容，不能拉伸或创建超限图层')
 return {'id':uuid.uuid4().hex,'name':name,'type':'image','x':x,'y':y,'width':w,'height':h,'src':'data:image/png;base64,'+base64.b64encode(Path(file).read_bytes()).decode(),'provenance':'codex-image-generation','assetKind':'background' if background else 'complete-asset','inferred':True,'review':True}

def reusable_background(home,original_sha):
 for record_file in Path(home).glob('*/1_过程/02_结构/背景补全来源.json'):
  try:
   record=json.loads(record_file.read_text('utf8'));project=record_file.parents[2]
   file=project/'1_过程/01_素材/完整干净背景.png'
   originals=list((project/'2_输出').glob('*_原图.*'))
   if record.get('actualImageGeneration') and file.is_file() and len(originals)==1 and hashlib.sha256(originals[0].read_bytes()).hexdigest()==original_sha:
    return file,record
  except (OSError,ValueError):continue
 return None

def complete_background(source,scene,assets,structure,cancelled,original_source=None,force_repair=False,on_status=None):
 file=assets/'完整干净背景.png'
 foreground=[{key:n[key] for key in ('name','type','assetKind','sourceVectorId','sourceEntityId','x','y','width','height','fill','z_index') if key in n} for n in scene['nodes'][1:]]
 prompt='从编辑目标提取完整干净背景。去掉所有人物、前景物体、独立标题、文字、印章、标识、按钮、UI及阴影，补齐它们遮住的原有背景。保持画布比例、原有镜头、透视、背景风格、原有景观和光照，不重新设计。没有文字、人物、物体轮廓或色块残留，完整不透明。'+COLOR_PRESERVATION+'原生矢量前景也必须移除；清单中的独立纯色大区域、前景云地和遮罩台面不得因位于底部、面积大或颜色接近背景而保留，不得烘焙进干净背景。按原图遮挡边缘、坐标及z_index识别这些独立实体，补齐其后的背景，不保留重复轮廓；没有证据时不凭空新增前景。当前须移除的独立前景清单（含原生矢量和完整角色，坐标为工作图像素）：'+json.dumps(foreground,ensure_ascii=False)
 record_file=structure/'背景补全来源.json'
 original_sha=hashlib.sha256(Path(original_source or source).read_bytes()).hexdigest()
 if not force_repair and file.is_file() and record_file.is_file() and json.loads(record_file.read_text('utf8')).get('actualImageGeneration'):
  record=json.loads(record_file.read_text('utf8'))
 else:
  cached=None if force_repair else reusable_background(assets.parents[2],original_sha)
  if cached:
   previous,record=cached;file.write_bytes(previous.read_bytes())
   record={**record,'file':str(file),'reusedFrom':str(previous),'reusedSourceOriginalSHA256':original_sha,'generatedAssetSHA256':hashlib.sha256(file.read_bytes()).hexdigest()}
  else:record=CLIENT.generate(prompt,[source],file,cancelled=cancelled,on_status=on_status)
 record['sourceOriginalSHA256']=original_sha
 (structure/'背景补全来源.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf8')
 scene['nodes'][0]=image_node(file,'完整干净背景',[0,0,scene['width'],scene['height']],True)

def reusable_complete_asset(home,original_sha,node):
 for scene_file in Path(home).glob('*/1_过程/02_结构/工程.scene.json'):
  try:
   project=scene_file.parents[2];originals=list((project/'2_输出').glob('*_原图.*'))
   if len(originals)!=1 or hashlib.sha256(originals[0].read_bytes()).hexdigest()!=original_sha:continue
   scene=json.loads(scene_file.read_text('utf8'));qa=project/'1_过程/03_检查';review=json.loads((qa/'Codex画面复核.json').read_text('utf8'))
   proof=json.loads((qa/'独立回读图层来源.json').read_text('utf8'));psd=Path(scene['delivery']['psd'])
   if not psd.is_file() or proof['psdSHA256']!=hashlib.sha256(psd.read_bytes()).hexdigest():continue
   proven={}
   for layer in proof['layers']:
    independent=(qa/layer['file']).resolve()
    if not independent.is_relative_to(qa.resolve()) or not layer.get('nativeComposite'):continue
    if independent.is_file() and hashlib.sha256(independent.read_bytes()).hexdigest()==layer['sha256']:proven[layer['name']]=layer
    elif (qa/'交付与清理记录.json').is_file():
     receipt=json.loads((qa/'交付与清理记录.json').read_text('utf8'))
     if receipt.get('status')=='PASS' and receipt.get('psdSHA256')==proof['psdSHA256']:proven[layer['name']]=layer
   passed=approved_asset_names(scene,review)
   for previous in scene['nodes']:
    if previous.get('type')!='image' or previous.get('assetKind')!=node.get('assetKind') or previous['name'] not in passed or previous['name'] not in proven or previous.get('assetKind')=='background':continue
    x,y,w,h=(node[k] for k in ('x','y','width','height'));px,py,pw,ph=(previous[k] for k in ('x','y','width','height'))
    intersection=max(0,min(x+w,px+pw)-max(x,px))*max(0,min(y+h,py+ph)-max(y,py))
    if intersection/max(1,w*h+pw*ph-intersection)<.75:continue
    record=json.loads((scene_file.parent/('补全_'+previous['id']+'.json')).read_text('utf8'));file=Path(record['file'])
    if not record.get('actualImageGeneration') or not record.get('transparent') or not file.is_file() or not file.resolve().is_relative_to(project.resolve()):continue
    raw=file.read_bytes();registered=base64.b64decode(previous['src'].split(',',1)[1])
    if hashlib.sha256(raw).digest()!=hashlib.sha256(registered).digest():continue
    return file,previous,record
  except (OSError,ValueError,KeyError):continue
 return None

def complete_asset(source,node,assets,structure,cancelled,original_source=None,force_repair=False,on_status=None):
 file=assets/('完整_'+re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',str(node['name']))+'_'+node['id'][:16]+'.png')
 original_sha=hashlib.sha256(Path(original_source or source).read_bytes()).hexdigest()
 cached=None if force_repair else reusable_complete_asset(assets.parents[2],original_sha,node)
 if cached:
  previous,prior,record=cached;file.write_bytes(previous.read_bytes())
  record={**record,'file':str(file),'reusedFrom':str(previous),'sourceOriginalSHA256':original_sha,'generatedAssetSHA256':hashlib.sha256(file.read_bytes()).hexdigest(),'independentVisualReviewSource':'previous actual PSD per-layer PASS'}
  (structure/('补全_'+node['id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf8')
  reused={**prior,'id':node['id'],'name':node['name'],**{k:node[k] for k in ('sourceAssetId','sourceEntityId','sourceEntityParts','sourceTextParts') if k in node},'src':'data:image/png;base64,'+base64.b64encode(file.read_bytes()).decode()}
  for k in ['gradient','layerStyle','displayMask']:reused.pop(k,None)
  return {**reused,**design_fields(node)}
 # Use a local source crop to constrain camera/layout; never paste original RGB into generated alpha.
 from asset_geometry import extraction_bounds
 target=extraction_bounds(node);tx,ty,tw,th=target
 original=Image.open(source).convert('RGB');pad=max(8,round(min(tw,th)*.07))
 x=max(0,int(tx)-pad);y=max(0,int(ty)-pad);right=min(original.width,int(tx+tw)+pad);bottom=min(original.height,int(ty+th)+pad)
 crop=structure/'图像编辑局部参照.png';original.crop((x,y,right,bottom)).save(crop)
 prompt=f'编辑目标是局部参考，只提取完整素材“{node["name"]}”。画布{right-x}x{bottom-y}，保持原位置、比例、颜色、光照、纹理、人物身份与姿势。'+COLOR_PRESERVATION+'去掉背景及非该素材的相邻物体；真正被遮挡的部分补全，但不重设计。白色实体、牌面、布料和皮肤必须保留，不能当背景去掉；字形、手指、发丝和孔洞完整。真实透明背景，不是白底或棋盘格。'
 if node.get('layerStyle'):prompt+='图层样式将单独原生重建：不要把外挂投影、发光、描边、颜色叠加或渐变叠加烘焙进完整底稿。保留物体材质本身的光照与纹理，完整可见/遮挡后实体先补全。'
 if node.get('_repairNotes'):prompt+='本次只修正以下实际逐件复核问题，保留已好的地方：'+json.dumps(node['_repairNotes'],ensure_ascii=False)
 try:record=CLIENT.generate(prompt,[crop],file,transparent=True,cancelled=cancelled,on_status=on_status)
 finally:crop.unlink(missing_ok=True)
 record.update(sourceOriginalSHA256=original_sha,generatedAssetSHA256=hashlib.sha256(file.read_bytes()).hexdigest(),**{k:node[k] for k in ('sourceAssetId','sourceEntityId','sourceEntityParts','sourceTextParts') if k in node})
 (structure/('补全_'+node['id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf8')
 # Padding is reference context, never additional display size. Place the
 # visible alpha against the requested object bounds, preserving source bytes.
 complete=image_node(file,node['name'],target,preserve_canvas=bool(node.get('_fixedExtractionCanvas')))
 complete['id']=node['id'];complete['assetKind']=node.get('assetKind','complete-asset');complete.update({k:node[k] for k in ('sourceAssetId','sourceEntityId','sourceEntityParts','sourceTextParts') if k in node});complete.update(design_fields(node))
 return complete

def review_sheets(scene,qa):
 nodes=scene['nodes'];font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',15);pages=[]
 for start in range(0,len(nodes),8):
  group=nodes[start:start+8];atlas=Image.new('RGB',(1280,((len(group)+3)//4)*370),(35,38,43));draw=ImageDraw.Draw(atlas)
  for offset,n in enumerate(group):
   x=(offset%4)*320;y=(offset//4)*370;draw.text((x+5,y+5),f'{start+offset:02d} {n["name"][:18]}',font=font,fill='white')
   independent=qa/'独立图层'/(f'{start+offset+1:03d}_'+re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',n['name'])+'.png')
   if not independent.is_file():raise RuntimeError('缺少当前PSD实际独立图层：'+n['name'])
   im=Image.open(independent).convert('RGBA');bbox=im.getbbox();im=im.crop(bbox) if bbox else im
   im.thumbnail((310,160))
   for row,color in [(0,(240,240,240)),(1,(24,25,28))]:
    at=(x+5,y+30+row*170);draw.rectangle([at[0],at[1],at[0]+310,at[1]+160],fill=color);atlas.paste(im,at,im)
  file=qa/f'独立图层图册_{start//8+1}.png';atlas.save(file);pages.append(file)
 return pages
