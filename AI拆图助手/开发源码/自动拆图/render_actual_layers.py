"""Render actual PSD leaves mapped to original scene IDs, plus parent on/off checks."""
import argparse,hashlib,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('psd');p.add_argument('qa');p.add_argument('packages');a=p.parse_args()
sys.path.insert(0,a.packages)
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'技能包/game-ui-to-psd/scripts'))
from psd_gradient_compat import install as install_gradient_compat
install_gradient_compat()
from psd_tools import PSDImage
file=Path(a.psd);qa=Path(a.qa);psd=PSDImage.open(file);layers=qa/'独立图层';layers.mkdir(exist_ok=True)
manifest=qa.parent/'02_结构/项目.json'
job=json.loads(manifest.read_text('utf-8-sig')) if manifest.exists() else {}

def specs(items):
 for s in items:
  yield s
  if s.get('kind')=='group':yield from specs(s.get('children',[]))
all_specs=list(specs(job.get('layers',[])))
leaf_specs=[s for s in all_specs if s.get('kind')!='group'];indexed=any('sourceSceneIndex' in s for s in leaf_specs)
by_id={s.get('sourceNativeLayerId',s.get('nativeLayerId')):s for s in all_specs if s.get('sourceNativeLayerId',s.get('nativeLayerId')) is not None}
if len(by_id)!=sum(s.get('sourceNativeLayerId',s.get('nativeLayerId')) is not None for s in all_specs):raise RuntimeError('Duplicate source native layer IDs')
rows=[];seen=set()
for psd_index,layer in enumerate(l for l in psd.descendants() if not l.is_group()):
 spec=by_id.get(layer.layer_id)
 if indexed and (spec is None or 'sourceSceneIndex' not in spec):raise RuntimeError('Actual PSD leaf lost original scene ID: '+layer.name)
 index=spec['sourceSceneIndex'] if indexed else psd_index
 if index in seen:raise RuntimeError('Duplicate original scene index');
 seen.add(index)
 if spec and spec['name']!=layer.name:raise RuntimeError('Actual layer name/source ID mismatch: '+layer.name)
 name=''.join('_' if c in '\\/:*?"<>|' or ord(c)<32 else c for c in layer.name)
 image=layer.composite(force=True,layer_filter=lambda _:True)
 if image is None:raise RuntimeError('Native layer cannot render: '+layer.name)
 target=layers/(f'{index+1:03d}_'+name+'.png');image.save(target)
 rows.append({'index':index,'sourceSceneIndex':index,'psdIndex':psd_index,'nodeId':spec.get('nodeId') if spec else None,'nativeLayerId':layer.layer_id,'name':layer.name,'file':'独立图层/'+target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'nativeComposite':True})
if indexed and len(rows)!=len(leaf_specs):raise RuntimeError('Original scene/actual PSD leaf count mismatch')
group_specs=[s for s in all_specs if s.get('kind')=='group']
group_rows=[];group_dir=qa/'父组显示检查';group_dir.mkdir(exist_ok=True)
for group_index,layer in enumerate(l for l in psd.descendants() if l.is_group()):
 spec=by_id.get(layer.layer_id)
 if spec is None and group_index<len(group_specs):spec=group_specs[group_index]
 if spec and spec['name']!=layer.name:raise RuntimeError('Actual group ID/order mismatch: '+layer.name)
 if not spec or not (spec.get('displayMask') or spec.get('native',{}).get('effects')):continue
 files={};mask=layer.mask;mask_disabled=mask.disabled if mask else None
 descriptors=[layer.tagged_blocks.get_data(tag) for tag in [b'lfx2',b'lmfx']]
 saved=[(d,d.get(b'masterFXSwitch')) for d in descriptors if d is not None]
 def within_group(candidate):
  while candidate is not layer:
   if not candidate.visible:return False
   candidate=candidate.parent
   if candidate is None:return False
  return True
 def save(kind):
  im=layer.composite(viewport=(0,0,psd.width,psd.height),force=True,layer_filter=within_group)
  if im is None:raise RuntimeError('Parent group cannot render: '+layer.name)
  target=group_dir/(f'{group_index+1:03d}_'+str(layer.layer_id)+'_'+kind+'.png');im.save(target)
  files[kind]={'file':'父组显示检查/'+target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'nativeComposite':True}
 try:
  save('enabled')
  if mask:mask.disabled=True
  for d,_ in saved:d[b'masterFXSwitch']=False
  save('maskAndEffectsDisabled')
 finally:
  if mask:mask.disabled=mask_disabled
  for d,value in saved:d[b'masterFXSwitch']=value
 unsupported=[type(e).__name__ for e in layer.effects if e.enabled and type(e).__name__ in ['DropShadow','InnerShadow','OuterGlow','InnerGlow']]
 group_rows.append({'unsupportedEffects':unsupported,'independentRendererNote':'psd_tools不绘制阴影/光晕；这些效果只核实原生描述及开关，像素不等于Photoshop' if unsupported else None,'nodeId':spec.get('nodeId'),'nativeLayerId':layer.layer_id,'name':layer.name,'maskOriginallyDisabled':mask_disabled,'files':files,'reason':'父组显示蒙版和组样式开启/关闭的实际独立回读；子图层底稿不改写'})
(qa/'独立回读图层来源.json').write_text(json.dumps({'psdSHA256':hashlib.sha256(file.read_bytes()).hexdigest(),'layers':rows,'groups':group_rows},ensure_ascii=False,indent=2),'utf8')
print('PASS actual native independent leaf composites: '+str(len(rows))+'; parent on/off checks: '+str(len(group_rows)))
