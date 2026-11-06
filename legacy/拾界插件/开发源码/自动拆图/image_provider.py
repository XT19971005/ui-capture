"""Image transport is independent of the conversational model; never resubmit a generation."""
import hashlib,io,json,os,re,time,uuid,threading,tempfile,subprocess,shutil
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image
from runtime import STATE

BASE='https://api-matrix.tuyoo.com/api/matrix/aimake/v1'
CONNECTION={'provider':'codex','model':'gpt-image-2'}
MODELS={'nano-banana-2':'Nano Banana 2','gpt-image-2':'GPT Image 2','nano-banana-pro':'Nano Banana Pro'}
# GPT Image 2.5 advertises native transparency; always verify returned alpha.
# Other models retain the explicit Pixelcut path.
NATIVE_TRANSPARENCY_MODELS=frozenset(('gpt-image-2.5-flare','gpt-image-2.5-sunburst'))
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
 if data.get('code') not in (0,'0'):raise ValueError('亿创未接受请求，请检查本人连接、模型权限与额度')
 return data.get('data')

def valid_model(model):
 return isinstance(model,str) and bool(re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,95}',model))

_schema_cache={}
_schema_lock=threading.RLock()

def model_schema(model,secret=None):
 if not valid_model(model):raise ValueError('亿创模型标识无效')
 cache_key=(hashlib.sha256((secret or '').encode()).digest(),model)
 with _schema_lock:
  cached=_schema_cache.get(cache_key)
  if cached and time.monotonic()-cached[0]<300:return cached[1]
 value=request('/models/'+model+'/schema',secret=secret)
 if not isinstance(value,dict) or not isinstance(value.get('input'),dict):raise ValueError('亿创模型参数说明暂不可读取，未提交生成')
 with _schema_lock:
  if len(_schema_cache)>=256:_schema_cache.pop(next(iter(_schema_cache)))
  _schema_cache[cache_key]=(time.monotonic(),value)
 return value

class ModelCatalog(list):
 def __init__(self,values,unavailable):
  super().__init__(values);self.unavailable=unavailable

def catalog(secret=None):
 from concurrent.futures import ThreadPoolExecutor
 values=request('/models',secret=secret)
 if not isinstance(values,list):raise ValueError('亿创模型目录格式无效')
 candidates=[m for m in values if isinstance(m,dict) and valid_model(m.get('id')) and m.get('material_type_slug','picture')=='picture']
 unavailable=[]
 def describe(m):
  ident=m['id']
  try:schema=model_schema(ident,secret)
  except ValueError:
   unavailable.append(ident);return None
  props=schema['input'].get('properties',{});required=set(schema['input'].get('required',[]));output=schema.get('output',{}).get('properties',{})
  if 'prompt' not in props or required-{'prompt','ref_images','input_images'} or not {'image_url','image_urls'}.intersection(output):return None
  return {'id':ident,'name':m.get('display_name') or MODELS.get(ident,ident),'reference':bool({'ref_images','input_images'}.intersection(props)),'vector':ident=='recraft-v4-vector'}
 with ThreadPoolExecutor(max_workers=8) as pool:values=[value for value in pool.map(describe,candidates) if value]
 return ModelCatalog(values,unavailable)


