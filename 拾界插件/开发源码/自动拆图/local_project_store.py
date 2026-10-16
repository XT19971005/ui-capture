"""Explicit saves only: atomic project files, bounded deduplicated bodies, cheap lists."""
import gzip, hashlib, io, json, os, re, tempfile, threading, time, uuid, zlib
from pathlib import Path
from image_wire import decode_job, measure, IMAGE_FIELDS, MAX_HTTP_BYTES, MAX_IMAGES

HEADER_LIMIT=65536
class ProjectConflict(ValueError):pass

def pack_record(record):
 images=[];indexes={}
 def walk(value,key=None):
  if isinstance(value,str) and key in IMAGE_FIELDS and value.startswith('data:image/'):
   if value not in indexes:
    if len(images)>=MAX_IMAGES:raise ValueError('工程独立图片数量超过4096限制，原工程已保留')
    indexes[value]=len(images);images.append(value)
   return {'$image':indexes[value]}
  if isinstance(value,dict):
   if '$image' in value:raise ValueError('工程包含保留的图片引用字段')
   return {k:walk(v,k) for k,v in value.items()}
  if isinstance(value,list):return [walk(v) for v in value]
  return value
 return {'wireFormat':'shijie-image-table','wireVersion':1,'job':walk(record),'images':images}

class LocalProjectStore:
 def __init__(self,root):self.root=Path(root);self.lock=threading.RLock()
 def path(self,ident):
  if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',ident):raise ValueError('工程标识无效')
  path=self.root/(hashlib.sha256(ident.encode('utf8')).hexdigest()+'.shijie-project')
  if path.resolve().parent!=self.root.resolve():raise ValueError('工程路径无效')
  return path
 def _header(self,stream):
  line=stream.readline(HEADER_LIMIT+1)
  if len(line)>HEADER_LIMIT or not line.endswith(b'\n'):raise ValueError('本地工程索引损坏')
  meta=json.loads(line)
  if not isinstance(meta,dict) or meta.get('storageVersion')!='local-disk-v1':raise ValueError('本地工程格式无效')
  if not isinstance(meta.get('updated'),int) or not isinstance(meta.get('title'),str):raise ValueError('本地工程索引无效')
  if not isinstance(meta.get('persistedVersion'),str) or not meta['persistedVersion'] or len(meta['persistedVersion'])>160:raise ValueError('本地工程版本索引损坏；原文件已保留')
  return meta
 def list(self):
  with self.lock:
   result=[]
   if not self.root.exists():return result
   for path in self.root.glob('*.shijie-project'):
    if path.resolve().parent!=self.root.resolve():continue
    try:
     with path.open('rb') as stream:meta=self._header(stream)
     if self.path(meta.get('id'))==path:result.append(meta)
    except (OSError,ValueError,TypeError):continue
   return sorted(result,key=lambda p:p['updated'],reverse=True)
 def get(self,ident,wire=False):
  with self.lock,self.path(ident).open('rb') as stream:
   meta=self._header(stream)
   if meta.get('id')!=ident:raise ValueError('本地工程索引不匹配')
   try:
    with gzip.GzipFile(fileobj=stream,mode='rb') as body:raw=body.read(MAX_HTTP_BYTES+1)
   except (EOFError,gzip.BadGzipFile,zlib.error):raise ValueError('本地工程压缩内容损坏或不完整；原文件已保留，请导入有效工程副本') from None
   if len(raw)>MAX_HTTP_BYTES:raise ValueError('工程文件超过容量限制')
   packed=json.loads(raw);record=decode_job(packed)
   if record.get('id')!=ident:raise ValueError('本地工程内容不匹配')
   return packed if wire else record
 def _check_version(self,path,expected):
  previous=None
  if path.exists():
   with path.open('rb') as stream:previous=self._header(stream)
  actual=previous.get('persistedVersion') if previous else None
  if actual!=expected:raise ProjectConflict('工程已在另一个页面更新或删除；当前修改仍在页面中，请重新打开或导出工程副本。')
 def save(self,ident,record,expected):
  path=self.path(ident)
  if not isinstance(record,dict) or record.get('id')!=ident or record.get('saveMode')!='saved' or record.get('kind') not in ('image','web') or not isinstance(record.get('doc'),dict):raise ValueError('保存工程参数无效')
  if record['doc'].get('_projectId')!=ident:raise ValueError('工程内容标识不匹配')
  title=record.get('title')
  if not isinstance(title,str) or len(title)>1000:raise ValueError('工程名称无效或过长')
  measure(record)
  now=int(time.time()*1000)
  meta={'id':ident,'kind':record['kind'],'title':title,'updated':now,'savedAt':now,'persistedAt':now,'persistedVersion':str(uuid.uuid4()),'revision':record.get('revision') or str(uuid.uuid4()),'saveMode':'saved','source':'local-disk','storageVersion':'local-disk-v1'}
  for key in ('width','height'):
   value=record['doc'].get(key)
   if isinstance(value,(int,float)) and not isinstance(value,bool) and 0<value<=1000000:meta[key]=value
  if not isinstance(meta['revision'],str) or len(meta['revision'])>160:raise ValueError('工程版本无效')
  saved={**record,**meta};saved.pop('_expectedVersion',None)
  raw=json.dumps(pack_record(saved),ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
  if len(raw)>MAX_HTTP_BYTES:raise ValueError('工程文件超过容量限制')
  header=json.dumps(meta,ensure_ascii=False,separators=(',',':')).encode('utf8')+b'\n'
  compressed=gzip.compress(raw,compresslevel=1,mtime=0)
  with self.lock:
   self._check_version(path,expected);self.root.mkdir(parents=True,exist_ok=True)
   temp=None
   try:
    with tempfile.NamedTemporaryFile(dir=self.root,prefix='.saving-',suffix='.tmp',delete=False) as stream:
     temp=Path(stream.name);stream.write(header);stream.write(compressed);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)
   finally:
    if temp is not None:temp.unlink(missing_ok=True)
  return meta
 def delete(self,ident,expected):
  with self.lock:
   path=self.path(ident);self._check_version(path,expected);path.unlink(missing_ok=True)
