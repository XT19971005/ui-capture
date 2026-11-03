"""Assistant-only model selection. Image generation keeps the existing engine."""
import base64, json, time
from pathlib import Path
import requests
from runtime import STATE

BASE='https://taishi.tuyoo.com/v1'
VISIBLE_TAISHI_MODELS=('grok-4.6','gpt-6.1-sol')
# Set once from the isolated job's stdin. No host or cross-application credential discovery.
CONNECTION={}

def gateway_key():
 key=CONNECTION.get('key')
 if not key:raise ValueError('请在模型设置中配置本人的太石 Key')
 return key

def gateway_models(key=None):
 try:
  with requests.get(BASE+'/models',headers={'Authorization':'Bearer '+(key or gateway_key())},timeout=(10,20),allow_redirects=False) as response:
   if response.status_code!=200:raise ValueError('太石模型目录不可用（HTTP '+str(response.status_code)+'）')
   data=response.json()
 except requests.RequestException:raise ValueError('太石模型目录连接未完成，请稍后检查') from None
 if not isinstance(data,dict) or not isinstance(data.get('data'),list):raise ValueError('太石模型目录格式无效')
 ids=list(dict.fromkeys(m['id'] for m in data['data'] if isinstance(m,dict) and isinstance(m.get('id'),str) and 0<len(m['id'])<=200))
 return [{'id':i,'name':i} for i in VISIBLE_TAISHI_MODELS if i in ids]

def gateway_analyze(prompt,images,schema,model,cancelled,on_status,on_text=None):
 if cancelled():raise InterruptedError('已停止对话')
 key=gateway_key();models=gateway_models(key)
 if not model or not any(m['id']==model for m in models):raise ValueError('请选择太石返回的可用模型')
 content=[{'type':'input_text','text':prompt+'\n返回JSON结构：'+json.dumps(schema,ensure_ascii=False)}]
 for file in images:content.append({'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(Path(file).read_bytes()).decode('ascii')})
 if cancelled():raise InterruptedError('已停止对话')
 on_status('太石正在理解画面与要求…');text='';complete=False;started=time.monotonic()
 try:
  with requests.post(BASE+'/responses',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'text/event-stream'},json={'model':model,'input':[{'role':'user','content':content}],'stream':True,'store':False,'text':{'format':{'type':'json_object'}}},stream=True,timeout=(10,30),allow_redirects=False) as response:
   if response.status_code!=200:raise ValueError('太石未接受本次请求（HTTP '+str(response.status_code)+'），请检查所选模型与额度')
   if 'text/event-stream' not in response.headers.get('Content-Type',''):raise ValueError('太石未返回预期回复流')
   data=[]
   def event():
    nonlocal text,complete
    if not data:return
    raw='\n'.join(data);data.clear()
    if raw=='[DONE]':return
    value=json.loads(raw);kind=value.get('type')
    if kind=='response.output_text.delta':text+=value.get('delta','')
    if kind=='response.output_text.done' and not text:text=value.get('text','')
    if kind=='response.completed':
     output='\n'.join(p['text'] for i in value.get('response',{}).get('output',[]) if i.get('type')=='message' for p in i.get('content',[]) if p.get('type')=='output_text')
     if output:text=output
     complete=True
    if kind in ('error','response.failed','response.incomplete'):raise ValueError('太石未完整完成回复，请检查模型能力和额度')
    if on_text and text:on_text(text)
   for line in response.iter_lines(decode_unicode=False):
    if cancelled():raise InterruptedError('已停止对话')
    if time.monotonic()-started>420:raise ValueError('太石回复超时，未自动重试')
    if isinstance(line,bytes):line=line.decode('utf8')
    if line.startswith('data:'):data.append(line[5:].lstrip())
    elif not line.strip():event()
    if len(text)>32000 or sum(map(len,data))>64000:raise ValueError('太石回复超过长度限制')
    if complete:break
   event()
 except requests.RequestException:raise ValueError('太石连接中断，未自动重试，工程未修改') from None
 if not complete or not text.strip():raise ValueError('太石回复未完整结束，未自动重试')
 return json.loads(text)

def analyze(prompt,images,schema,provider,model,cancelled,on_status,on_text=None):
 if provider=='taishi':return gateway_analyze(prompt,images,schema,model,cancelled,on_status,on_text)
 from codex_client import CLIENT
 # Freeze the request's model without changing the user's persistent Codex default.
 if not CLIENT.company and model and model not in [m['id'] for m in CLIENT.models()]:raise ValueError('当前Codex账号没有提供所选模型')
 return CLIENT.analyze(prompt,images,schema,cancelled,on_status=on_status,**({'model_override':model} if model else {}),**({'on_text':on_text} if on_text else {}))
