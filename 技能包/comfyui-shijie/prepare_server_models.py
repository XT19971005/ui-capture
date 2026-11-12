"""Configure the platform's checked model list; all weight downloads stay on server.
Uses only Python stdlib and the user's existing TYCOMFY_AUTHORIZATION environment value.
Never writes or prints credentials. No local weights or inference dependencies are installed.
"""
import argparse,json,os,re,urllib.request,urllib.parse
from urllib.error import HTTPError
from pathlib import Path
BASE='http://47.117.156.236:8000/tycomfyui/api/v1/'
FILES=('model.safetensors','config.json','generation_config.json','preprocessor_config.json','tokenizer.json','tokenizer_config.json','chat_template.json','merges.txt','vocab.json','video_preprocessor_config.json')
PREFIX='shijie/Qwen3-VL-2B-Instruct/'

def merge_dependencies(existing, additions):
 keys={(str(row['node_id']),row['input']) for row in additions}
 return [dict(row) for row in existing if (str(row['node_id']),row['input']) not in keys]+[dict(row) for row in additions]

class SameHost(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if urllib.parse.urlparse(newurl).netloc!=urllib.parse.urlparse(BASE).netloc:raise RuntimeError('Refusing cross-host credential redirect')
  return super().redirect_request(req,fp,code,msg,headers,newurl)

class Platform:
 def __init__(self):
  self.authorization=os.environ.get('TYCOMFY_AUTHORIZATION','').strip()
  if not self.authorization:raise RuntimeError('需要平台当前登录凭证放入TYCOMFY_AUTHORIZATION环境变量；不落盘、不打印')
  if not self.authorization.startswith('Bearer '):self.authorization='Bearer '+self.authorization
  self.opener=urllib.request.build_opener(SameHost())
  self.schema=self.request('GET',BASE+'openapi.json')
 def request(self,method,url,payload=None):
  if urllib.parse.urlparse(url).netloc!=urllib.parse.urlparse(BASE).netloc:raise RuntimeError('API credentials restricted to the original server')
  body=json.dumps(payload,ensure_ascii=False).encode('utf8') if payload is not None else None
  req=urllib.request.Request(url,data=body,method=method,headers={'Authorization':self.authorization,'Content-Type':'application/json'})
  try:
   with self.opener.open(req,timeout=120) as response:return json.load(response)
  except HTTPError as error:raise RuntimeError(str(error.code)+': '+error.read().decode('utf8')[:3000]) from None
 def call(self,operation,params=None,body=None):
  params=params or {}
  for path,methods in self.schema['paths'].items():
   for method,definition in methods.items():
    if not isinstance(definition,dict) or definition.get('operationId')!=operation:continue
    route=path
    for key in re.findall(r'{([^}]+)}',route):route=route.replace('{'+key+'}',urllib.parse.quote(str(params[key]),safe=''))
    if route.startswith('/api/v1/'):url=BASE+route[len('/api/v1/'):]
    elif route.startswith('/tycomfyui/'):url=urllib.parse.urljoin(BASE,route)
    else:url=BASE+route.lstrip('/')
    return self.request(method.upper(),url,body)
  raise RuntimeError('平台未公开所需操作：'+operation)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--workflow-id',required=True);parser.add_argument('--apply',action='store_true');parser.add_argument('--prepare',action='store_true');args=parser.parse_args()
 client=Platform();response=client.call('getWorkflow',{'workflow_id':args.workflow_id});workflow=response.get('workflow',response)
 graph=workflow['api_graph'];ui=workflow['ui_graph'];experts=[(i,n) for i,n in graph.items() if n.get('class_type')=='ShijieVisualExpert']
 if len(experts)!=1:raise RuntimeError('此配置工具需要且仅需要一个本地视觉专家节点')
 expert_id,node=experts[0];dependencies=[]
 manifest=json.loads((Path(__file__).resolve().parent/'expert/model_manifest.json').read_text(encoding='utf8'))
 for i,file in enumerate(f for f in manifest['files'] if f['name']=='model.safetensors'):
  name=file['name'];filename=PREFIX+name;input_name=f'model_file_{i}'
  node['inputs'][input_name]=filename
  dependencies.append({'node_id':str(expert_id),'input':input_name,'category':'text_encoders','filename':filename,'url':file['url'],'sha256':file['sha256'],'size_bytes':file['size_bytes']})
 node['inputs']['download_source']='仅使用本地'
 for n in ui.get('nodes',[]):
  if str(n.get('id'))==str(expert_id):
   n['widgets_values']=(n.get('widgets_values',[])[:3]+[PREFIX+'model.safetensors']);n['widgets_values'][0]='仅使用本地'
   existing={a['name'] for a in n.get('inputs',[])}
   for i in range(1):
    key=f'model_file_{i}'
    if key not in existing:n.setdefault('inputs',[]).append({'name':key,'type':'STRING','link':None,'widget':{'name':key}})
 payload={'revision':workflow['revision'],'api_graph':graph,'ui_graph':ui,'model_dependencies':merge_dependencies(workflow.get('model_dependencies',[]),dependencies)}
 # Inspectable source list is safe; credentials are never part of the payload.
 output=Path(__file__).resolve().parent/'docs'/'服务器专家模型依赖清单.json';output.write_text(json.dumps({'workflow_id':args.workflow_id,**payload},ensure_ascii=False,indent=2),encoding='utf8')
 if not args.apply:print('已使用官方发布者摘要；清单已生成，尚未更新工作流或下载模型。');return
 client.call('updateWorkflow',{'workflow_id':args.workflow_id},payload)
 current=client.call('getWorkflow',{'workflow_id':args.workflow_id});current=current.get('workflow',current)
 preparation=client.call('prepareWorkflowModels',{'workflow_id':args.workflow_id},body={'revision':current['revision']}) if args.prepare else '已配置；可点击画布底部下载需要的模型'
 print(json.dumps({'workflow_id':args.workflow_id,'revision':current['revision'],'model_files':len(dependencies),'preparation':preparation},ensure_ascii=False))
if __name__=='__main__':main()
