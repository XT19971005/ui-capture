import json,tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase,Client,override_settings
from django.contrib.auth.models import Group
from django.utils import timezone
from shijie.accounts.models import User
from shijie.pipeline.models import DesktopService,Job
from shijie.pipeline.storage import job_root,read_scene
from tests.test_service import png
class SharedRoutingAPI(TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.override=override_settings(DATA_ROOT=Path(self.tmp.name),MIN_FREE=1,LAN_SHARED=False);self.override.enable();self.addCleanup(self.override.disable)
  self.a=User.objects.create_user(username='audit-a',email='audit-a@example.test');self.b=User.objects.create_user(username='audit-b',email='audit-b@example.test')
  group=Group.objects.get_or_create(name='使用者')[0]
  for user in (self.a,self.b):user.groups.add(group)
  self.client.force_login(self.a);self.other=Client();self.other.force_login(self.b)
  self.service=DesktopService.objects.create(pk=1,enabled=True,token_digest='test-only',heartbeat=timezone.now(),capabilities={'ready':True,'models':[{'id':'gpt-6.1-sol'}],'model':'gpt-6.1-sol','imageGeneration':True,'analysisProvider':'tygpt','imageProvider':'aimake','imageModel':'gpt-image-2'})
 def plan(self):return {'image':png(),'scene':{'width':4,'height':3,'nodes':[]},'selectedIds':[],'messages':[{'role':'user','content':'仅分析'}],'provider':'tygpt','model':'gpt-6.1-sol'}
 def test_settings_report_real_shared_providers(self):
  state=self.client.get('/api/engine/assistant/models?provider=tygpt').json();self.assertEqual(state['provider'],'tygpt')
  state=self.client.get('/api/engine/image-provider').json();self.assertEqual(state['provider'],'aimake')
 def test_auto_analysis_follows_enabled_company_without_codex_login(self):
  import sys,types
  self.service.enabled=False;self.service.save()
  ai=types.ModuleType('shijie.pipeline.ai');ai.selected_provider=lambda user:'company'
  def forbidden(*args,**kwargs):raise AssertionError('company analysis must not check Codex login')
  ai.status=ai.pending_login=ai.account_busy=forbidden
  value={**self.plan(),'provider':'auto'}
  with patch.dict(sys.modules,{'shijie.pipeline.ai':ai}),patch('shijie.pipeline.company.credentials',return_value={'key':'test-only'}):
   response=self.client.post('/api/engine/assistant/jobs',value,content_type='application/json')
  self.assertEqual(response.status_code,202,response.content)
  job=Job.objects.get(pk=response.json()['id']);snapshot=json.loads((job_root(job)/'connection.json').read_text())
  self.assertEqual(snapshot['analysisProvider'],'company');self.assertFalse(snapshot['needsCodex'])
 def test_public_editor_serves_annotation_order_module_before_assistant(self):
  response=self.client.get('/image-editor.html');self.assertEqual(response.status_code,200)
  html=response.content.decode();self.assertIn('annotation-order.js',html)
  self.assertLess(html.index('annotation-order.js'),html.index('free-assistant.js'))
  module=self.client.get('/annotation-order.js');self.assertEqual(module.status_code,200)
  self.assertIn(b'ShijieAnnotationOrder',module.content)
 def test_task_keeps_provider_and_never_checks_personal_codex(self):
  response=self.client.post('/api/engine/assistant/jobs',self.plan(),content_type='application/json')
  self.assertEqual(response.status_code,202,response.content);job=Job.objects.get(pk=response.json()['id'])
  snapshot=json.loads((job_root(job)/'connection.json').read_text());self.assertEqual(snapshot['analysisProvider'],'tygpt');self.assertEqual(snapshot['imageProvider'],'aimake');self.assertFalse(snapshot['needsCodex'])
  self.assertEqual(read_scene(job_root(job)/'input.json')['provider'],'tygpt');self.assertEqual(self.other.get('/api/engine/jobs/'+str(job.pk)).status_code,404)
 def test_codex_capability_does_not_block_external_image_channel(self):
  value={'image':png(),'width':4,'height':3,'title':'audit','projectId':'audit','layers':[{'name':'主体','instruction':'完整主体','box':{'x':0,'y':0,'width':4,'height':3}}]}
  response=self.client.post('/api/engine/assistant/split',value,content_type='application/json');self.assertEqual(response.status_code,202,response.content)
 def test_no_task_is_created_while_worker_offline(self):
  self.service.heartbeat=None;self.service.save()
  response=self.client.post('/api/engine/assistant/jobs',self.plan(),content_type='application/json');self.assertEqual(response.status_code,503);self.assertFalse(Job.objects.exists())
 def test_public_server_uses_saved_tygpt_and_aimake_without_desktop(self):
  import sys,types
  from shijie.pipeline import providers
  from shijie.pipeline.storage import write_json
  self.service.enabled=False;self.service.save()
  write_json(providers.path(self.a),{'tygpt':{'key':providers.cipher(self.a).encrypt(b'test-pat').decode()},'aimake':{'provider':'aimake','model':'gpt-image-2','key':providers.cipher(self.a).encrypt(b'test-image-key').decode()}})
  ai=types.ModuleType('shijie.pipeline.ai');ai.selected_provider=lambda user:'codex'
  def forbidden(*args,**kwargs):raise AssertionError('TYGPT/aimake must not check personal Codex')
  ai.status=forbidden
  with patch.dict(sys.modules,{'shijie.pipeline.ai':ai}),patch('tygpt_transport.validate_pat'),patch('tygpt_transport.gateway_models',return_value=[{'id':'gpt-6.1-sol'}]):
   response=self.client.post('/api/engine/assistant/jobs',self.plan(),content_type='application/json')
  self.assertEqual(response.status_code,202,response.content);job=Job.objects.get(pk=response.json()['id']);self.assertEqual(job.executor,'server')
  snapshot=json.loads((job_root(job)/'connection.json').read_text());self.assertEqual(snapshot['analysisProvider'],'tygpt');self.assertEqual(snapshot['imageProvider'],'aimake');self.assertFalse(snapshot['needsCodex'])
  credentials=providers.job_credentials(self.a,snapshot);self.assertEqual(credentials['analysisProvider'],'tygpt');self.assertEqual(credentials['image']['provider'],'aimake');self.assertFalse(credentials['needsCodex'])
  self.assertEqual(self.other.get('/api/engine/jobs/'+str(job.pk)).status_code,404)