def rasterize_vector(raw):
 import xml.etree.ElementTree as ET
 if len(raw)>4*1024*1024 or b'<!' in raw:raise ValueError('矢量图片格式或大小不受支持')
 try:root=ET.fromstring(raw)
 except ET.ParseError:raise ValueError('矢量图片无法读取') from None
 allowed={'svg','g','path','rect','circle','ellipse','polygon','polyline','line','defs','linearGradient','radialGradient','stop','clipPath','mask','pattern','use','title','desc'}
 for el in root.iter():
  if el.tag.split('}')[-1] not in allowed:raise ValueError('矢量图片含不支持的外部资源或元素')
  for name,value in el.attrib.items():
   if name.lower().startswith('on') or name.split('}')[-1]=='href' and not value.startswith('#') or '@import' in value.lower():raise ValueError('矢量图片不能引用外部资源')
   for ref in re.findall(r'url\((.*?)\)',value,re.I):
    if not ref.strip(" \"' ").startswith('#'):raise ValueError('矢量图片不能引用外部资源')
 box=root.get('viewBox','0 0 1024 1024').replace(',',' ').split()
 try:
  width=float(root.get('width',box[2]));height=float(root.get('height',box[3]))
 except (ValueError,IndexError):raise ValueError('矢量图片尺寸无效') from None
 if not 0<width<=6000 or not 0<height<=6000 or width*height>6000000:raise ValueError('矢量图片超过安全尺寸')
 root.set('width',str(max(1,round(width))));root.set('height',str(max(1,round(height))))
 ET.register_namespace('','http://www.w3.org/2000/svg')
 raw=ET.tostring(root,encoding='utf-8',xml_declaration=False)
 node=shutil.which('node')
 if not node:raise ValueError('矢量预览运行环境尚未就绪')
 script="const c=require('@napi-rs/canvas');let b=[];process.stdin.on('data',x=>b.push(x));process.stdin.on('end',async()=>{try{const im=await c.loadImage(Buffer.concat(b));if(!im.width||!im.height||Math.max(im.width,im.height)>6000||im.width*im.height>6000000)throw Error();const out=c.createCanvas(im.width,im.height);out.getContext('2d').drawImage(im,0,0);process.stdout.write(out.toBuffer('image/png'));}catch{process.exitCode=1;}});"
 try:result=subprocess.run([node,'-e',script],input=raw,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=Path(__file__).resolve().parents[4],timeout=20)
 except subprocess.TimeoutExpired:raise ValueError('矢量图片预览超时') from None
 if result.returncode or not result.stdout.startswith(b'\x89PNG'):raise ValueError('矢量图片暂不能转换为画布素材')
 return result.stdout


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
 with Image.open(images[0]) as source:ratio=source.width/source.height;target_area=max(655360,min(8294400,source.width*source.height))
 if not 1/3<=ratio<=3:raise ValueError('亿创自定义画布仅支持1:3至3:1，当前原图比例不支持，未改变比例或提交生成')
 candidates=[]
 for width in range(16,3841,16):
  height=round(width/ratio/16)*16;area=width*height
  if height<16 or height>3840 or not 655360<=area<=8294400:continue
  error=abs(width/height-ratio)/ratio
  if error<=.001:candidates.append((abs(area-target_area),error,width,height))
 if not candidates:raise ValueError('亿创暂不能保持该画布比例，未提交生成')
 _,_,width,height=min(candidates)
 return {'width':width,'height':height}

def validate_input(value,schema,label='生图参数'):
 types=schema.get('type',[]);types=[types] if isinstance(types,str) else types
 matches={'string':isinstance(value,str),'integer':type(value) is int,'number':type(value) in (int,float),'boolean':type(value) is bool,'array':isinstance(value,list),'object':isinstance(value,dict),'null':value is None}
 if types and not any(matches.get(kind,False) for kind in types):raise ValueError(label+'类型与模型要求不符，尚未提交生成')
 if 'enum' in schema and value not in schema['enum']:raise ValueError(label+'不在模型支持的范围内')
 if isinstance(value,str) and (len(value)<schema.get('minLength',0) or len(value)>schema.get('maxLength',32000)):raise ValueError(label+'长度与模型要求不符')
 if type(value) in (int,float) and (value<schema.get('minimum',float('-inf')) or value>schema.get('maximum',float('inf'))):raise ValueError(label+'超出模型范围')
 if isinstance(value,list):
  if len(value)<schema.get('minItems',0) or len(value)>schema.get('maxItems',16):raise ValueError(label+'数量与模型要求不符')
  for item in value:validate_input(item,schema.get('items',{}),label)
 if isinstance(value,dict):
  for name in schema.get('required',[]):
   if name not in value:raise ValueError(label+'缺少参数：'+name)
  for name,item in value.items():validate_input(item,schema.get('properties',{}).get(name,{}),label+' '+name)


