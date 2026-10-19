import copy, importlib.util, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

IMAGE='data:image/png;base64,'+'QUJD'*4096
def record():
 return {'id':'one','kind':'image','title':'中文工程','revision':'rev1','saveMode':'saved','doc':{'_projectId':'one','format':'shijie-scene','version':2,'source':IMAGE,'nodes':[{'src':IMAGE}],'_splitBaseline':{'scene':{'source':IMAGE}}}}

class LocalProjectStoreTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(importlib.util.find_spec('local_project_store'),'local disk project storage must exist')
  import local_project_store
  self.module=local_project_store;self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=local_project_store.LocalProjectStore(Path(self.temp.name)/'工程库')
 def test_roundtrip_deduplicates_and_preserves_baseline(self):
  original=record();meta=self.store.save('one',original,None)
  self.assertEqual(self.store.get('one')['doc'],original['doc']);self.assertEqual(meta['source'],'local-disk');self.assertNotIn('doc',meta)
  files=list((Path(self.temp.name)/'工程库').iterdir());self.assertEqual(len(files),1);self.assertLess(files[0].stat().st_size,len(IMAGE))
 def test_list_reads_metadata_even_if_body_is_unavailable(self):
  self.store.save('one',record(),None)
  with patch.object(self.module.gzip,'GzipFile',side_effect=AssertionError('list must not inflate scenes')):
   rows=self.store.list();self.assertEqual(rows[0]['title'],'中文工程');self.assertNotIn('doc',rows[0])
 def test_failed_replace_retains_previous_and_cleans_temporary_file(self):
  old=self.store.save('one',record(),None);new=record();new['doc']['source']='changed';new['revision']='rev2'
  with patch.object(self.module.os,'replace',side_effect=OSError('disk full')):
   with self.assertRaises(OSError):self.store.save('one',new,old['persistedVersion'])
  self.assertEqual(self.store.get('one')['doc']['source'],IMAGE);self.assertEqual(len(list((Path(self.temp.name)/'工程库').iterdir())),1)
 def test_stale_save_and_delete_cannot_overwrite_newer_project(self):
  old=self.store.save('one',record(),None);new=record();new['revision']='rev2';self.store.save('one',new,old['persistedVersion'])
  with self.assertRaises(self.module.ProjectConflict):self.store.save('one',record(),old['persistedVersion'])
  with self.assertRaises(self.module.ProjectConflict):self.store.delete('one',old['persistedVersion'])
  self.assertEqual(self.store.get('one')['revision'],'rev2')
 def test_invalid_id_and_oversize_leave_disk_unchanged(self):
  for ident in ('../escape','a/b','', 'x'*161):
   with self.assertRaises(ValueError):self.store.save(ident,record(),None)
  import image_wire
  with patch.object(image_wire,'MAX_UNIQUE_IMAGE_BYTES',100):
   with self.assertRaises(ValueError):self.store.save('one',record(),None)
  self.assertFalse((Path(self.temp.name)/'工程库').exists())
 def test_reserved_image_reference_cannot_create_unreadable_saved_file(self):
  value=record();value['doc']['custom']={'$image':0}
  with self.assertRaises(ValueError):self.store.save('one',value,None)
  self.assertEqual(self.store.list(),[])
 def test_get_and_list_do_not_create_storage_and_missing_delete_is_safe(self):
  self.assertEqual(self.store.list(),[])
  with self.assertRaises(FileNotFoundError):self.store.get('one')
  self.store.delete('one',None);self.assertFalse((Path(self.temp.name)/'工程库').exists())
 def test_too_many_unique_images_cannot_replace_saved_project(self):
  meta=self.store.save('one',record(),None);value=record()
  value['doc']['nodes']=[{'src':'data:image/png;base64,'+str(i)} for i in range(4097)]
  with self.assertRaises(ValueError):self.store.save('one',value,meta['persistedVersion'])
  self.assertEqual(self.store.get('one')['doc'],record()['doc'])
 def test_missing_or_empty_header_version_cannot_be_overwritten_as_new_project(self):
  for version in (None,'',17):
   with self.subTest(version=version):
    path=self.store.path('one');self.store.root.mkdir(exist_ok=True)
    header={'id':'one','storageVersion':'local-disk-v1','updated':1,'title':'saved'}
    if version is not None:header['persistedVersion']=version
    content=json.dumps(header).encode()+b'\nretained damaged body';path.write_bytes(content)
    with self.assertRaises(ValueError):self.store.save('one',record(),None)
    self.assertEqual(path.read_bytes(),content)

 def test_saved_filename_uses_chinese_title_and_same_title_projects_remain_distinct(self):
  self.store.save('one',record(),None)
  self.assertEqual(self.store.path('one').name,'中文工程.shijie-project')
  second=record();second['id']='two';second['doc']['_projectId']='two'
  self.store.save('two',second,None)
  self.assertEqual(self.store.path('two').name,'中文工程（2）.shijie-project')
  self.assertEqual({p['id'] for p in self.store.list()},{'one','two'})
  self.assertEqual(self.store.get('one')['doc'],record()['doc'])

 def test_legacy_hash_filename_is_readable_then_explicit_save_renames_without_changing_id(self):
  import hashlib
  meta=self.store.save('one',record(),None)
  legacy=self.store.root/(hashlib.sha256(b'one').hexdigest()+'.shijie-project')
  self.store.path('one').rename(legacy)
  self.assertEqual(self.store.get('one')['doc'],record()['doc'])
  self.assertEqual(self.store.list()[0]['id'],'one')
  new=record();new['title']=new['doc']['title']='万圣节赛车海报'
  self.store.save('one',new,meta['persistedVersion'])
  self.assertFalse(legacy.exists())
  self.assertEqual(self.store.path('one').name,'万圣节赛车海报.shijie-project')
  self.assertEqual(len(list(self.store.root.iterdir())),1)

 def test_rename_failure_after_moving_old_file_keeps_old_contents_and_version(self):
  meta=self.store.save('one',record(),None);new=record();new['title']='新中文名称';new['doc']['source']='changed'
  real_replace=self.module.os.replace;calls=[]
  def replace(source,target):
   calls.append((source,target))
   if len(calls)==2:raise OSError('disk full after rename')
   return real_replace(source,target)
  with patch.object(self.module.os,'replace',side_effect=replace):
   with self.assertRaises(OSError):self.store.save('one',new,meta['persistedVersion'])
  self.assertEqual(self.store.get('one')['doc'],record()['doc'])
  self.assertEqual(self.store.list()[0]['persistedVersion'],meta['persistedVersion'])
  self.assertEqual(len(list(self.store.root.iterdir())),1)

 def test_title_cannot_escape_storage_or_replace_another_project(self):
  first=self.store.save('one',record(),None);new=record();new['title']='../../中文工程<>:\\坏名?*\n '
  self.store.save('one',new,first['persistedVersion'])
  saved=self.store.path('one')
  self.assertEqual(saved.resolve().parent,self.store.root.resolve())
  self.assertIn('中文工程',saved.name)
  self.assertFalse(any(c in saved.name for c in '<>:"/\\|?*\n'))

 def test_reserved_device_title_is_safe(self):
  value=record();value['title']='CON.txt'
  self.assertTrue(self.store._destination('CON.txt',self.store._legacy_path('one')).name.startswith('工程_'))
  self.store.save('one',value,None)
  self.assertEqual(self.store.get('one')['title'],'CON.txt')

 def test_archive_keeps_exact_legacy_record_and_is_idempotent(self):
  self.store.save('one',record(),None);old=record();old['saveMode']='auto';old['doc'].pop('_projectId');old['title']='old numeric 123'
  result=self.store.archive_browser(old);self.assertTrue(result['verified'])
  archive=self.module.LocalProjectStore(self.store.root/'旧版浏览器备份');rows=archive.list()
  self.assertEqual(archive.get(rows[0]['id'])['legacyOriginal'],old)
  self.store.archive_browser(old);self.assertEqual(len(archive.list()),1)
  self.assertEqual(len(self.store.list()),1)

 def test_archive_requires_readable_main_project(self):
  with self.assertRaises(FileNotFoundError):self.store.archive_browser(record())
  self.assertFalse((self.store.root/'旧版浏览器备份').exists())

 def test_reconnected_directory_reuses_cas_lock(self):
  other=self.module.LocalProjectStore(self.store.root/'..'/self.store.root.name)
  self.assertIs(self.store.lock,other.lock)
  meta=self.store.save('one',record(),None)
  other.save('one',record(),meta['persistedVersion'])
  with self.assertRaises(self.module.ProjectConflict):self.store.save('one',record(),meta['persistedVersion'])

 def test_thumbnail_is_in_lightweight_index_and_does_not_change_doc(self):
  import base64,io
  from PIL import Image
  buffer=io.BytesIO();Image.new('RGB',(32,20),'red').save(buffer,format='WEBP')
  value=record();value['thumbnail']='data:image/webp;base64,'+base64.b64encode(buffer.getvalue()).decode()
  meta=self.store.save('one',value,None)
  with patch.object(self.module.gzip,'GzipFile',side_effect=AssertionError('cover list must not inflate document')):
   self.assertEqual(self.store.list()[0]['thumbnail'],value['thumbnail'])
  self.assertEqual(meta['thumbnailRevision'],meta['revision']);self.assertEqual(self.store.get('one')['doc'],record()['doc'])
  changed=record();changed['revision']='second';self.store.save('one',changed,meta['persistedVersion'])
  self.assertNotIn('thumbnail',self.store.list()[0])
 def test_invalid_or_huge_thumbnail_does_not_overwrite_project(self):
  meta=self.store.save('one',record(),None)
  for thumbnail in ('https://example.test/a.png','data:image/svg+xml;base64,AAAA','data:image/webp;base64,'+'A'*65000):
   value=record();value['thumbnail']=thumbnail
   with self.assertRaises(ValueError):self.store.save('one',value,meta['persistedVersion'])
  self.assertEqual(self.store.get('one')['doc'],record()['doc'])

if __name__=='__main__':unittest.main()
