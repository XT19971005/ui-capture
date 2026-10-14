"""Check native PSD structure and bitmap consistency; never imply visual acceptance."""
import argparse,json,sys,hashlib,math,copy,re
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('psd');ap.add_argument('--project',required=True);ap.add_argument('--psd-tools-path')
a=ap.parse_args()
if a.psd_tools_path:sys.path.insert(0,a.psd_tools_path)
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.composite import paint as native_paint
from psd_tools.terminology import Key,Enum
from psd_gradient_compat import install as install_gradient_compat
install_gradient_compat()
root=Path(a.project);DIRS=__import__('project_dirs').project_dirs(root);qa=root/(DIRS['qa']);qa.mkdir(exist_ok=True)
job=json.loads((root/(DIRS['plan']+'/项目.json')).read_text('utf8'));psd=PSDImage.open(a.psd)
source_report_file=qa/'来源检查.json';source_report=json.loads(source_report_file.read_text('utf8')) if source_report_file.exists() else {}
def sha(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()
source_report_valid=source_report.get('projectManifestSHA256')==sha(root/(DIRS['plan']+'/项目.json')) and source_report.get('psdSHA256')==sha(a.psd)
layer_dir=qa/'独立图层';layer_dir.mkdir(exist_ok=True)
errors=[];asset_errors=[];counts={'groups':0,'text':0,'vector':0,'bitmap':0};layer_rows=[];complete_assets=[];vector_checks=[];native_vector_checks=[];effect_checks=[];gradient_checks=[]
gradient_dir=qa/'原生渐变图层';gradient_dir.mkdir(exist_ok=True)
def flattened(items):
 for s in items:
  if s.get('kind')=='group':yield from flattened(s.get('children',[]))
  else:yield s
specs=list(flattened(job['layers']))
actual=list(psd.descendants());leaves=[l for l in actual if not l.is_group()]
if psd.size!=(job['width'],job['height']):errors.append('canvas mismatch')
if len(leaves)!=len(specs):errors.append('leaf count mismatch')
def expected_groups(items):
 for s in items:
  if s.get('kind')=='group':
   yield s
   yield from expected_groups(s.get('children',[]))
mask_checks=[]
for s,l in zip(expected_groups(job['layers']),[l for l in actual if l.is_group()]):
 if s['name']!=l.name:errors.append('group name/order mismatch: '+s['name'])
 if s.get('native',{}).get('effects'):
  expected=s['native']['effects'];mapping={'dropShadow':'DropShadow','innerShadow':'InnerShadow','outerGlow':'OuterGlow','innerGlow':'InnerGlow','stroke':'Stroke','solidFill':'ColorOverlay','gradientOverlay':'GradientOverlay'}
  if l.effects.enabled==bool(expected.get('disabled',False)):errors.append('group effect master switch changed: '+l.name)
  for key,kind in mapping.items():
   values=expected.get(key,[]);values=values if isinstance(values,list) else [values];found=[e for e in l.effects if type(e).__name__==kind]
   if len(values)!=len(found):errors.append('group native effects missing: '+l.name+' '+kind)
   for e,f in zip(values,found):
    if f.enabled!=bool(e.get('enabled',True)):errors.append('group effect enabled switch changed: '+l.name+' '+kind)
  effect_checks.append({'name':l.name,'group':True,'masterEnabled':l.effects.enabled,'effects':[{'kind':type(e).__name__,'enabled':e.enabled} for e in l.effects]})
 if s.get('displayMask'):
  m=s['displayMask'];present=l.has_mask();disabled=l.mask.disabled if present else None
  if not present or disabled!=bool(m.get('disabled',False)):errors.append('display mask missing/state changed: '+s['name'])
  if present and l.mask.topil() is None:errors.append('display mask pixels missing: '+s['name'])
  mask_checks.append({'name':s['name'],'nativeGroupMask':present,'disabled':disabled,'reason':m['reason']})
for l in actual:
 vector=l._record.tagged_blocks.get_data(b'SoCo') is not None or l._record.tagged_blocks.get_data(b'GdFl') is not None
 kind='groups' if l.is_group() else 'text' if l.kind=='type' else 'vector' if vector else 'bitmap'
 counts[kind]+=1;layer_rows.append({'name':l.name,'kind':kind,'bbox':l.bbox,'visible':l.visible})
for index,(s,l) in enumerate(zip(specs,leaves)):
 isolated=l.topil()
 if isolated is not None:
  safe_name=''.join(c if c not in '\\/:*?"<>|' else '_' for c in l.name)
  isolated.save(layer_dir/(f'{index+1:03d}_'+safe_name+'.png'))
 if s['name']!=l.name:errors.append('name/order mismatch: '+s['name'])
 if s.get('native',{}).get('effects'):
  expected_effects=s['native']['effects'];actual_effects=list(l.effects);mapping={'outerGlow':'OuterGlow','innerGlow':'InnerGlow','dropShadow':'DropShadow','innerShadow':'InnerShadow','stroke':'Stroke','solidFill':'ColorOverlay','gradientOverlay':'GradientOverlay','patternOverlay':'PatternOverlay','bevel':'BevelEmboss','satin':'Satin'}
  if not expected_effects.get('disabled',False):
   for key,kind in mapping.items():
    values=expected_effects.get(key,[]);values=values if isinstance(values,list) else [values]
    values=[e for e in values if e and e.get('enabled',True) and e.get('present',True)]
    actual=[e for e in actual_effects if type(e).__name__==kind and e.enabled]
    if len(actual)!=len(values):errors.append('native layer effects missing or disabled: '+l.name+' '+kind)
    for expected_fx,actual_fx in zip(values,actual):
     if expected_fx.get('size') and abs(actual_fx.size-expected_fx['size']['value'])>.02:errors.append('native effect size changed: '+l.name)
     if 'opacity' in expected_fx and abs(actual_fx.opacity-expected_fx['opacity']*100)>1:errors.append('native effect opacity changed: '+l.name)
  effect_checks.append({'name':l.name,'masterEnabled':l.effects.enabled,'effects':[{'kind':type(e).__name__,'enabled':e.enabled} for e in actual_effects]})
 if s['kind']=='text':
  if l.kind!='type' or not l.engine_dict:errors.append('not native editable text: '+l.name)
  else:
   expected=(s.get('native',{}).get('text',{}).get('text') or s.get('text',{}).get('value','')).rstrip('\r')
   if l.text.rstrip('\r')!=expected:errors.append('text content mismatch: '+l.name)
  if s.get('cleanTextSource'):
   proof=s['cleanTextSource'];cache_file=root/s['cache'];pixels=np.array(Image.open(cache_file).convert('RGBA'));valid=pixels[:,:,3]>128
   if sha(cache_file)!=proof['cacheSHA256']:asset_errors.append('clean text cache changed: '+l.name)
   color=proof['fillColor'];target=np.array([color['r'],color['g'],color['b']])
   if valid.any() and int(np.abs(pixels[:,:,:3][valid].astype('int16')-target).max())>4:asset_errors.append('text cache contains background colors instead of pure glyph pixels: '+l.name)
   if np.any(pixels[0,:,3]) or np.any(pixels[-1,:,3]) or np.any(pixels[:,0,3]) or np.any(pixels[:,-1,3]):asset_errors.append('text cache touches its boundary; glyph may be clipped: '+l.name)
 if s['kind']=='shape' and not(l._record.tagged_blocks.get_data(b'SoCo') is not None or l._record.tagged_blocks.get_data(b'GdFl') is not None):errors.append('not native vector: '+l.name)
 if s['kind']=='shape' and isolated is not None and not l.effects.enabled:
  # Whole-canvas MAE hides damaged small logos. Compare each native path's
  # opaque interior with its own cache, allowing only rasterizer edge pixels.
  from scipy.ndimage import binary_erosion,binary_dilation
  native_image=l.composite(viewport=l.bbox,force=True)
  if native_image is None:errors.append('native vector cannot render: '+l.name)
  else:
   expected_alpha=np.array(isolated.convert('RGBA'))[:,:,3]
   actual_alpha=np.array(native_image.convert('RGBA'))[:,:,3]
   if expected_alpha.shape!=actual_alpha.shape:errors.append('native vector bounds changed: '+l.name)
   else:
    lost=int(np.count_nonzero(binary_erosion(expected_alpha>240)&(actual_alpha<20)))
    added=int(np.count_nonzero(binary_erosion(actual_alpha>240)&(expected_alpha<20)))
    # Erosion has no interior for a 1px/2px stroke. Keep a one-pixel
    # rasterizer tolerance around visible ink instead of erasing that stroke
    # from the requirement: complete thin components must still exist.
    edge_tolerance=np.ones((3,3),dtype=bool)
    thin_lost=int(np.count_nonzero((expected_alpha>128)&~binary_dilation(actual_alpha>20,structure=edge_tolerance)))
    thin_added=int(np.count_nonzero((actual_alpha>128)&~binary_dilation(expected_alpha>20,structure=edge_tolerance)))
    union=np.count_nonzero((expected_alpha>128)|(actual_alpha>128))
    iou=float(np.count_nonzero((expected_alpha>128)&(actual_alpha>128))/max(1,union))
    native_vector_checks.append({'name':l.name,'nativeAlphaIoU':iou,'opaqueInteriorPixelsLost':lost,'opaqueInteriorPixelsAdded':added,'inkPixelsLostOutsideEdgeTolerance':thin_lost,'inkPixelsAddedOutsideEdgeTolerance':thin_added,'edgeTolerancePixels':1})
    if lost or added or thin_lost or thin_added:errors.append('native vector lost strokes or filled holes versus its layer cache: '+l.name)
 if s.get('gradient'):
  descriptor=l._record.tagged_blocks.get_data(b'GdFl');expected=s['gradient'];row={'name':l.name,'type':expected.get('style','linear'),'nativeGradientPresent':descriptor is not None}
  if descriptor is None:errors.append('native editable gradient missing: '+l.name)
  else:
   style=expected.get('style','linear');actual_style=descriptor.get(b'Type').enum
   if actual_style!=(Enum.Radial if style=='radial' else Enum.Linear):errors.append('native gradient type changed: '+l.name)
   axis=expected['axis'];width=l.bbox[2]-l.bbox[0];height=l.bbox[3]-l.bbox[1]
   if style=='radial':angle=0.;scale=2*axis[5]/width
   else:
    dx,dy=axis[2]-axis[0],axis[3]-axis[1];length=math.hypot(dx,dy);angle=-math.degrees(math.atan2(dy,dx));scale=length/(abs(dx/length)*width+abs(dy/length)*height)
   actual_angle=float(descriptor.get(b'Angl',0));actual_scale=float(descriptor.get(b'Scl ',100))
   if abs(actual_angle-angle)>.001:errors.append('native gradient direction changed: '+l.name)
   if abs(actual_scale-round(scale*100))>.01:errors.append('native gradient scale changed: '+l.name)
   stops=descriptor.get(b'Grad').get(b'Clrs');row.update(angle=actual_angle,scalePercent=actual_scale,colorStops=[])
   if len(stops)!=len(expected['stops']):errors.append('native gradient stops missing: '+l.name)
   for entry,(position,color) in zip(stops,expected['stops']):
    actual_rgb=[float(entry.get(b'Clr ').get(key)) for key in (b'Rd  ',b'Grn ',b'Bl  ')];target=[int(color[n:n+2],16) for n in (1,3,5)]
    if max(abs(x-y) for x,y in zip(actual_rgb,target))>.1 or abs(int(entry.get(b'Lctn'))-round(position*4096))>1:errors.append('native gradient color/location changed: '+l.name)
    row['colorStops'].append({'position':int(entry.get(b'Lctn'))/4096,'rgb':actual_rgb})
   alpha_stops=descriptor.get(b'Grad').get(b'Trns');expected_alpha=expected.get('opacityStops',[[0,1],[1,1]])
   if len(alpha_stops)!=len(expected_alpha):errors.append('native gradient opacity stops missing: '+l.name)
   row['opacityStops']=[]
   for entry,(position,opacity) in zip(alpha_stops,expected_alpha):
    actual_opacity=float(entry.get(b'Opct'))/100
    if abs(actual_opacity-opacity)>.005 or abs(int(entry.get(b'Lctn'))-round(position*4096))>1:errors.append('native gradient opacity changed: '+l.name)
    row['opacityStops'].append({'position':int(entry.get(b'Lctn'))/4096,'opacity':actual_opacity})
   rendered_gradient=l.composite(viewport=(0,0,psd.width,psd.height),force=True).crop(l.bbox)
   if rendered_gradient is not None:rendered_gradient.save(gradient_dir/(f'{index+1:03d}_'+l.name.replace('/','_')+'.png'));row['independentImage']=(DIRS['qa']+'/原生渐变图层/')+f'{index+1:03d}_'+l.name.replace('/','_')+'.png'
  gradient_checks.append(row)
 if s.get('native',{}).get('effects',{}).get('gradientOverlay'):
  rendered_gradient=l.composite(viewport=(0,0,psd.width,psd.height),force=True).crop(l.bbox)
  if rendered_gradient is not None:rendered_gradient.save(gradient_dir/(f'{index+1:03d}_'+l.name.replace('/','_')+'.png'))
 if s.get('integrityRegion'):
  reg=s['integrityRegion'];x,y,right,bottom=reg['box']
  src=np.array(Image.open(root/job['source']).convert('RGB'))[y:bottom,x:right].astype('int16')
  if reg.get('rules'):
   ref=np.ones(src.shape[:2],bool)
   for k,key in enumerate(['r','g','b']):
    low,high=reg['rules'].get(key,[0,255]);ref&=(src[:,:,k]>=low)&(src[:,:,k]<=high)
  elif reg.get('mode')=='cream':ref=(src[:,:,0]>190)&(src[:,:,1]>165)&(src[:,:,2]>100)
  elif reg.get('mode')=='white':ref=(src[:,:,0]>188)&(src[:,:,1]>175)&(src[:,:,2]>168)
  else:ref=(src[:,:,0]<185)&(src[:,:,1]<85)&(src[:,:,2]<75)
  full=Image.new('RGBA',psd.size);full.paste(l.topil().convert('RGBA'),l.bbox[:2])
  rendered=np.array(full)[y:bottom,x:right,3]>127
  union=int(np.count_nonzero(ref|rendered));iou=float(np.count_nonzero(ref&rendered)/max(1,union))
  boundary_mismatch=None
  if reg.get('boundaryTolerance'):
   from scipy.ndimage import binary_dilation
   radius=reg['boundaryTolerance'];footprint=np.ones((radius*2+1,radius*2+1),dtype=bool)
   boundary_mismatch=int(np.count_nonzero(ref & ~binary_dilation(rendered,structure=footprint))+np.count_nonzero(rendered & ~binary_dilation(ref,structure=footprint)))
  vector_checks.append({'name':l.name,'referenceIoU':iou,'pixelsOutsideBoundaryTolerance':boundary_mismatch})
  if iou<reg.get('minIoU',.9) and boundary_mismatch!=0:asset_errors.append('vector lost source lettering or filled its holes: '+l.name)
 if s.get('role') in ('character','background','artwork'):
  if l.vector_mask is not None or l.mask is not None:asset_errors.append('complete asset has unexpected mask: '+l.name)
  if s.get('completeAssetSHA256') and hashlib.sha256((root/s['file']).read_bytes()).hexdigest()!=s['completeAssetSHA256'].lower():asset_errors.append('complete asset source was altered: '+l.name)
  if s.get('completeAssetSource'):
   row=next((v for v in source_report.get('checks',[]) if v['index']==index),None)
   if not source_report_valid or not row or row['assetSHA256']!=sha(root/s['file']) or row['sourceSHA256']!=s['completeAssetSource']['sha256'].lower() or row['referenceSHA256']!=sha(root/row['reference']):
    asset_errors.append('missing or stale source RGBA proof; run pipeline verify: '+l.name)
    expected=Image.new('RGBA',psd.size)
   else:expected=Image.open(root/row['reference']).convert('RGBA')
  else:
   im=Image.open(root/(s.get('cache') or s['file'])).convert('RGBA')
   if not s.get('cache') and ('width' in s or 'height' in s):im=im.resize((s.get('width',im.width),s.get('height',im.height)),Image.Resampling.BILINEAR)
   expected=Image.new('RGBA',psd.size);expected.paste(im,(s.get('x',0),s.get('y',0)))
  result=Image.new('RGBA',psd.size);result.paste(l.topil().convert('RGBA'),l.bbox[:2])
  filename=('PSD内完整人物_'+f'{index+1:03d}_'+re.sub(r'[\\/:*?"<>|]','_',l.name)+'.png') if s['role']=='character' and sum(v.get('role')=='character' for v in specs)>1 else ('PSD内完整人物.png' if s['role']=='character' else 'PSD内完整艺术字.png' if s['role']=='artwork' else 'PSD内完整背景.png')
  result.save(qa/filename)
  e=np.array(expected).astype('int16');r=np.array(result).astype('int16');delta=np.abs(e-r)
  # Ignore RGB of fully transparent pixels; PNG encoders may keep arbitrary values there.
  valid=(e[:,:,3]>0)|(r[:,:,3]>0)
  lost=int(np.count_nonzero((e[:,:,3]>240)&(r[:,:,3]<20)))
  if s['role']=='artwork':
   # Pillow and Canvas use different resize kernels; preserve opaque strokes and
   # compare the alpha over the union rather than rejecting edge interpolation.
   mean_alpha=float(delta[:,:,3][valid].mean()) if valid.any() else 0
   complete_assets.append({'name':l.name,'sourceSHA256':hashlib.sha256((root/s['file']).read_bytes()).hexdigest(),'opaquePixelsLost':lost,'meanAlphaDifference':mean_alpha,'maskPresent':l.vector_mask is not None or l.mask is not None})
   if lost or mean_alpha>2:asset_errors.append('complete artwork strokes were cut or repositioned: '+l.name)
   if s.get('completeAssetSource') and (int(np.max(delta[:,:,3]))>2 or (valid.any() and float(delta[:,:,:3][valid].mean())>1)):asset_errors.append('artwork RGBA differs from confirmed source: '+l.name)
  elif int(np.max(delta[:,:,3]))>2 or (valid.any() and float(delta[:,:,:3][valid].mean())>1):asset_errors.append('PSD asset differs from supplied complete image: '+l.name)
  if s['role']=='character':
   if not(np.any(r[:,:,3]==0) and np.any(r[:,:,3]>240)):asset_errors.append('character lacks true transparency: '+l.name)
   if np.any((e[:,:,3]>240)&(r[:,:,3]<20)):asset_errors.append('opaque character pixels cut away: '+l.name)
  elif s['role']=='background' and not np.all(r[:,:,3]>=254):asset_errors.append('background has alpha holes: '+l.name)

cached=psd.topil().convert('RGBA');cached.save(qa/'PSD缓存合成.png')
independent=psd.composite(force=True).convert('RGBA');independent.save(qa/'PSD独立合成.png')
def visible_rgba(image):
 pixels=np.array(image).astype('float32');pixels[:,:,:3]*=pixels[:,:,3:4]/255.0;return pixels
# Transparent RGB is not visible and differs legitimately between compositors.
composite_delta=float(np.abs(visible_rgba(cached)-visible_rgba(independent)).mean())
if composite_delta>job.get('maxIndependentCompositeMAE',3.0):errors.append('native render differs excessively from display cache')
input_files={job['source']} if job.get('source') else set()
for s in specs:
 for key in ('file','cache'):
  if s.get(key):input_files.add(s[key])
 if s.get('completeAssetSource'):input_files.add(s['completeAssetSource']['file'])
report={'projectManifestSHA256':sha(root/(DIRS['plan']+'/项目.json')),'psdSHA256':sha(a.psd),'verifiedInputs':{file:sha(root/file) for file in sorted(input_files)},'structuralChecks':'PASS' if not errors else 'FAIL','assetChecks':'PASS' if not asset_errors else 'FAIL','visualReview':'REQUIRED','counts':counts,'errors':errors,'assetErrors':asset_errors,'completeAssets':complete_assets,'vectorReferenceChecks':vector_checks,'nativeVectorChecks':native_vector_checks,'nativeEffectChecks':effect_checks,'nativeGradientChecks':gradient_checks,'nativeMaskChecks':mask_checks,'independentCompositeMAE':composite_delta,'visualReviewNote':'必须检查真实画面与原图。结构、alpha 和缓存一致不能证明补绘内容或图像拼接合格。','layers':layer_rows}
(qa/'检查结果.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('layers','verifiedInputs')},ensure_ascii=True))
sys.exit(1 if errors or asset_errors else 0)




