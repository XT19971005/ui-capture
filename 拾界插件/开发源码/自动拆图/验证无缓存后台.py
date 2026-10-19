import json,re,subprocess,sys,tempfile
from pathlib import Path
from runtime import ROOT
def main():
 result=subprocess.run([sys.executable,'-B','-X','utf8','-m','unittest','discover','-s','开发源码/自动拆图','-p','test_*.py','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
 out=ROOT.parent/'测试结果/拾界_无缓存';out.mkdir(parents=True,exist_ok=True)
 (out/'后台单元与真实浏览器回归.txt').write_text(result.stdout+result.stderr,'utf8')
 roots={Path(tempfile.gettempdir()),ROOT/'依赖/运行临时'}
 remains=[str(p) for root in roots if root.exists() for p in root.iterdir() if p.is_dir() and p.name.startswith(('shijie-task-','shijie-web-','shijie-browser-test-'))]
 count=re.search(r'Ran (\d+) tests',result.stderr)
 report={'status':'PASS' if result.returncode==0 and not remains else 'FAIL','tests':int(count[1]) if count else 0,'exitCode':result.returncode,'remainingOwnedTemporaryDirectories':remains,'generationVisualClaim':'No new ImageGen claim; visual/native regressions and actual existing reviewed PSD are tested separately','realPSDTransportEvidence':'真实HTTP内存PSD验收.json','checks':['success/error/cancel workspace cleanup','independent SHA and actual visual-record hard gates','RAM consumption and expiration','cross-page capture consumption and invalid image rejection','real browser dynamic DOM/canvas actual pixels','browser close/failure leaves no profile']}
 (out/'后台无缓存回归.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8');print(json.dumps(report,ensure_ascii=False));return 0 if report['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
