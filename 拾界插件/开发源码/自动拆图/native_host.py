"""Narrow native bridge: starts only the bundled local engine; no arbitrary execution."""
import json, os, struct, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'依赖/自动拆图/运行'

def connect():
    STATE.mkdir(parents=True,exist_ok=True)
    def running():
        try:
            record=json.loads((STATE/'service.json').read_text(encoding='utf-8'))
            if record.get('service')!='shijie-engine' or record.get('port')!=19217:return None
            req=urllib.request.Request('http://127.0.0.1:19217/health',headers={'X-Shijie-Token':record['token']})
            with urllib.request.urlopen(req,timeout=1) as r:health=json.load(r)
            if health.get('service')=='shijie-engine' and health.get('version')=='0.9.0':return {'url':'http://127.0.0.1:19217','token':record['token'],**health}
        except Exception:return None
    result=running()
    if result:return result
    logfile=open(STATE/'启动.log','ab')
    env=os.environ.copy();env['TEMP']=env['TMP']=str(ROOT/'依赖/运行临时');env['PYTHONDONTWRITEBYTECODE']='1'
    subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('server.py'))],cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=logfile,stderr=logfile,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    logfile.close()
    for _ in range(100):
        result=running()
        if result:return result
        time.sleep(.1)
    raise RuntimeError('本机引擎启动失败，请查看 D 盘插件目录的依赖/自动拆图/运行/启动.log')

def main():
    header=sys.stdin.buffer.read(4)
    if len(header)!=4:return
    length=struct.unpack('<I',header)[0]
    if length>8192:return
    message=json.loads(sys.stdin.buffer.read(length))
    try:
        if message!={'action':'connect'}:raise ValueError('不支持的操作')
        result={'ok':True,**connect()}
    except Exception as e:result={'ok':False,'error':str(e)[:300]}
    encoded=json.dumps(result).encode('utf-8');sys.stdout.buffer.write(struct.pack('<I',len(encoded))+encoded);sys.stdout.buffer.flush()
if __name__=='__main__':main()
