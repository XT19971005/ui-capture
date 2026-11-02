"""Ephemeral workspaces and bounded, audited in-memory web results."""
import copy,hashlib,json,tempfile,threading,time,uuid
from pathlib import Path

class SessionStore:
 def __init__(self,ttl=1200):self.ttl=ttl;self.items={};self.lock=threading.RLock()
 def _expire(self):
  now=time.monotonic()
  for key in list(self.items):
   if self.items[key]['expires']<=now:del self.items[key]
 def put(self,scene,psd,filename='图片拆分.psd',audit=None):
  with self.lock:
   self._expire();ident=uuid.uuid4().hex;result=copy.deepcopy(scene)
   if psd is not None:psd=bytes(psd)
   result.pop('_projectId',None);result['_sessionId']=ident
   result['delivery']={'storage':'memory','sessionId':ident,'filename':filename,'psdSHA256':hashlib.sha256(psd).hexdigest() if psd is not None else None,'structuralChecks':(audit or {}).get('structuralChecks')}
   self.items[ident]={'scene':result,'psd':bytes(psd) if psd is not None else None,'filename':filename,'audit':copy.deepcopy(audit),'expires':time.monotonic()+self.ttl}
   return copy.deepcopy(result)
 def get(self,ident):
  with self.lock:self._expire();return copy.deepcopy(self.items.get(ident))
 def take(self,ident):
  with self.lock:self._expire();return self.items.pop(ident,None)
 def clear(self):
  with self.lock:self.items.clear()
 def count(self):
  with self.lock:self._expire();return len(self.items)

SESSIONS=SessionStore()
CAPTURES=SessionStore(ttl=600)
def _reaper():
 while True:
  time.sleep(30);SESSIONS.count();CAPTURES.count()
threading.Thread(target=_reaper,daemon=True).start()

def run_temporary(generate):
 with tempfile.TemporaryDirectory(prefix='shijie-task-') as folder:
  home=Path(folder);sealed=_seal(generate(home),home)
 # Publish only after successful workspace cleanup, including error paths.
 return SESSIONS.put(*sealed)

def _seal(scene,home):
 from layer_review import require_unique_names
 require_unique_names(scene)
 delivery=scene.get('delivery',{})
 if not delivery:return scene,None,'图片拆分.psd',None
 project=Path(delivery['project']).resolve();target=Path(delivery['psd']).resolve()
 if not project.is_relative_to(home.resolve()) or target.parent!=(project/'2_输出').resolve():raise ValueError('临时输出路径无效')
 qa=project/'1_过程/03_检查';audit=json.loads((qa/'检查结果.json').read_text('utf8'));raw=target.read_bytes()
 if audit.get('structuralChecks')!='PASS' or audit.get('assetChecks')!='PASS' or audit.get('psdSHA256')!=hashlib.sha256(raw).hexdigest():raise ValueError('PSD 独立检查失败或字节已变化')
 if scene.get('recognition',{}).get('reviewStatus')=='NEEDS_REVIEW':
  visual=json.loads((qa/'Codex画面复核.json').read_text('utf8'));checklist=json.loads((qa/'画面复核.json').read_text('utf8'))
  if checklist.get('psdSHA256')!=hashlib.sha256(raw).hexdigest():raise ValueError('实际复核记录不对应当前PSD')
  return scene,raw,target.name,{**audit,'visualReview':visual,'fileReview':checklist,'visualStatus':'NEEDS_REVIEW'}
 visual,checklist=visual_records(scene,qa,hashlib.sha256(raw).hexdigest())
 return scene,raw,target.name,{**audit,'visualReview':visual,'fileReview':checklist}

def visual_records(scene,qa,expected_sha=None):
 from layer_review import require_unique_names,review_errors
 require_unique_names(scene)
 if scene.get('recognition',{}).get('reviewStatus')!='PASS':raise ValueError('自动画面复核未通过')
 visual=json.loads((qa/'Codex画面复核.json').read_text('utf8'));checklist=json.loads((qa/'画面复核.json').read_text('utf8'))
 if expected_sha is None and scene.get('delivery',{}).get('psd'):expected_sha=hashlib.sha256(Path(scene['delivery']['psd']).read_bytes()).hexdigest()
 if expected_sha is not None and checklist.get('psdSHA256')!=expected_sha:raise ValueError('实际画面复核记录不对应当前 PSD')
 if review_errors(scene,visual,checklist):raise ValueError('实际逐层画面检查未通过')
 return visual,checklist
