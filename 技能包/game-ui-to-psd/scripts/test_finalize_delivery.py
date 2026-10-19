"""Synthetic compact-layout regression; never a visual acceptance test."""
import argparse,sys,json,hashlib,subprocess,uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
r=Path(a.out).resolve()/('run-'+uuid.uuid4().hex[:8]);w=r/'1_过程';out=r/'2_输出';qa=w/'03_检查'
for d in (w/'01_素材',w/'02_结构',qa,out):d.mkdir(parents=True,exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def put(f,obj):f.write_text(json.dumps(obj),'utf8')
original=out/'original.png';original.write_bytes(b'synthetic-original')
psd=out/'test.psd';psd.write_bytes(b'synthetic-psd')
asset=w/'01_素材/complete.png';asset.write_bytes(b'immutable-source')
evidence=qa/'compare.png';evidence.write_bytes(b'qa-fixture')
(qa/'独立图层图册_1.png').write_bytes(b'contact-sheet-fixture')
job={'source':'../2_输出/original.png','outputName':'test.psd'};put(w/'02_结构/项目.json',job)
review={'psdSHA256':sha(psd),'checks':[{'name':'synthetic','status':'PASS','notes':'Fixture observation only','file':'03_检查/compare.png','sha256':sha(evidence)}],'issues':[]};put(qa/'画面复核.json',review)
state={'visualReview':'PENDING'};put(qa/'流水线状态.json',state)
audit={'psdSHA256':sha(psd),'projectManifestSHA256':sha(w/'02_结构/项目.json'),'structuralChecks':'PASS','assetChecks':'PASS'};put(qa/'检查结果.json',audit)
def invoke():return subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).with_name('finalize_delivery.py')),'--project',str(r)],capture_output=True,text=True,encoding='utf8')
assert invoke().returncode!=0 and evidence.exists(),'Pending review must not clean'
state['visualReview']='PASS';put(qa/'流水线状态.json',state)
result=invoke();assert result.returncode==0,result.stderr
assert {f.name for f in r.iterdir()}=={'1_过程','2_输出'}
assert {f.name for f in out.iterdir()}=={'test.psd','original.png'}
assert asset.read_bytes()==b'immutable-source'
assert not evidence.exists() and (qa/'图层图册/独立图层图册_1.png').exists()
assert invoke().returncode==0,'Cleanup must be idempotent'
print(json.dumps({'status':'PASS','cases':['pending review refuses cleanup','two directory layout','original unique','assets immutable','atlas retained','cleanup idempotent'],'fixture':str(r)},ensure_ascii=False))
