"""Explicit saves only: atomic project files, bounded deduplicated bodies, cheap lists."""
import base64, gzip, hashlib, io, json, os, re, tempfile, threading, time, uuid, zlib
from pathlib import Path
from image_wire import decode_job, measure, IMAGE_FIELDS, MAX_HTTP_BYTES, MAX_IMAGES

HEADER_LIMIT=65536
_STORE_LOCKS={}
_STORE_LOCKS_GUARD=threading.Lock()
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
 def __init__(self,root):
  self.root=Path(root)
  with _STORE_LOCKS_GUARD:self.lock=_STORE_LOCKS.setdefault(os.path.normcase(str(self.root.resolve())),threading.RLock())
 def _legacy_path(self,ident):
  if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',ident):raise ValueError('工程标识无效')
  path=self.root/(hashlib.sha256(ident.encode('utf8')).hexdigest()+'.shijie-project')
  if path.resolve().parent!=self.root.resolve():raise ValueError('工程路径无效')
  return path
 def _entries(self):
  if not self.root.exists():return
  for path in self.root.glob('*.shijie-project'):
   if path.is_symlink() or path.resolve().parent!=self.root.resolve():continue
   try:
    with path.open('rb') as stream:meta=self._header(stream)
    self._legacy_path(meta.get('id'))
    yield path,meta
   except (OSError,ValueError,TypeError):continue
 def path(self,ident):
  legacy=self._legacy_path(ident)
  matches=[(p,m) for p,m in self._entries() if m['id']==ident]
  return max(matches,key=lambda pair:(pair[1]['updated'],pair[0].name))[0] if matches else legacy
 def _destination(self,title,current):
  name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',title).strip(' .')[:80].rstrip(' .') or '未命名工程'
  if re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])',name.split('.')[0].rstrip(' ')):name='工程_'+name
  index=1
  while True:
   path=self.root/(name+('' if index==1 else f'（{index}）')+'.shijie-project')
   if path.resolve().parent!=self.root.resolve():raise ValueError('工程路径无效')
   if not path.exists() or os.path.normcase(str(path))==os.path.normcase(str(current)):return path
   index+=1
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
   entries={}
   for path,meta in self._entries():
    old=entries.get(meta['id'])
    if old is None or (meta['updated'],path.name)>(old[1]['updated'],old[0].name):entries[meta['id']]=(path,meta)
   return sorted((meta for _,meta in entries.values()),key=lambda p:p['updated'],reverse=True)
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
  self._legacy_path(ident)
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
  thumbnail=record.get('thumbnail')
  if thumbnail is not None:
   if not isinstance(thumbnail,str) or len(thumbnail)>48*1024 or not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',thumbnail):raise ValueError('工程封面格式无效或超过48KiB限制')
   try:
    from PIL import Image
    with Image.open(io.BytesIO(base64.b64decode(thumbnail.split(',',1)[1],validate=True))) as image:
     if image.format not in ('PNG','JPEG','WEBP') or image.width>480 or image.height>300:raise ValueError('工程封面尺寸过大')
     image.verify()
   except (OSError,ValueError) as error:raise ValueError('工程封面图片无效') from error
   meta.update(thumbnail=thumbnail,thumbnailRevision=meta['revision'])
  saved={**record,**meta};saved.pop('_expectedVersion',None)
  raw=json.dumps(pack_record(saved),ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
  if len(raw)>MAX_HTTP_BYTES:raise ValueError('工程文件超过容量限制')
  header=json.dumps(meta,ensure_ascii=False,separators=(',',':')).encode('utf8')+b'\n'
  if len(header)>HEADER_LIMIT:raise ValueError('工程索引过大，原工程已保留')
  compressed=gzip.compress(raw,compresslevel=1,mtime=0)
  with self.lock:
   path=self.path(ident);self._check_version(path,expected);self.root.mkdir(parents=True,exist_ok=True)
   destination=self._destination(title,path)
   temp=None
   try:
    with tempfile.NamedTemporaryFile(dir=self.root,prefix='.saving-',suffix='.tmp',delete=False) as stream:
     temp=Path(stream.name);stream.write(header);stream.write(compressed);stream.flush();os.fsync(stream.fileno())
    # Keep the previous complete bytes available if writing the new version
    # fails after a title change. IDs and CAS versions do not depend on names.
    if path.exists() and os.path.normcase(str(path))!=os.path.normcase(str(destination)):os.replace(path,destination)
    os.replace(temp,destination)
   finally:
    if temp is not None:temp.unlink(missing_ok=True)
  return meta
 def delete(self,ident,expected):
  with self.lock:
   path=self.path(ident);self._check_version(path,expected);path.unlink(missing_ok=True)
 def archive_browser(self,record):
  if not isinstance(record,dict) or not isinstance(record.get('doc'),dict):raise ValueError('旧工程内容无效')
  self._legacy_path(record.get('id'))
  current=self.get(record['id']) # Never remove a browser copy without an openable main project.
  raw=json.dumps(record,ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf8')
  ident='browser-'+hashlib.sha256(raw).hexdigest()
  archive=LocalProjectStore(self.root/'旧版浏览器备份')
  doc={**record['doc'],'_projectId':ident}
  value={'id':ident,'kind':record.get('kind'),'title':current['title'],'saveMode':'saved','doc':doc,'legacyOriginal':record}
  with self.lock:
   previous=next((p for p in archive.list() if p['id']==ident),None)
   if previous is None:archive.save(ident,value,None)
   restored=archive.get(ident)
   if restored.get('legacyOriginal')!=record:raise ValueError('旧工程备份回读不一致，浏览器原记录保留')
   return {'verified':True,'id':record['id'],'archive':archive.path(ident).name}
