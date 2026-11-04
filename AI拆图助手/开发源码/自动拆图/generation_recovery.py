"""Durable generated assets, independent of the disposable job and page state."""
import copy, uuid

class GenerationRecovery:
 def __init__(self,store,title):
  self.store=store
  self.ident='generation-'+uuid.uuid4().hex
  self.version=None
  self.title=str(title)[:140]+' · 生成恢复'

 def save(self,scene):
  doc=copy.deepcopy(scene)
  doc['_projectId']=self.ident
  doc['title']=self.title
  doc['_generationRecovery']={'version':1,'completedLayers':len(scene['nodes']),'complete':not scene.get('_partial',False)}
  doc['nodes'].insert(0,{'id':'source-'+self.ident,'type':'image','name':'原图 · 对照（锁定）','src':scene['source'],'x':0,'y':0,'width':scene['width'],'height':scene['height'],'locked':True,'hidden':True,'visible':False,'provenance':'source-reference'})
  meta=self.store.save(self.ident,{'id':self.ident,'kind':'image','title':self.title,'saveMode':'saved','doc':doc},self.version)
  self.version=meta['persistedVersion']
  return self.ident
