import base64
import tempfile
from pathlib import Path
from django.test import SimpleTestCase
from PIL import Image, ImageDraw
from workflow_assets import image_node


class AssetPlacement(SimpleTestCase):
    def test_invisible_alpha_noise_does_not_shrink_the_visible_asset(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'line.png'
            for opacity in (255, 12):
                with self.subTest(opacity=opacity):
                    image = Image.new('RGBA', (1200, 400))
                    ImageDraw.Draw(image).rectangle((100, 196, 1099, 203), fill=(240, 190, 80, opacity))
                    image.putpixel((0, 0), (240, 190, 80, 1))
                    image.putpixel((1199, 399), (240, 190, 80, 1))
                    image.save(file)
                    node = image_node(file, 'line', [60, 40, 250, 2])
                    scale = node['width'] / image.width
                    self.assertEqual((node['x'] + 100*scale, node['y'] + 196*scale, 1000*scale, 8*scale), (60, 40, 250, 2))
                    self.assertEqual(base64.b64decode(node['src'].split(',')[1]), file.read_bytes())
                    fixed = image_node(file, 'fixed', [0, 0, 1200, 400], preserve_canvas=True)
                    self.assertEqual((fixed['x'], fixed['y'], fixed['width'], fixed['height']), (0, 0, 1200, 400))
            # Truly faint artwork remains valid; no pixels are erased or invented.
            Image.new('RGBA', (200, 100), (50, 80, 110, 1)).save(file)
            faint = image_node(file, 'faint', [10, 20, 200, 100])
            self.assertEqual((faint['x'], faint['y'], faint['width'], faint['height']), (10, 20, 200, 100))

    def test_edge_cropped_object_is_not_shrunk_into_its_visible_sliver(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'asset.png'
            Image.new('RGBA', (200, 100), 'green').save(file)
            result = image_node(file, 'table', [100, 150, 200, 50], source_size=(300, 200))
            self.assertEqual((result['x'], result['y'], result['width'], result['height']), (100, 150, 200, 100))
            self.assertEqual(result['placementBasis'], 'source-boundary-estimate')
            inside = image_node(file, 'object', [20, 20, 200, 50], source_size=(300, 200))
            self.assertEqual((inside['width'], inside['height']), (100, 50))
