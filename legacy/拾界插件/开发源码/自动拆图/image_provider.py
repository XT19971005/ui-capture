"""Image transport is independent of the conversational model; never resubmit a generation."""
import hashlib,io,json,os,time,uuid,threading
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image
from runtime import STATE

BASE='https://api-matrix.tuyoo.com/api/matrix/aimake/v1'
MODELS={'gpt-image-2':'GPT Image 2'}
CONNECTION={'provider':'codex','model':'gpt-image-2'}
_uploads={}
_upload_lock=threading.RLock()

def settings():return CONNECTION

def key(config=None):
 value=(config or CONNECTION).get('key')
 if not value:raise ValueError('请在模型设置中配置本人的亿创 Key')
 return value

def request(route,body=None,secret=None):
 if not route.startswith('/') or route.startswith('//'):raise ValueError('亿创接口路径无效')
 try:
  with requests.request('POST' if body is not None else 'GET',BASE+route,headers={'X-API-KEY':secret or key()},json=body,timeout=(10,60),allow_redirects=False) as response:
   if response.status_code!=200:raise ValueError('亿创请求未完成（HTTP '+str(response.status_code)+'）')
   data=response.json()
 except requests.RequestException:raise ValueError('亿创连接中断；生成提交结果未知时不会自动重试') from None
 if not isinstance(data,dict) or data.get('code') not in (0,'0'):raise ValueError('亿创未接受请求，请检查本人连接、模型权限与额度')
 return data.get('data')

def catalog(secret=None):
 values=request('/models',secret=secret)
 if not isinstance(values,list):raise ValueError('亿创模型目录格式无效')
 return [{'id':m['id'],'name':MODELS[m['id']]} for m in values if isinstance(m,dict) and m.get('id') in MODELS]

def safe_https(url):
 if not isinstance(url,str) or len(url)>16384:raise ValueError('亿创返回的文件链接无效')
 parsed=urlparse(url)
 if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None,443):raise ValueError('亿创返回的文件链接无效')
 return url

# Pin the checked address while retaining the original HTTPS certificate identity.
# No redirect, proxy, cookie, ambient credential or API key reaches signed storage.
from contextlib import contextmanager
@contextmanager
def storage_request(method,url,headers=None,body=None):
 import ipaddress,socket,urllib3
 parsed=urlparse(safe_https(url))
 try:addresses=list(dict.fromkeys(entry[4][0] for entry in socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)))
 except socket.gaierror:raise ValueError('亿创文件域名暂不可读取') from None
 if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):raise ValueError('亿创文件链接不能指向本机或内网')
 headers=dict(headers or {})
 if any(not isinstance(k,str) or not isinstance(v,str) or any(c in k+v for c in '\r\n\0') or k.lower() in ('host','authorization','proxy-authorization','cookie','x-api-key') for k,v in headers.items()):raise ValueError('亿创签名上传头无效')
 headers['Host']=parsed.hostname
 pool=urllib3.HTTPSConnectionPool(addresses[0],443,server_hostname=parsed.hostname,assert_hostname=parsed.hostname,cert_reqs='CERT_REQUIRED',timeout=urllib3.Timeout(connect=10,read=90))
 response=None
 try:
  response=pool.urlopen(method,(parsed.path or '/')+('?' + parsed.query if parsed.query else ''),body=body,headers=headers,redirect=False,retries=False,preload_content=False)
  yield response
 except urllib3.exceptions.HTTPError:raise ValueError('亿创文件传输未完成；不会重提生成') from None
 finally:
  if response is not None:response.close()
  pool.close()

def upload(file,secret,cancelled):
 if cancelled():raise InterruptedError('已取消')
 file=Path(file);fingerprint=(hashlib.sha256(secret.encode()).digest(),hashlib.sha256(file.read_bytes()).digest())
 with _upload_lock:
  cached=_uploads.get(fingerprint)
  if cached and time.monotonic()-cached[0]<600:return cached[1]
 data=request('/uploads/files',{'filename':file.name,'mime_type':'image/png'},secret)
 if not isinstance(data,dict) or data.get('method')!='PUT':raise ValueError('亿创上传回执无效')
 # Signed storage requests never carry the API key.
 with file.open('rb') as stream,storage_request('PUT',data['upload_url'],headers=data.get('headers') or {},body=stream) as response:
  if not 200<=response.status<300:raise ValueError('参考图片上传未完成，尚未生成')
 if cancelled():raise InterruptedError('已取消')
 confirmed=request('/uploads/files/complete',{'object_key':data['object_key'],'filename':file.name},secret)
 if cancelled():raise InterruptedError('已取消；参考已上传，尚未提交生成')
 url=safe_https(confirmed['url'])
 with _upload_lock:
  _uploads[fingerprint]=(time.monotonic(),url)
  while len(_uploads)>64:_uploads.pop(next(iter(_uploads)))
 return url

