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
   wanted=['AI拆图助手/重启AI拆图助手引擎.ps1','AI拆图助手/重启AI拆图助手引擎.cmd','AI拆图助手/启动AI拆图助手.ps1','AI拆图助手/开发源码/自动拆图/server.py','AI拆图助手/插件程序/edge/icon.png','AI拆图助手/依赖/运行环境/python/python.exe','AI拆图助手/依赖/运行环境/python/python310._pth','技能包/同步到Codex.ps1','技能包/维护约定.md','技能包/game-ui-to-psd/SKILL.md','技能包/依赖/Node/node_modules/ag-psd/index.js']
   banned=['AI拆图助手/开发源码/工作台增强/test-free-assistant-browser.cjs','AI拆图助手/项目/a.psd','AI拆图助手/自检记录/a.png','AI拆图助手/插件程序/示例/a.json','AI拆图助手/插件程序/edge/vendor/ocr/lang/chi_sim.traineddata','AI拆图助手/开发源码/构建PSD.cjs','AI拆图助手/开发源码/自动拆图/diagnose_font.cjs','AI拆图助手/开发源码/自动拆图/native-host.json','AI拆图助手/开发源码/自动拆图/native-host.cmd','AI拆图助手/依赖/运行环境/python/site-packages/torch/a.py','AI拆图助手/依赖/自动拆图/models/a.safetensors','技能包/game-ui-to-psd/runtime.local.json','技能包/game-ui-to-psd/runtime.local.json.bak','AI拆图助手/开发源码/自动拆图/service.json.old','AI拆图助手/auth.json','AI拆图助手/依赖/运行环境/python/site-packages/flask/__pycache__/a.pyc']
   for rel in wanted+banned:
    p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('fixture',encoding='utf-8')
   output=Path(tmp)/'share.zip'; self.share.build_archive(root,output)
   with zipfile.ZipFile(output) as z:
    names=set(z.namelist())
    self.assertTrue(set(wanted)<=names)
    self.assertFalse(set(banned)&names)
 def test_rejects_symlink_outside_bundle(self):
  self.assertFalse(self.share.is_allowed(Path('AI拆图助手/依赖/自动拆图/packages/torch/file.py')))
if __name__=='__main__': unittest.main()
