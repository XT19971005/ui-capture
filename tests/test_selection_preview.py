import base64
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase
from PIL import Image
from selected_entities import kernel


class SelectionPreview(SimpleTestCase):
    def test_generation_backups_are_images_not_megabytes_of_prompt_text(self):
        from selected_entities import diagnose
        from region_refine import diagnose as diagnose_region
        raw=io.BytesIO();Image.new('RGBA',(20,20),'red').save(raw,'PNG')
        node=dict(id='asset',name='red',type='image',x=0,y=0,width=20,height=20,src='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode(),
                  completionBase={'src':'image-backup-'+'a'*1100000})
        scene=dict(format='shijie-scene',version=2,width=20,height=20,nodes=[node],groups=[],edges=[])
        def analyze(prompt,*args,**kwargs):
            self.assertLess(len(prompt),10000);self.assertNotIn('image-backup-',prompt)
            result=dict(assetChecks=[dict(id='asset',status='PASS',issues=[],placement=None)],patches=[],notes=[])
            if 'entities' in args[1]['properties']:result['entities']=[]
            return result
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';Image.new('RGB',(20,20),'red').save(source)
            with patch('codex_client.CLIENT.analyze',side_effect=analyze):
                diagnose(source,scene,[node],root,lambda:False,None)
                diagnose_region(source,scene,[node],dict(x=0,y=0,width=20,height=20),root,lambda:False,None)

    def test_ai_selection_evidence_contains_raster_pixels_and_ancestor_mask(self):
        buffer = io.BytesIO()
        Image.new('RGBA', (20, 20), 'red').save(buffer, 'PNG')
        node = dict(id='asset', name='red', type='image', x=20, y=10, width=20, height=20,
                    src='data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode())
        scene = dict(format='shijie-scene', version=2, width=60, height=40, nodes=[node], edges=[],
                     groups=[dict(id='group', name='masked', children=['asset'], opacity=.5,
                                  displayMask=dict(enabled=True, type='rect', x=20, y=10, width=10, height=20))])
        with tempfile.TemporaryDirectory() as folder:
            prefix = str(Path(folder) / 'preview')
            kernel(dict(operation='preview', scene=scene, box=dict(x=20, y=10, width=20, height=20), prefix=prefix))
            image = Image.open(prefix + '-dark.png').convert('RGB')
            red = image.getpixel((5, 5))
            self.assertGreater(red[0], 130, 'AI evidence must contain the selected image')
            self.assertLess(red[1], 20, 'parent opacity must apply')
            self.assertEqual(image.getpixel((15, 5)), (24, 25, 28), 'parent display mask must remain')
