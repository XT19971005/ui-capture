"""One durable incremental safety copy per source project; verified retirement only."""
import copy, hashlib, uuid


def _generated(doc):
 return [node for node in doc.get('nodes',[]) if node.get('provenance')!='source-reference']


class GenerationRecovery:
 def __init__(self,store,title,project_id=None):
  self.store=store
  self.source_id=project_id if isinstance(project_id,str) and project_id else None
  self.ident='generation-source-'+hashlib.sha256(self.source_id.encode()).hexdigest() if self.source_id else 'generation-'+uuid.uuid4().hex
  self.title=str(title)[:140]+' · 生成恢复'

 def save(self,scene):
  with self.store.lock:
   try:previous=self.store.get(self.ident)
   except FileNotFoundError:previous=None
   # Merge by generated identity. Concurrent rounds cannot erase unmerged assets.
   nodes={node['id']:copy.deepcopy(node) for node in _generated(previous['doc'])} if previous else {}
   for node in scene.get('nodes',[]):
    old=nodes.get(node['id'])
    proof_fields={'review','assetReview','assetReviewStatus','reviewIssue','positionReviewRequired','boundaryReviewRequired'}
    if old is not None and {k:v for k,v in old.items() if k not in proof_fields}!={k:v for k,v in node.items() if k not in proof_fields}:
     # A reused identity with different content must remain recoverable too.
     backup=copy.deepcopy(old);backup['id']=old['id']+'-recovered-'+uuid.uuid4().hex
     nodes[backup['id']]=backup
    nodes[node['id']]=copy.deepcopy(node)
   doc=copy.deepcopy(scene);doc['_projectId']=self.ident;doc['title']=self.title
   groups={group['id']:copy.deepcopy(group) for group in previous['doc'].get('groups',[])} if previous else {}
   groups.update({group['id']:copy.deepcopy(group) for group in scene.get('groups',[])})
   if groups:doc['groups']=list(groups.values())
   doc['_generationRecovery']={'version':2,'sourceProjectId':self.source_id,'completedLayers':len(nodes),'complete':not scene.get('_partial',False)}
   doc['nodes']=[{'id':'source-'+self.ident,'type':'image','name':'原图 · 对照（锁定）','src':scene['source'],'x':0,'y':0,'width':scene['width'],'height':scene['height'],'locked':True,'hidden':True,'visible':False,'provenance':'source-reference'},*nodes.values()]
   meta=self.store.save(self.ident,{'id':self.ident,'kind':'image','title':self.title,'saveMode':'saved','doc':doc},previous['persistedVersion'] if previous else None)
   scene['_generationRecoveryId']=self.ident;scene['_generationRecoveryVersion']=meta['persistedVersion']
   return self.ident


def acknowledge(store,project_id,recovery_id,expected_version):
 """Client assertions are insufficient: re-read durable main and CAS safety copy."""
 retained={'deleted':False,'retained':True}
 if not all(isinstance(value,str) and value for value in (project_id,recovery_id,expected_version)):return retained
 expected_id='generation-source-'+hashlib.sha256(project_id.encode()).hexdigest()
 if recovery_id!=expected_id:return retained # Never delete historical/random recovery projects.
 with store.lock:
  try:recovery=store.get(recovery_id);main=store.get(project_id)
  except FileNotFoundError:return retained
  info=recovery['doc'].get('_generationRecovery',{})
  if info.get('version')!=2 or info.get('sourceProjectId')!=project_id or recovery.get('persistedVersion')!=expected_version:return retained
  doc=main.get('doc',{})
  if doc.get('_generationStages',{}).get('blocked'):return retained
  nodes={node.get('id'):node for node in doc.get('nodes',[])}
  originals=doc.get('_generationStages',{}).get('completed',[])
  def content_matches(saved,node):
   # Moving/renaming a returned layer does not discard its generated content.
   for key,value in node.items():
    if key in ('x','y','name','visible','hidden','locked','selected','parentId','groupId','zIndex','rotation','scaleX','scaleY'):continue
    if saved.get(key)!=value:return False
   return True
  for node in _generated(recovery['doc']):
   saved=nodes.get(node.get('id'))
   if not saved:return retained
   if content_matches(saved,node):continue
   # Transparent-edge compaction changes the live src and geometry. The complete
   # original may prove durability only inside this same saved main document,
   # with a matching nonempty plan token on the recovery, live and original layer.
   token=node.get('_generationPlanToken')
   if not isinstance(token,str) or not token or saved.get('_generationPlanToken')!=token:return retained
   if not any(isinstance(original,dict) and original.get('id')==node.get('id') and original.get('_generationPlanToken')==token and content_matches(original,node) for original in originals):return retained
  store.delete(recovery_id,expected_version)
  return {'deleted':True,'retained':False}