def generation_input(model,prompt,images,urls,schema=None):
 if schema is not None:
  props=schema.get('input',{}).get('properties',{})
  if 'prompt' not in props:raise ValueError('所选模型不是提示词生图模型，尚未提交生成')
  limit=props['prompt'].get('maxLength',32000);minimum=props['prompt'].get('minLength',5 if model.startswith('nano-banana') else 1)
  if not isinstance(prompt,str) or not prompt.strip() or not minimum<=len(prompt)<=limit:raise ValueError('所选模型提示词需要'+str(minimum)+'至'+str(limit)+'字符，未截断或提交生成')
  result={'prompt':prompt}
  ref=next((name for name in ('input_images','ref_images') if name in props),None)
  if images and not ref:raise ValueError('所选模型仅支持文生图，不支持参考图片；请改选支持参考图的模型')
  if model.startswith('nano-banana'):
   for file in images:
    with Image.open(file) as source:
     if min(source.size)<300 or Path(file).stat().st_size>30*1024*1024:raise ValueError('Nano Banana参考图宽高均须至少300像素且不超过30MB；未改变原图或提交生成')
  if ref:
   maximum=props[ref].get('maxItems',3 if model=='nano-banana' else 14)
   if not props[ref].get('minItems',0)<=len(images)<=maximum:raise ValueError('所选模型最多支持'+str(maximum)+'张参考图，未上传或生成')
   result[ref]=urls
  for name in ('resolution','quality','output_format','sequential_image_generation','tier','image_size'):
   if name in props and 'default' in props[name]:result[name]=props[name]['default']
  if 'output_format' in props and 'png' in props['output_format'].get('enum',[]):result['output_format']='png'
  ratio=1
  if images:
   with Image.open(images[0]) as im:ratio=im.width/im.height
  choices=props.get('aspect_ratio',{}).get('enum',[])
  if choices:
   candidates=[(abs(int(v.split(':')[0])/int(v.split(':')[1])-ratio)/ratio,v) for v in choices if isinstance(v,str) and re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*',v)]
   error,chosen=min(candidates) if candidates else (1,None)
   if error<=.001:result['aspect_ratio']=chosen
   elif 'width' in props and 'height' in props and model.startswith('gpt-image-'):result.update(dimensions(images))
   else:raise ValueError('所选模型不支持当前原图比例；未拉伸原图或提交生成')
  elif images:raise ValueError('所选模型不能指定参考画布比例，尚未上传或生成')
  for name in schema.get('input',{}).get('required',[]):
   if name not in result:raise ValueError('所选模型还需要参数：'+name+'，尚未提交生成')
  probe=dict(result)
  if ref and images and not urls:probe[ref]=['https://reference.invalid/image.png']*len(images)
  validate_input(probe,schema.get('input',{}))
  return result
 if model=='gpt-image-2':return {'prompt':prompt,'input_images':urls,'output_format':'png','quality':'high',**dimensions(images)}
 if model not in ('nano-banana-2','nano-banana-pro'):raise ValueError('请选择已适配的图片模型')
 if not 5<=len(prompt)<=5000:raise ValueError('Nano Banana 提示词须为5至5000字符，未提交生成')
 if len(images)>14:raise ValueError('Nano Banana 最多支持14张参考图，未上传或生成')
 ratios=['1:1','2:3','3:2','3:4','4:3','4:5','5:4','9:16','16:9','21:9']
 if model=='nano-banana-2':ratios+=['9:21','1:4','4:1','1:8','8:1']
 ratio=1
 for index,file in enumerate(images):
  with Image.open(file) as im:
   if min(im.size)<300 or Path(file).stat().st_size>30*1024*1024:raise ValueError('Nano Banana参考图宽高均须至少300像素且不超过30MB；未改变原图或提交生成')
   if index==0:ratio=im.width/im.height
 chosen=min(ratios,key=lambda v:abs(int(v.split(':')[0])/int(v.split(':')[1])-ratio))
 a,b=map(int,chosen.split(':'))
 if abs(a/b-ratio)/ratio>.001:raise ValueError('所选Nano Banana模型不支持当前原图比例；未拉伸或提交生成，请改用GPT Image 2')
 return {'prompt':prompt,'ref_images':urls,'aspect_ratio':chosen,'resolution':'1K'}

def remove_background(source,target,secret,cancelled=lambda:False,timeout=900,on_status=None):
 """Pixelcut is a separate billed task. Never resubmit either upstream stage."""
 notice=on_status or (lambda _:None)
 if cancelled():raise InterruptedError('已取消；尚未提交Pixelcut抠图')
 notice('Pixelcut正在上传生图结果…')
 url=upload(source,secret,cancelled);ident=uuid.uuid4().hex
 receipt=STATE/('亿创抠图任务_'+ident+'.json')
 record={'requestId':ident,'model':'pixelcut-background-removal','state':'submitting','sourceSHA256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'createdAt':time.time()}
 def save():receipt.write_text(json.dumps(record),encoding='utf8')
 if cancelled():raise InterruptedError('已取消；尚未提交Pixelcut抠图')
 save()
 try:job=request('/models/pixelcut-background-removal/generate',{'input':{'input_image':url,'output_format':'rgba'},'request_num':1,'client_request_id':ident},secret)
 except Exception:
  record['state']='uncertain';save();raise
 gid=job.get('gen_id') if isinstance(job,dict) else None
 if not isinstance(gid,str) or not gid or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-' for c in gid):raise ValueError('Pixelcut提交结果未确认，不会重复提交')
 record.update(genId=gid,state='submitted');save();started=time.monotonic();poll_errors=0
 while True:
  if cancelled():raise InterruptedError('已停止等待；Pixelcut任务已提交，不会重复生成或抠图')
  if time.monotonic()-started>timeout:raise ValueError('Pixelcut尚未完成，任务号已保留；未重复生图或抠图')
  notice('亿创生图已完成，Pixelcut正在去背景…')
  try:result=request('/models/pixelcut-background-removal/'+gid+'/status',secret=secret)
  except ValueError as error:
   poll_errors+=1
   if poll_errors>=3 or not any(s in str(error) for s in ('连接中断','HTTP 502','HTTP 503','HTTP 504')):raise
   notice('Pixelcut进度读取中断，正在查询原任务，不重复提交…');time.sleep(1);continue
  poll_errors=0
  items=result.get('outputs',[])
  if any(item.get('item_status')=='failed' for item in items):raise ValueError('Pixelcut抠图失败，未应用不透明结果；没有重新生图')
  done=next((item for item in items if item.get('item_status')=='succeeded' and isinstance(item.get('data'),dict) and (item['data'].get('image_url') or item['data'].get('image_urls'))),None)
  if done:break
  time.sleep(.6)
 raw=bytearray()
 output_url=done['data'].get('image_url') or next(iter(done['data'].get('image_urls') or []),None)
 with storage_request('GET',output_url) as response:
  if response.status!=200:raise ValueError('Pixelcut结果下载失败，原任务未重提')
  for chunk in response.stream(65536):
   if cancelled():raise InterruptedError('已取消Pixelcut结果下载')
   raw.extend(chunk)
   if len(raw)>64*1024*1024:raise ValueError('Pixelcut结果超过64MB限制')
 with Image.open(io.BytesIO(raw)) as im:
  if max(im.size)>6000 or im.width*im.height>6000000:raise ValueError('图片超过服务器画布上限')
  im.load()
  if im.mode!='RGBA' or im.getchannel('A').getextrema()[0]!=0 or not im.getchannel('A').getbbox():raise ValueError('Pixelcut未返回有效透明RGBA，未应用结果')
  size=list(im.size)
 with Image.open(source) as original:
  if tuple(size)!=original.size:raise ValueError('Pixelcut改变了画幅，未自动缩放或应用')
 if cancelled():raise InterruptedError('已取消，未应用Pixelcut结果')
 target=Path(target);tmp=target.with_name(target.name+'.'+ident+'.tmp')
 try:tmp.write_bytes(raw);os.replace(tmp,target)
 finally:tmp.unlink(missing_ok=True)
 record.update(state='completed',outputSHA256=hashlib.sha256(raw).hexdigest());save()
 return {'provider':'aimake','model':'pixelcut-background-removal','genId':gid,'sourceGeneratedSHA256':record['sourceSHA256'],'size':size}


def generate_transparent(prompt,images,target,cancelled,timeout,on_status,**kwargs):
 notice=on_status or (lambda _:None)
 if cancelled():raise InterruptedError('已取消')
 secret=key()
 if not any(m.get('id')=='pixelcut-background-removal' for m in request('/models',secret=secret)):raise ValueError('本人亿创未提供Pixelcut抠图，尚未提交生图')
 target=Path(target)
 with tempfile.TemporaryDirectory(prefix='pixelcut-stage-',dir=target.parent) as folder:
  rgb=Path(folder)/'generated.png'
  instruction=prompt+'\n阶段输出说明：前文的透明要求描述最终成品；为交给Pixelcut去背景，本阶段背景使用纯白，该阶段说明仅覆盖背景输出要求，避免与RGBA指令冲突，其他主体要求全部不变。不得添加阴影、底座、棋盘格、描边或彩色标线，不增加参考中不存在的对象。保留原有白色实体、细线、镂空和柔和边缘，不因换底改变造型、大小、方向、光照、颜色或在画布上的位置。'
  record=generate(instruction,images,rgb,transparent=False,cancelled=cancelled,timeout=timeout,on_status=on_status,**kwargs)
  post=remove_background(rgb,target,secret,cancelled,timeout,on_status)
  record.update(file=str(target),transparent=True,size=post['size'],postprocessing=post)
  notice('Pixelcut透明化完成，正在准备素材校对…')
  return record


def generate(prompt,images,target,transparent=False,cancelled=lambda:False,timeout=900,on_status=None,**unused):
 value=settings();model=value['model']
 if transparent and model not in NATIVE_TRANSPARENCY_MODELS:return generate_transparent(prompt,images,target,cancelled,timeout,on_status,**unused)
 secret=key(value);notice=on_status or (lambda _:None)
 if not any(m['id']==model for m in catalog(secret)):raise ValueError('所选亿创图片模型不可用')
 if cancelled():raise InterruptedError('已取消')
 instruction=prompt+('\n保真编辑优先级：可见原图的轮廓、内部孔洞、纹理、非对称细节、颜色和朝向是依据，不是风格灵感；只推断被遮挡或出画的缺失部分，不重新设计、不变成同类另一款。保持第一张参考画布中的相对位置和比例，不自动居中、放大主体或重新排版。其他参考只帮助定位目标，不把标线或其他对象画进结果。' if unused.get('allow_identity_change') is False else '')+('\n必须输出真正RGBA透明PNG，背景Alpha为0；禁止棋盘格、纯色底或彩笔标线。' if transparent else '')
 schema=model_schema(model,secret)
 generation_input(model,instruction,images,[],schema=schema);notice('亿创正在上传本层参考…');urls=[upload(file,secret,cancelled) for file in images]
 model_input=generation_input(model,instruction,images,urls,schema=schema)
 if transparent and model in NATIVE_TRANSPARENCY_MODELS:model_input['background']='transparent'
 validate_input(model_input,schema['input'])
 if cancelled():raise InterruptedError('已取消；尚未提交亿创生成')
 ident=uuid.uuid4().hex;receipt=STATE/('亿创任务_'+ident+'.json');record={'requestId':ident,'model':model,'state':'submitting','createdAt':time.time()}
 receipt.write_text(json.dumps(record),encoding='utf-8')
 if cancelled():
  record['state']='cancelled-before-submit';receipt.write_text(json.dumps(record),encoding='utf-8');raise InterruptedError('已取消；尚未提交亿创生成')
 try:job=request('/models/'+model+'/generate',{'input':model_input,'request_num':1,'client_request_id':ident},secret)
 except Exception:
  record['state']='uncertain';receipt.write_text(json.dumps(record),encoding='utf-8');raise
 gen_id=job.get('gen_id') if isinstance(job,dict) else None
 if not isinstance(gen_id,str) or not gen_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-' for c in gen_id):raise ValueError('亿创提交结果未确认，不会重复提交')
 record.update(genId=gen_id,state='submitted');receipt.write_text(json.dumps(record),encoding='utf-8');started=time.monotonic();poll_errors=0
 while True:
  if cancelled():raise InterruptedError('已停止等待；亿创原任务已提交，不会重复生成')
  if time.monotonic()-started>timeout:raise ValueError('亿创原任务尚未完成，任务号已保留，未自动重提')
  try:result=request('/models/'+model+'/'+gen_id+'/status',secret=secret)
  except ValueError as error:
   poll_errors+=1
   if poll_errors>=3 or not any(s in str(error) for s in ('连接中断','HTTP 502','HTTP 503','HTTP 504')):raise
   notice('亿创进度读取中断，正在查询原任务，不重复提交…');time.sleep(1);continue
  poll_errors=0;items=result.get('outputs',[])
  failed=[item for item in items if item.get('item_status')=='failed']
  if failed:raise ValueError('亿创本层生成失败，原图保留，未自动重试')
  done=next((item for item in items if item.get('item_status')=='succeeded' and isinstance(item.get('data'),dict) and (item['data'].get('image_url') or item['data'].get('image_urls'))),None)
  if done:break
  notice('亿创正在生成本层素材…');time.sleep(.6)
 target=Path(target);raw=bytearray()
 output_url=done['data'].get('image_url') or next(iter(done['data'].get('image_urls') or []),None)
 with storage_request('GET',output_url) as response:
  if response.status!=200:raise ValueError('亿创结果下载未完成，原任务未重提')
  for chunk in response.stream(65536):
   if cancelled():raise InterruptedError('已取消下载')
   raw.extend(chunk)
   if len(raw)>64*1024*1024:raise ValueError('亿创图片超过64MB限制')
 if model=='recraft-v4-vector' and not raw.startswith(b'\x89PNG'):raw=rasterize_vector(bytes(raw))
 with Image.open(io.BytesIO(raw)) as image:
  if max(image.size)>6000 or image.width*image.height>6000000:raise ValueError('图片超过服务器画布上限')
  image.load()
  if transparent and image.mode=='RGBA' and not image.getchannel('A').getbbox():raise ValueError('亿创返回了全透明空白图片，未应用')
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
