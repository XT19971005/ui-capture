"""Disposable UI backend; private project store and no real model execution."""
if __name__ == '__main__':
 import sys
 from pathlib import Path
 folder=Path(sys.argv[1]).resolve();folder.mkdir(parents=True,exist_ok=True)
 import server,assistant_models,image_provider,codex_client
 from local_project_store import LocalProjectStore
 from werkzeug.serving import make_server
 server.PORT=19237;server.LOCAL_ORIGINS.add('http://127.0.0.1:19237');server.ALLOWED_ORIGINS|=server.LOCAL_ORIGINS
 server.DEFAULT_PROJECT_DIRECTORY=folder/'工程文件';server.PROJECT_LOCATION_CONFIG=folder/'directory.local.json';server.SAVED_PROJECTS=LocalProjectStore(server.DEFAULT_PROJECT_DIRECTORY);server.PROJECT_LOCATION_ERROR=None
 assistant_models.CONFIG=folder/'assistant.local.json';assistant_models.DRAMA_CONFIG=folder/'absent.json';image_provider.CONFIG=folder/'image.local.json';image_provider.DRAMA_CONFIG=folder/'absent.json'
 codex_client.CLIENT.account=lambda:{'ok':True,'ready':True};codex_client.CLIENT.models=lambda:[{'id':'test-sol','name':'自检模型','default':True}];codex_client.CLIENT.model=lambda:'test-sol'
 codex_client.CLIENT.login=lambda:{'url':'https://example.invalid/ui-self-test-login'}
 assistant_models.gateway_models=lambda key=None:[{'id':n,'name':n} for n in ['grok-4.6','gpt-6.1-sol']]
 assistant_models.read_config=lambda:{'baseUrl':assistant_models.BASE,'selectedModel':'grok-4.6','keyEncrypted':''}
 def blocked(*args,**kwargs):raise RuntimeError('自检环境禁止真实生成')
 codex_client.CLIENT.generate=blocked;codex_client.CLIENT.analyze=blocked;image_provider.request=blocked
 http=make_server('127.0.0.1',19237,server.app,threaded=True);print('UI_FIXTURE_READY',flush=True)
 try:http.serve_forever()
 except KeyboardInterrupt:pass
 finally:http.server_close()
