"""Validated planning checkpoints. Never performs model calls or automatic retries."""
import hashlib,json,os,uuid
from pathlib import Path
try:
 from .staged_expert import _inventory,read_object,BUCKETS
 from .component_expert import bind_plan
except ImportError:
 from staged_expert import _inventory,read_object,BUCKETS
 from component_expert import bind_plan

PROTOCOL='qp-stage-checkpoint-v1'
def digest(value):return hashlib.sha256(value).hexdigest()

class StageStore:
 def __init__(self,root,rgb,knowledge):
  self.root=Path(root);self.rgb=rgb;self.knowledge=knowledge
  self.source=digest(str(rgb.shape).encode()+rgb.tobytes())
 def key(self,stage,inventory):
  if stage not in ('inventory',*BUCKETS):raise ValueError('未知阶段')
  return digest(json.dumps([PROTOCOL,self.source,self.knowledge['sha256'],stage,inventory],ensure_ascii=False).encode())
 def validate(self,stage,inventory,reply):
  if stage=='inventory':_inventory(reply,self.rgb,self.knowledge);return
  inv,_=_inventory(inventory,self.rgb,self.knowledge);value,_=read_object(reply)
  expected={r['id'] for r in inv['items'] if r['bucket']==stage}
  rows=value.get('assets')
  if not isinstance(rows,list):raise ValueError('分支缺少素材列表')
  ids=[r.get('id') for r in rows if isinstance(r,dict)]
  if len(ids)!=len(rows) or len(set(ids))!=len(ids) or set(ids)!=expected:raise ValueError('分支ID越权、重复或缺失：'+stage)
  for r in rows:
   method=r.get('method')
   if stage=='texts' and method!='text':raise ValueError('文字分支方法错误')
   if stage=='vectors' and method not in ('shape','solid'):raise ValueError('矢量分支方法错误')
  if rows:
   h,w=self.rgb.shape[:2]
   checked=[dict(r,z=z,name=next(i['name'] for i in inv['items'] if i['id']==r['id'])) for z,r in enumerate(rows)]
   bind_plan(json.dumps(dict(width=w,height=h,knowledge_ack=inv['knowledge_ack'],background_prompt=inv['background_prompt'],assets=checked)),self.rgb,self.knowledge)
 def lookup(self,stage,inventory):
  key=self.key(stage,inventory)
  if stage!='inventory':
   inv,_=_inventory(inventory,self.rgb,self.knowledge)
   if not any(r['bucket']==stage for r in inv['items']):
    return json.dumps(dict(assets=[],warnings=[],checkpoint_status='SKIPPED_EMPTY')), 'SKIPPED_EMPTY'
  p=self.root/(key+'.json')
  if not p.exists():return None,'NEEDS_AGENT'
  v=json.loads(p.read_text('utf-8'))
  if v.get('key')!=key or digest(v.get('reply','').encode())!=v.get('reply_sha256'):raise ValueError('规划检查点摘要不符，拒绝复用')
  self.validate(stage,inventory,v['reply'])
  return v['reply'],'CACHED_VALIDATED'
 def save(self,stage,inventory,reply):
  self.validate(stage,inventory,reply);key=self.key(stage,inventory)
  self.root.mkdir(parents=True,exist_ok=True)
  value=dict(protocol=PROTOCOL,key=key,stage=stage,source_sha256=self.source,knowledge_sha256=self.knowledge['sha256'],reply=reply,reply_sha256=digest(reply.encode()),visual_status='NOT_REVIEWED')
  temp=self.root/(key+'.'+uuid.uuid4().hex+'.tmp')
  try:
   temp.write_text(json.dumps(value,ensure_ascii=False),'utf-8');os.replace(temp,self.root/(key+'.json'))
  finally:
   if temp.exists():temp.unlink()
