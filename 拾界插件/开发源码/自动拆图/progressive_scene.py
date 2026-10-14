"""RAM-only preview of completed extraction steps, still awaiting final review."""
import copy

def completed_scene(scene):
 nodes=[n for n in scene['nodes'] if n.get('provenance')!='pending-image-generation']
 if not nodes:return None
 ids={n['id'] for n in nodes}
 snapshot={k:copy.deepcopy(scene[k]) for k in ('format','version','title','width','height','source','provenance') if k in scene}
 groups=[{**copy.deepcopy(g),'children':[i for i in g['children'] if i in ids]} for g in scene.get('groups',[]) if any(i in ids for i in g['children'])]
 snapshot.update(nodes=copy.deepcopy(nodes),groups=groups,edges=[copy.deepcopy(e) for e in scene.get('edges',[]) if e.get('from') in ids and e.get('to') in ids],_partial=True)
 snapshot['recognition']={**copy.deepcopy(scene.get('recognition',{})),'automatic':True,'reviewStatus':'PROCESSING'}
 return snapshot
