"""Assistant TYGPT PAT API and Codex; image generation remains separate."""
import base64,ctypes,json,mimetypes,os,threading,uuid
from pathlib import Path
import requests
from runtime import STATE

BASE='https://zxty.tuyoo.com/aichat/v1'
CONFIG=STATE/'assistant-tygpt.local.json'
_lock=threading.RLock()

def protect(value,decrypt=False):
 if os.name!='nt':raise ValueError('请在本人的Windows电脑配置TYGPT连接')
 from ctypes import wintypes
 class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]
 legacy=decrypt and not value.startswith('dpapi:')
 raw=(bytes.fromhex(value) if legacy else base64.b64decode(value[6:],validate=True)) if decrypt else value.encode('utf8')
 buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));target=Blob()
 crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
 kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
 call=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
 if not call(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('无法读取本人TYGPT凭据，请重新配置')
 try:
  data=ctypes.string_at(target.data,target.size)
  return data.decode('utf-16-le' if legacy else 'utf8') if decrypt else 'dpapi:'+base64.b64encode(data).decode('ascii')
 finally:kernel.LocalFree(target.data)

def read_config():
 try:
  if CONFIG.stat().st_size>32768:raise ValueError()
  config=json.loads(CONFIG.read_text('utf-8-sig'))
  if not isinstance(config,dict) or config.get('baseUrl')!=BASE or not isinstance(config.get('keyEncrypted'),str) or not config['keyEncrypted'].startswith('dpapi:'):raise ValueError()
  return config
 except (OSError,ValueError,TypeError):raise ValueError('尚未配置有效TYGPT PAT，请在助手连接中填写本人的PAT') from None


def gateway_key():
 value=protect(read_config()['keyEncrypted'],True)
 if not isinstance(value,str) or not value or len(value)>4096 or any(c in value for c in '\r\n\0'):raise ValueError('TYGPT凭据不可读取，请重新配置本人的PAT')
 return value


class _TygptError(ValueError):
 """Static, credential-free errors that must survive JSON parsing guards."""


def _http_error(code,action):
 detail={401:'PAT无效或已过期，请重新配置本人的PAT',403:'当前PAT没有所需能力或模型权限',429:'服务限流或当前额度受限，请稍后检查'}.get(code,'服务未接受请求，请检查连接与模型配置')
 raise _TygptError('TYGPT'+action+'失败（HTTP '+str(code)+'）：'+detail+'；未自动重试')


def _reasoning_effort(model):
 supported=model.get('reasoning_efforts')
 if not isinstance(supported,list):return None
 allowed={'none','minimal','low','medium','high','xhigh','max','ultra'}
 efforts=[v for v in supported if isinstance(v,str) and v in allowed]
 return next((v for v in ('medium','low') if v in efforts),efforts[0] if efforts else None)


def gateway_models(key=None):
 try:
  with requests.get(BASE+'/models',headers={'Authorization':'Bearer '+(key or gateway_key())},timeout=(10,30),allow_redirects=False) as response:
   if response.status_code!=200:_http_error(response.status_code,'模型目录读取')
   data=response.json()
 except _TygptError:raise
 except requests.Timeout:raise _TygptError('TYGPT模型目录读取超时，未自动重试') from None
 except requests.RequestException:raise ValueError('TYGPT模型目录连接未完成，请检查PAT与网络') from None
 except (ValueError,TypeError):raise ValueError('TYGPT模型目录读取未完成，请检查PAT与模型权限') from None
 entries=data if isinstance(data,list) else next((data[k] for k in ('data','list','models') if isinstance(data,dict) and isinstance(data.get(k),list)),None)
 if entries is None:raise ValueError('TYGPT模型目录格式无效，未使用虚构模型')
 result=[];seen=set()
 for entry in entries:
  ident=entry if isinstance(entry,str) else entry.get('id') if isinstance(entry,dict) else None
  if not isinstance(ident,str) or not ident.strip() or len(ident)>200 or ident in seen:continue
  name=entry.get('name') if isinstance(entry,dict) else ident
  item={'id':ident,'name':name if isinstance(name,str) and name else ident}
  if isinstance(entry,dict):
   if isinstance(entry.get('capabilities'),dict):item['capabilities']={k:v for k,v in entry['capabilities'].items() if k in ('image','audio','video','file') and type(v) is bool}
   if isinstance(entry.get('reasoning_efforts'),list):item['reasoning_efforts']=[v for v in entry['reasoning_efforts'] if isinstance(v,str)]
   if type(entry.get('high_cost')) is bool:item['high_cost']=entry['high_cost']
  result.append(item);seen.add(ident)
 return result


def _default_model(models):
 visual=[m for m in models if m.get('capabilities',{}).get('image') is not False]
 return next((ident for ident in ('gpt-6.1-sol','gpt-6-sol') if any(m['id']==ident for m in visual)),visual[0]['id'] if visual else models[0]['id'] if models else '')


def validate_pat(key):
 # The official API authenticates before rejecting an empty message. This
 # exact parameter-validation response proves PAT access without generation.
 try:
  with requests.post(BASE+'/agent/chat',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json={'message':'','max_retries':0,'stream':False},timeout=(10,30),allow_redirects=False) as response:
   if response.status_code!=400:_http_error(response.status_code,'PAT鉴权')
   data=response.json()
   if response.status_code!=400 or not isinstance(data,dict) or type(data.get('code')) is not int or data['code']!=400 or not isinstance(data.get('message'),str) or 'message' not in data['message'] or '不能为空' not in data['message']:raise ValueError()
 except _TygptError:raise
 except requests.Timeout:raise _TygptError('TYGPT PAT鉴权超时，未自动重试') from None
 except (requests.RequestException,ValueError,TypeError):raise ValueError('TYGPT PAT鉴权未通过，请核对本人的PAT、能力开放权限及网络；未自动重试') from None


def save_key(value):
 if not isinstance(value,str) or not value.strip() or len(value)>4096 or any(c in value for c in '\r\n\0'):raise ValueError('请填写本人的有效TYGPT PAT')
 value=value.strip();validate_pat(value);models=gateway_models(value)
 if not models:raise ValueError('TYGPT未返回可用模型，凭据未保存')
 encrypted=protect(value)
 with _lock:
  CONFIG.parent.mkdir(parents=True,exist_ok=True);tmp=CONFIG.with_suffix('.tmp')
  try:tmp.write_text(json.dumps({'baseUrl':BASE,'keyEncrypted':encrypted}),encoding='utf8');os.replace(tmp,CONFIG)
  finally:
   if tmp.exists():tmp.unlink()
 return {'ready':True,'models':models,'provider':'tygpt','model':_default_model(models)}


def status(provider):
 if provider=='tygpt':
  if not CONFIG.exists():return {'ready':False,'models':[],'model':'','provider':'tygpt','message':'请配置本人的TYGPT PAT'}
  key=gateway_key();validate_pat(key);models=gateway_models(key)
  return {'ready':bool(models),'models':models,'model':_default_model(models), 'provider':'tygpt'}
 if provider!='codex':raise ValueError('模型来源无效')
 from codex_client import CLIENT
 account=CLIENT.account()
 return {**account,'models':CLIENT.models() if account['ready'] else [],'model':CLIENT.model() if account['ready'] else '', 'provider':'codex'}


def _reply_text(data):
 if not isinstance(data,dict) or not isinstance(data.get('content'),str) or not data['content'].strip():raise ValueError('TYGPT未返回有效content同步回复')
 return data['content']


def tygpt_analyze(prompt,images,schema,model,cancelled,on_status,on_text=None):
 if cancelled():raise InterruptedError('已停止对话')
 key=gateway_key();models=gateway_models(key)
 selected=next((m for m in models if m['id']==model),None)
 if not selected:raise ValueError('请选择TYGPT返回的可用模型')
 if images and selected.get('capabilities',{}).get('image') is False:raise ValueError('所选TYGPT模型不支持图片，请选择目录中支持图片的模型')
 files=[]
 for file in images:
  try:
   path=Path(file).resolve(strict=True)
   if not path.is_file() or path.stat().st_size>25000000:raise ValueError()
   mime=mimetypes.guess_type(path.name)[0]
   if mime not in ('image/png','image/jpeg','image/webp'):raise ValueError()
   files.append({'file_name':path.name,'file_type':mime,'file_base64':base64.b64encode(path.read_bytes()).decode('ascii')})
  except (OSError,ValueError,TypeError):raise ValueError('TYGPT参考图片不可读取或格式尺寸无效') from None
 body={'message':prompt+'\n返回JSON结构：'+json.dumps(schema,ensure_ascii=False),'sender_id':str(uuid.uuid4()),'model':model,'files':files,'max_retries':0,'stream':False}
 effort=_reasoning_effort(selected)
 if effort is not None:body['reasoning_effort']=effort
 if cancelled():raise InterruptedError('已停止对话')
 on_status('TYGPT正在理解画面与要求…')
 try:
  with requests.post(BASE+'/agent/chat',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json=body,timeout=(10,420),allow_redirects=False) as response:
   if response.status_code!=200:_http_error(response.status_code,'对话请求')
   data=response.json()
 except _TygptError:raise
 except requests.Timeout:raise _TygptError('TYGPT对话请求超时，服务可能已接收请求；未自动重试，工程未修改') from None
 except requests.RequestException:raise ValueError('TYGPT连接中断，未自动重试，工程未修改') from None
 except (ValueError,TypeError):raise ValueError('TYGPT请求或同步回复未完成，未自动重试') from None
 if cancelled():raise InterruptedError('已停止对话')
 text=_reply_text(data)
 if len(text)>32000:raise ValueError('TYGPT回复超过长度限制')
 if on_text:on_text(text)
 try:
  stripped=text.strip()
  if stripped.startswith('```') and stripped.endswith('```'):stripped=stripped.split('\n',1)[1].rsplit('```',1)[0].strip()
  result=json.loads(stripped)
 except (ValueError,IndexError):raise ValueError('TYGPT未返回有效JSON方案，请重新发起对话') from None
 if not isinstance(result,dict):raise ValueError('TYGPT方案格式无效')
 return result


def analyze(prompt,images,schema,provider,model,cancelled,on_status,on_text=None):
 if provider=='tygpt':return tygpt_analyze(prompt,images,schema,model,cancelled,on_status,on_text)
 if provider!='codex':raise ValueError('模型来源无效')
 from codex_client import CLIENT
 if model and model not in [m['id'] for m in CLIENT.models()]:raise ValueError('当前Codex账号没有提供所选模型')
 return CLIENT.analyze(prompt,images,schema,cancelled,on_status=on_status,**({'model_override':model} if model else {}),**({'on_text':on_text} if on_text else {}))
