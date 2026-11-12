"""Node installer hook: fetch only small, pinned tokenizer/config files on server.
Large model weights are exclusively prepared by the platform's model download queue.
No network/offline/security settings are changed.
"""
import hashlib,json,os,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def prepare_support(destination,fetch=urllib.request.urlopen,manifest=None):
 manifest=manifest or json.loads((ROOT/'expert/model_manifest.json').read_text(encoding='utf8'))
 destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);count=0
 for file in manifest['files']:
  if file['name']=='model.safetensors':continue
  if file['name'] not in {'config.json','generation_config.json','preprocessor_config.json','tokenizer.json','tokenizer_config.json','chat_template.json','merges.txt','vocab.json','video_preprocessor_config.json'}:raise ValueError('Unexpected support file')
  if file['size_bytes']>16000000 or not file['url'].startswith('https://modelscope.cn/models/Qwen/Qwen3-VL-2B-Instruct/resolve/master/'):raise ValueError('Unexpected support source')
  path=destination/file['name']
  if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==file['sha256']:count+=1;continue
  temp=path.with_suffix(path.suffix+'.partial')
  try:
   digest=hashlib.sha256();total=0
   with fetch(file['url'],timeout=120) as response,temp.open('wb') as stream:
    while True:
     chunk=response.read(1024*1024)
     if not chunk:break
     total+=len(chunk)
     if total>file['size_bytes']:raise ValueError('Support file exceeds declared size')
     digest.update(chunk);stream.write(chunk)
   if total!=file['size_bytes'] or digest.hexdigest()!=file['sha256']:raise ValueError('Publisher checksum mismatch: '+file['name'])
   os.replace(temp,path);count+=1
  finally:
   if temp.exists():temp.unlink()
 return count

if __name__=='__main__':
 print('[拾界] Server installer preparing small model support files; weight download uses platform queue',flush=True)
 print('[拾界] Verified support files: '+str(prepare_support(ROOT/'model_support/Qwen3-VL-2B-Instruct')),flush=True)
