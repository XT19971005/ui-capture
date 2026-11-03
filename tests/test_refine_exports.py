import tempfile
from pathlib import Path
from django.test import SimpleTestCase
from PIL import Image
from refine_ui import _export


class RefineExports(SimpleTestCase):
    def test_complete_refine_export_and_independent_readback_runs_on_ubuntu(self):
        with tempfile.TemporaryDirectory(prefix='shijie-refine-test-') as folder:
            root = Path(folder)
            for name in ('1_过程/02_结构', '1_过程/03_检查', '2_输出'):
                (root / name).mkdir(parents=True)
            original = root / '2_输出/original.png'
            Image.new('RGB', (160, 100), 'white').save(original)
            scene = dict(format='shijie-scene', version=2, title='Refine', width=160, height=100, groups=[], edges=[],
                         nodes=[dict(id='text', name='caption', type='text', text='验收', x=10, y=10,
                                     width=80, height=35, fontSize=30, fontFamily='Noto Sans CJK SC', fontWeight=700, fill='#000000')],
                         delivery=dict(project=str(root), psd=str(root / '2_输出/result.psd'), original=str(original)))
            preview = _export(scene, root, lambda: False)
            self.assertEqual(Image.open(preview).size, (160, 100))
