"""RAM-only preview of completed extraction steps, still awaiting final review."""
import copy

def remember_pending(scene):
 from incremental_assets import pending_generation
 pending=[n for n in scene['nodes'] if pending_generation(n)]
 scene.setdefault('recognition',{}).update(resumePendingNodes=copy.deepcopy(pending),resumeNodeOrder=[n['id'] for n in scene['nodes']],resumeGroups=copy.deepcopy(scene.get('groups',[])),pendingGenerationIds=[n['id'] for n in pending],extractionStatus='INCOMPLETE' if pending else 'COMPLETED')
 return pending

def completed_scene(scene):
 remember_pending(scene)
 nodes=[n for n in scene['nodes'] if n.get('versionArchived') or n.get('provenance')!='pending-image-generation']
 if not scene['nodes']:return None
 ids={n['id'] for n in nodes}
 snapshot={k:copy.deepcopy(scene[k]) for k in ('format','version','title','width','height','source','comparisonSource','originalSource','provenance','background','_projectId') if k in scene}
 original_groups={g['id']:g for g in scene.get('groups',[])};groups=[];visiting=set()
 def keep(ident):
  if ident in ids:return True
  if ident not in original_groups:return False
  if ident in visiting:raise ValueError('分组循环引用')
  visiting.add(ident);group=original_groups[ident];children=[child for child in group['children'] if keep(child)];visiting.remove(ident)
  if children and not any(g['id']==ident for g in groups):groups.append({**copy.deepcopy(group),'children':children})
  return bool(children)
 for ident in original_groups:keep(ident)
 groups.sort(key=lambda g:list(original_groups).index(g['id']))
 snapshot.update(nodes=copy.deepcopy(nodes),groups=groups,edges=[copy.deepcopy(e) for e in scene.get('edges',[]) if e.get('from') in ids and e.get('to') in ids],_partial=True)
 snapshot['recognition']={**copy.deepcopy(scene.get('recognition',{})),'automatic':True,'reviewStatus':'PROCESSING'}
 return snapshot