def dimensions(images):
 if not images:return {'width':1024,'height':1024}
 with Image.open(images[0]) as source:ratio=source.width/source.height
 if not 1/3<=ratio<=3:raise ValueError('亿创自定义画布仅支持1:3至3:1，当前原图比例不支持，未改变比例或提交生成')
 candidates=[]
 for width in range(16,3841,16):
  height=round(width/ratio/16)*16;area=width*height
  if height<16 or height>3840 or not 655360<=area<=8294400:continue
  error=abs(width/height-ratio)/ratio
  if error<=.001:candidates.append((abs(area-1048576),error,width,height))
 if not candidates:raise ValueError('亿创暂不能保持该画布比例，未提交生成')
 _,_,width,height=min(candidates)
 return {'width':width,'height':height}

def generate(prompt,images,target,transparent=False,cancelled=lambda:False,timeout=900,on_status=None,**unused):
 value=settings();model=value['model'];secret=key(value);notice=on_status or (lambda _:None)
 if not any(m['id']==model for m in catalog(secret)):raise ValueError('所选亿创图片模型不可用')
 if cancelled():raise InterruptedError('已取消')
 shape=dimensions(images);notice('亿创正在上传本层参考…');urls=[upload(file,secret,cancelled) for file in images]
 if cancelled():raise InterruptedError('已取消；尚未提交亿创生成')
 ident=uuid.uuid4().hex;receipt=STATE/('亿创任务_'+ident+'.json');record={'requestId':ident,'model':model,'state':'submitting','createdAt':time.time()}
 receipt.write_text(json.dumps(record),encoding='utf-8')
 instruction=prompt+('\n必须输出真正RGBA透明PNG，背景Alpha为0；禁止棋盘格、纯色底或彩笔标线。' if transparent else '')
 if cancelled():
  record['state']='cancelled-before-submit';receipt.write_text(json.dumps(record),encoding='utf-8');raise InterruptedError('已取消；尚未提交亿创生成')
 try:job=request('/models/'+model+'/generate',{'input':{'prompt':instruction,'input_images':urls,'output_format':'png','quality':'high',**shape},'request_num':1,'client_request_id':ident},secret)
 except Exception:
  record['state']='uncertain';receipt.write_text(json.dumps(record),encoding='utf-8');raise
 gen_id=job.get('gen_id') if isinstance(job,dict) else None
 if not isinstance(gen_id,str) or not gen_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-' for c in gen_id):raise ValueError('亿创提交结果未确认，不会重复提交')
 record.update(genId=gen_id,state='submitted');receipt.write_text(json.dumps(record),encoding='utf-8');started=time.monotonic()
 while True:
  if cancelled():raise InterruptedError('已停止等待；亿创原任务已提交，不会重复生成')
  if time.monotonic()-started>timeout:raise ValueError('亿创原任务尚未完成，任务号已保留，未自动重提')
  result=request('/models/'+model+'/'+gen_id+'/status',secret=secret);items=result.get('outputs',[])
  failed=[item for item in items if item.get('item_status')=='failed']
  if failed:raise ValueError('亿创本层生成失败，原图保留，未自动重试')
  done=next((item for item in items if item.get('item_status')=='succeeded' and isinstance(item.get('data'),dict) and item['data'].get('image_url')),None)
  if done:break
  notice('亿创正在生成本层素材…');time.sleep(.6)
 target=Path(target);raw=bytearray()
 with storage_request('GET',done['data']['image_url']) as response:
  if response.status!=200:raise ValueError('亿创结果下载未完成，原任务未重提')
  for chunk in response.stream(65536):
   if cancelled():raise InterruptedError('已取消下载')
   raw.extend(chunk)
   if len(raw)>64*1024*1024:raise ValueError('亿创图片超过64MB限制')
 with Image.open(io.BytesIO(raw)) as image:
  if max(image.size)>6000 or image.width*image.height>6000000:raise ValueError('亿创结果超过画布尺寸限制，未解码或缩小')
  image.load()
  if transparent and (image.mode!='RGBA' or image.getchannel('A').getextrema()[0]>0):raise ValueError('亿创本层未提供真实透明通道，结果待校对，未伪造透明素材')
  size=list(image.size)
 target.write_bytes(raw);record.update(state='completed',sha256=hashlib.sha256(raw).hexdigest());receipt.write_text(json.dumps(record),encoding='utf-8')
 return {'file':str(target),'size':size,'transparent':transparent,'actualImageGeneration':True,'provider':'aimake','model':model,'genId':gen_id}

class ImageClient:
 def generate(self,*args,**kwargs):
  if settings()['provider']=='aimake':return generate(*args,**kwargs)
  from codex_client import CLIENT as codex
  return codex.generate(*args,**kwargs)

CLIENT=ImageClient()
