"""Loopback HTTP transfer of an existing genuinely reviewed PSD; no regeneration."""
import hashlib,json,threading,urllib.error,urllib.request
from pathlib import Path
from runtime import ROOT
from session_outputs import run_temporary,SESSIONS
from server import app,TOKEN
from werkzeug.serving import make_server

def main():
 project=ROOT.parent/'交付包/河南文物公益行动';structure=project/'1_过程/02_结构';qa=project/'1_过程/03_检查'
 scene=json.loads((structure/'工程.scene.json').read_text('utf8'));psd=Path(scene['delivery']['psd']);before=hashlib.sha256(psd.read_bytes()).hexdigest()
 actual=json.loads((qa/'Codex画面复核.json').read_text('utf8'));assert actual['status']=='PASS'
 paths=[]
 def transfer(home):
  target=home/'实际已审核材料';out=target/'2_输出';checks=target/'1_过程/03_检查';out.mkdir(parents=True);checks.mkdir(parents=True)
  paths.append(home);copy=out/psd.name;copy.write_bytes(psd.read_bytes())
  for name in ('检查结果.json','Codex画面复核.json','画面复核.json'):(checks/name).write_bytes((qa/name).read_bytes())
  return {**scene,'delivery':{'project':str(target),'psd':str(copy)}}
 result=run_temporary(transfer);assert not paths[0].exists()
 http=make_server('127.0.0.1',0,app,threaded=True);threading.Thread(target=http.serve_forever,daemon=True).start()
 def get(route,method='GET'):
  req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+route,method=method,headers={'Host':'127.0.0.1:19217','X-Shijie-Token':TOKEN})
  return urllib.request.urlopen(req,timeout=20)
 try:
  ident=result['_sessionId'];prefix='/sessions/'+ident
  with get(prefix+'/scene') as response:received=json.load(response)
  assert received['nodes']==scene['nodes'];assert received['delivery']['storage']=='memory';assert 'project' not in received['delivery']
  with get(prefix+'/review') as response:review=json.load(response)
  assert review['visualReview']['status']=='PASS';assert review['psdSHA256']==before
  with get(prefix+'/psd') as response:download=response.read();header=response.headers['X-Shijie-PSD-SHA256']
  digest=hashlib.sha256(download).hexdigest();assert digest==header==before;assert SESSIONS.get(ident) is None
  try:get(prefix+'/psd');raise AssertionError('consumed session remained available')
  except urllib.error.HTTPError as exc:assert exc.code==404
  with get(prefix,'DELETE') as response:assert json.load(response)['ok']
  assert hashlib.sha256(psd.read_bytes()).hexdigest()==before
  report={'status':'PASS','scope':'actual existing independently reviewed PSD through temporary workspace and real loopback HTTP; no new ImageGen or visual approval fabricated','temporaryWorkspaceRemoved':True,'nativeEditableSceneUnchanged':True,'actualVisualReview':review['visualReview']['status'],'downloadSourceAuditSHA256':before,'downloadSHA256':digest,'consumedSessionReturns404':True,'formalDeliveryPreserved':True}
  output=ROOT.parent/'测试结果/拾界_无缓存';output.mkdir(parents=True,exist_ok=True);(output/'真实HTTP内存PSD验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8');print(json.dumps(report,ensure_ascii=False))
 finally:http.shutdown();http.server_close();SESSIONS.clear()
if __name__=='__main__':main()
