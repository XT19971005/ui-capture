"""Compact delivery: process assets/structure/checks; output PSD and original."""
import argparse,json,hashlib,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--project',required=True);a=p.parse_args()
delivery=Path(a.project).resolve();work=delivery/'1_过程';qa=work/'03_检查';out=delivery/'2_输出'
def read(f):return json.loads(f.read_text('utf-8-sig'))
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
job=read(work/'02_结构/项目.json');review=read(qa/'画面复核.json');audit=read(qa/'检查结果.json');state=read(qa/'流水线状态.json')
if Path(job['outputName']).name!=job['outputName']:raise ValueError('Unsafe PSD name')
psd=out/job['outputName'];source=(work/job['source']).resolve()
if source.parent!=out.resolve():raise ValueError('Original must be in output')
digest=sha(psd);receipt_file=qa/'交付与清理记录.json';already_clean=receipt_file.exists() and read(receipt_file).get('psdSHA256')==digest
if state.get('visualReview')!='PASS' or any(x.get('psdSHA256')!=digest for x in (review,audit)):raise ValueError('Current PSD must pass actual review')
if audit['projectManifestSHA256']!=sha(work/'02_结构/项目.json'):raise ValueError('Stale manifest')
if audit['structuralChecks']!='PASS' or audit['assetChecks']!='PASS' or review.get('issues'):raise ValueError('Unresolved checks')
for c in review['checks']:
 if c['status']!='PASS' or not c.get('notes'):raise ValueError('Pending observation')
 f=(work/c['file']).resolve()
 if not f.is_relative_to(delivery):raise ValueError('Evidence outside project')
 if not f.exists() and not already_clean:raise ValueError('Missing evidence before first cleanup')
 if f.exists() and sha(f)!=c['sha256']:raise ValueError('Changed evidence: '+c['name'])
if {f.name for f in out.iterdir()}!={job['outputName'],source.name}:raise ValueError('Output must contain PSD and original only')
sheets=qa/'图层图册';sheets.mkdir(exist_ok=True)
for f in qa.glob('独立图层图册_*.png'):shutil.copy2(f,sheets/f.name)
deleted=0
for f in qa.rglob('*.png'):
 if f.parent==sheets:continue
 if not f.resolve().is_relative_to(qa.resolve()):raise ValueError('Cleanup outside checks')
 f.unlink();deleted+=1
receipt={'status':'PASS','layout':['1_过程','2_输出'],'psdSHA256':digest,'originalSHA256':sha(source),'visualChecksCompleted':len(review['checks']),'cleanupAfterActualReview':True,'cleanedImages':deleted,'note':'保留必要图册和实际复核记录；画面更改后重新生成证据。'}
receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'status':'PASS','output':[str(psd),str(source)],'cleanedImages':deleted},ensure_ascii=False))
