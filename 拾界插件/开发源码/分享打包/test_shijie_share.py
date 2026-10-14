import importlib.util, tempfile, unittest, zipfile
from pathlib import Path
SCRIPT = Path(__file__).with_name('build_shijie_share.py')
class ShareTests(unittest.TestCase):
 def setUp(self):
  self.assertTrue(SCRIPT.is_file(), '分享打包工具尚未实现')
  spec=importlib.util.spec_from_file_location('share',SCRIPT); self.share=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.share)
 def test_relocated_package_excludes_credentials_models_and_projects(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'任意 路径'; root.mkdir()
   wanted=['拾界插件/启动拾界.ps1','拾界插件/开发源码/自动拆图/server.py','拾界插件/插件程序/edge/icon.png','拾界插件/依赖/运行环境/python/python.exe','拾界插件/依赖/运行环境/python/python310._pth','技能包/同步到Codex.ps1','技能包/维护约定.md','技能包/game-ui-to-psd/SKILL.md','技能包/依赖/Node/node_modules/ag-psd/index.js']
   banned=['拾界插件/项目/a.psd','拾界插件/自检记录/a.png','拾界插件/插件程序/示例/a.json','拾界插件/插件程序/edge/vendor/ocr/lang/chi_sim.traineddata','拾界插件/开发源码/构建PSD.cjs','拾界插件/开发源码/自动拆图/diagnose_font.cjs','拾界插件/开发源码/自动拆图/native-host.json','拾界插件/开发源码/自动拆图/native-host.cmd','拾界插件/依赖/运行环境/python/site-packages/torch/a.py','拾界插件/依赖/自动拆图/models/a.safetensors','技能包/game-ui-to-psd/runtime.local.json','技能包/game-ui-to-psd/runtime.local.json.bak','拾界插件/开发源码/自动拆图/service.json.old','拾界插件/auth.json','拾界插件/依赖/运行环境/python/site-packages/flask/__pycache__/a.pyc']
   for rel in wanted+banned:
    p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('fixture',encoding='utf-8')
   output=Path(tmp)/'share.zip'; self.share.build_archive(root,output)
   with zipfile.ZipFile(output) as z:
    names=set(z.namelist())
    self.assertTrue(set(wanted)<=names)
    self.assertFalse(set(banned)&names)
 def test_rejects_symlink_outside_bundle(self):
  self.assertFalse(self.share.is_allowed(Path('拾界插件/依赖/自动拆图/packages/torch/file.py')))
if __name__=='__main__': unittest.main()
