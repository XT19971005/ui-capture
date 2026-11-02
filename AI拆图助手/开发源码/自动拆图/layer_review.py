"""One-to-one layer names, file targets and actual observation gates."""
import re
from collections import Counter

def unique_layer_names(scene):
 nodes=[*scene['nodes'],*scene.get('groups',[])];base_name=lambda n:str(n.get('name') or n.get('text') or '图层').strip() or '图层';reserved={base_name(n) for n in nodes};used=set()
 for n in nodes:
  base=base_name(n);name=base;index=2
  if name in used:
   while True:
    name=base+'_'+str(index);index+=1
    if name not in used and name not in reserved:break
  n['name']=name;used.add(name)

def require_unique_names(scene):
 names=[n.get('name') for n in scene['nodes']]
 if any(not isinstance(n,str) or not n.strip() for n in names) or len(names)!=len(set(names)):raise ValueError('图层名称必须逐项唯一且非空')

def review_targets(scene,checklist):
 require_unique_names(scene);targets=[]
 for check in checklist['checks']:
  match=re.search(r'(?:^|/)独立图层/(\d+)_',check['file'].replace('\\','/'));index=int(match[1])-1 if match else None
  if index is not None and (not 0<=index<len(scene['nodes']) or scene['nodes'][index]['name']!=check['name']):raise ValueError('独立图层检查路径与当前图层不对应')
  targets.append({'name':check['name'],'file':check['file'],'atlasIndex':index})
 return targets

def unique_check_names(scene,checklist):
 # Layer observations retain their actual layer names. Overall reference files
 # with the same caption receive a distinct caption before requesting review.
 targets=review_targets(scene,checklist);used={t['name'] for t in targets if t['atlasIndex'] is not None}
 for check,target in zip(checklist['checks'],targets):
  if target['atlasIndex'] is not None:continue
  base=check['name'];name=base;index=2
  while name in used:name=base+'_检查'+str(index);index+=1
  check['name']=name;used.add(name)

def approved_asset_names(scene,review):
 passed={c['name'] for c in review.get('asset_checks',[]) if c.get('status')=='PASS'}
 passed -= {c['name'] for c in review.get('color_checks',[]) if c.get('status')=='FAIL'}
 if scene.get('recognition',{}).get('colorFidelityRequired'):
  passed &= {c['name'] for c in review.get('color_checks',[]) if c.get('status')=='PASS' and isinstance(c.get('notes'),str) and c['notes'].strip()}
 return passed

def discard_failed_assets(completed,repair_names):
 for key in list(completed):
  if completed[key].get('name') in repair_names:del completed[key]

def review_errors(scene,review,checklist):
 try:require_unique_names(scene)
 except ValueError as exc:return [str(exc)]
 errors=[]
 if review.get('status')!='PASS':errors.append('自动画面复核未通过')
 fields=[('asset_checks',[n['name'] for n in scene['nodes']]),('file_checks',[c['name'] for c in checklist.get('checks',[])])]
 if scene.get('recognition',{}).get('colorFidelityRequired'):fields.append(('color_checks',[n['name'] for n in scene['nodes']]))
 if scene.get('recognition',{}).get('acceptanceRequired'):
  from acceptance import FINAL_CRITERIA
  fields.append(('acceptance_checks',list(FINAL_CRITERIA)))
 for field,expected in fields:
  items=review.get(field,[]);names=[c.get('name') for c in items];counts=Counter(names)
  if not expected or len(expected)!=len(set(expected)) or any(counts[name]!=1 for name in expected):errors.append(field+' 未逐项唯一确认')
  if any(count!=1 for count in counts.values()) or any(name not in expected for name in names):errors.append(field+' 存在重复或未知检查项')
  if any(c.get('status')!='PASS' or not isinstance(c.get('notes'),str) or not c['notes'].strip() for c in items):errors.append(field+' 缺少通过状态或实际观察')
 if not checklist.get('checks') or any(c.get('status')!='PASS' or not isinstance(c.get('notes'),str) or not c['notes'].strip() for c in checklist['checks']):errors.append('实际检查文件未逐项通过')
 return errors
