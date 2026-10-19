import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server
from test_local_project_store import record
from local_project_store import LocalProjectStore
from image_wire import decode_job

class LocalProjectRoutesTests(unittest.TestCase):
 def setUp(self):
  self.client=server.app.test_client();self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.store=LocalProjectStore(Path(self.temp.name)/'工程库');p=patch.object(server,'SAVED_PROJECTS',self.store,create=True);p.start();self.addCleanup(p.stop)
  config_patch=patch.object(server,'PROJECT_LOCATION_CONFIG',Path(self.temp.name)/'library.local.json',create=True);config_patch.start();self.addCleanup(config_patch.stop)
  self.headers={'X-Shijie-Token':server.TOKEN,'Origin':'http://127.0.0.1:19217'}
 def req(self,method,path,**kw):return self.client.open(path,method=method,base_url='http://127.0.0.1:19217',**kw)
 def test_requires_token_and_local_origin_even_for_suffixes(self):
  for path in ('/saved-projects','/saved-projects/one','/saved-projects/one.js'):
   self.assertEqual(self.req('GET',path).status_code,401)
  headers={**self.headers,'Origin':'https://evil.test'}
  self.assertEqual(self.req('PUT','/saved-projects/one',headers=headers,json=record()).status_code,403)
 def test_explicit_save_lazy_list_get_conflict_delete(self):
  result=self.req('PUT','/saved-projects/one',headers=self.headers,json=record());self.assertEqual(result.status_code,200,result.json)
  meta=result.json['project'];self.assertNotIn('doc',meta)
  self.assertNotIn('doc',self.req('GET','/saved-projects',headers=self.headers).json['projects'][0])
  read=self.req('GET','/saved-projects/one',headers=self.headers);self.assertEqual(decode_job(read.json['project'])['doc'],record()['doc'])
  self.assertEqual(self.req('PUT','/saved-projects/one',headers=self.headers,json=record()).status_code,409)
  self.assertEqual(self.req('DELETE','/saved-projects/one',headers=self.headers,json={'_expectedVersion':meta['persistedVersion']}).status_code,200)
  self.assertEqual(self.req('GET','/saved-projects/one',headers=self.headers).status_code,404)
 def test_write_failure_never_returns_success(self):
  with patch.object(self.store,'save',side_effect=OSError('disk full')),self.assertLogs(level='ERROR'):
   response=self.req('PUT','/saved-projects/one',headers=self.headers,json=record())
  self.assertEqual(response.status_code,507);self.assertEqual(self.store.list(),[])
 def test_truncated_compressed_project_returns_clear_json_error(self):
  self.store.save('one',record(),None);path=self.store.path('one');original=path.read_bytes();path.write_bytes(original[:-6])
  response=self.req('GET','/saved-projects/one',headers=self.headers)
  self.assertEqual(response.status_code,400);self.assertIsInstance(response.json['error'],str);self.assertIn('损坏',response.json['error'])

 def test_archive_route_is_local_authenticated_and_keeps_exact_record(self):
  self.assertEqual(self.req('POST','/saved-projects/archive-browser',json=record()).status_code,401)
  self.store.save('one',record(),None)
  response=self.req('POST','/saved-projects/archive-browser',headers=self.headers,json=record())
  self.assertEqual(response.status_code,200,response.json);self.assertTrue(response.json['verified'])
  archive=LocalProjectStore(self.store.root/'旧版浏览器备份');meta=archive.list()[0]
  self.assertEqual(archive.get(meta['id'])['legacyOriginal'],record())
 def test_archive_route_failure_cannot_claim_verification(self):
  with patch.object(self.store,'archive_browser',side_effect=OSError('full')):
   response=self.req('POST','/saved-projects/archive-browser',headers=self.headers,json=record())
  self.assertEqual(response.status_code,507);self.assertNotIn('verified',response.json)

 def test_connect_directory_lists_files_without_import_and_routes_future_manual_saves(self):
  folder=Path(self.temp.name)/'选择的本地目录';folder.mkdir();other=LocalProjectStore(folder);other.save('one',record(),None)
  response=self.req('PUT','/saved-projects/settings/location',headers=self.headers,json={'directory':str(folder)})
  self.assertEqual(response.status_code,200,response.json)
  self.assertEqual(Path(response.json['directory']),folder.resolve())
  rows=self.req('GET','/saved-projects',headers=self.headers).json
  self.assertEqual(rows['projects'][0]['title'],'中文工程');self.assertEqual(Path(rows['directory']),folder.resolve())
  value=record();value['id']=value['doc']['_projectId']='two'
  self.assertEqual(self.req('PUT','/saved-projects/two',headers=self.headers,json=value).status_code,200)
  self.assertEqual(len(other.list()),2);self.assertEqual(self.store.list(),[])
 def test_invalid_or_unwritable_directory_never_replaces_current_library(self):
  for directory in ('relative/path',str(Path(self.temp.name)/'missing')):
   response=self.req('PUT','/saved-projects/settings/location',headers=self.headers,json={'directory':directory})
   self.assertEqual(response.status_code,400)
   self.assertIs(server.SAVED_PROJECTS,self.store)
  folder=Path(self.temp.name)/'valid';folder.mkdir()
  with patch.object(server,'persist_project_location',side_effect=OSError('full')):
   response=self.req('PUT','/saved-projects/settings/location',headers=self.headers,json={'directory':str(folder)})
  self.assertEqual(response.status_code,507);self.assertIs(server.SAVED_PROJECTS,self.store)

 def test_list_rows_and_directory_use_same_store_during_concurrent_switch(self):
  self.store.save('one',record(),None);other=LocalProjectStore(Path(self.temp.name)/'other');real_list=self.store.list
  def switch():
   server.SAVED_PROJECTS=other
   return real_list()
  with patch.object(self.store,'list',side_effect=switch):
   response=self.req('GET','/saved-projects',headers=self.headers)
  self.assertEqual(Path(response.json['directory']),self.store.root.resolve());self.assertEqual(response.json['projects'][0]['id'],'one')
 def test_wrong_directory_cannot_read_save_or_delete_even_same_version(self):
  meta=self.store.save('one',record(),None);wrong=str(Path(self.temp.name)/'other')
  value=record();value['_expectedVersion']=meta['persistedVersion'];value['_expectedDirectory']=wrong
  for method in ('PUT','DELETE'):
   response=self.req(method,'/saved-projects/one',headers=self.headers,json=value);self.assertEqual(response.status_code,409)
  self.assertEqual(self.req('GET','/saved-projects/one',headers=self.headers,query_string={'directory':wrong}).status_code,409)
  self.assertEqual(self.store.get('one')['doc'],record()['doc'])

 def test_registered_native_extension_can_use_disk_library_but_unknown_origin_cannot(self):
  extension=next(origin for origin in server.ALLOWED_ORIGINS if origin not in server.LOCAL_ORIGINS)
  headers={**self.headers,'Origin':extension,'Sec-Fetch-Site':'cross-site'}
  self.assertEqual(self.req('GET','/saved-projects/settings/location',headers=headers).status_code,200)
  response=self.req('PUT','/saved-projects/one',headers=headers,json=record());self.assertEqual(response.status_code,200,response.json)
  self.assertEqual(self.req('GET','/saved-projects',headers=headers).json['projects'][0]['title'],'中文工程')
  headers['Origin']='chrome-extension://unregistered'
  self.assertEqual(self.req('GET','/saved-projects',headers=headers).status_code,403)

if __name__=='__main__':unittest.main()

