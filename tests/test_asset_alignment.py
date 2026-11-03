import base64
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image
from django.test import SimpleTestCase

from asset_geometry import align_to_source


class AssetAlignment(SimpleTestCase):
    def sample(self):
        rng = np.random.default_rng(41)
        pixels = np.zeros((360, 520, 4), dtype=np.uint8)
        pixels[25:340, 20:500, :3] = cv2.GaussianBlur(rng.integers(20, 235, (315, 480, 3), dtype=np.uint8), (5, 5), 1)
        pixels[25:340, 20:500, 3] = 255
        for x, y in rng.integers([30, 35], [480, 320], (100, 2)):
            cv2.circle(pixels, (int(x), int(y)), int(rng.integers(4, 12)), (*map(int, rng.integers(20, 235, 3)), 255), -1)
        image = Image.fromarray(pixels)
        raw = io.BytesIO(); image.save(raw, 'PNG')
        source = Image.new('RGB', (500, 330), (100, 70, 140))
        small = image.resize((260, 180))
        source.paste(small, (120, 80), small)
        # Occlusion must not force the complete object into its visible fragment.
        source.paste((100, 70, 140), (120, 205, 380, 260))
        node = dict(id='asset', type='image', name='complete object', x=160, y=90,
                    width=150, height=100, src='data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode())
        return source, node

    def test_recovers_source_scale_and_anchor_without_changing_pixels(self):
        source, node = self.sample()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.png'; source.save(path)
            aligned = align_to_source(path, node)
        self.assertIsNotNone(aligned)
        for key, expected in [('x', 120), ('y', 80), ('width', 260), ('height', 180)]:
            self.assertAlmostEqual(aligned[key], expected, delta=1)
        self.assertEqual(aligned['src'], node['src'])
        self.assertEqual(node['width'], 150)
        self.assertGreaterEqual(aligned['sourceAlignment']['inliers'], 12)

    def test_no_evidence_keeps_the_existing_layer(self):
        _, node = self.sample()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'blank.png'; Image.new('RGB', (500, 330), 'white').save(path)
            self.assertIsNone(align_to_source(path, node))

    def test_off_canvas_search_does_not_wrap_around_negative_coordinates(self):
        source, node = self.sample(); node['x'] = -300
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.png'; source.save(path)
            self.assertTrue(align_to_source(path, node) is None)

    def test_extraction_uses_original_landmarks_before_returning_a_layer(self):
        from workflow_assets import complete_asset
        source, node = self.sample()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); assets = root / 'assets'; structure = root / 'structure'
            assets.mkdir(); structure.mkdir(); original = root / 'source.png'; source.save(original)
            def generate(prompt, references, target, **kwargs):
                target.write_bytes(base64.b64decode(node['src'].split(',', 1)[1]))
                return dict(file=str(target), actualImageGeneration=True, transparent=True)
            with patch('workflow_assets.CLIENT.generate', side_effect=generate):
                result = complete_asset(original, node, assets, structure, lambda: False, force_repair=True)
        self.assertAlmostEqual(result['width'], 260, delta=1)
        self.assertAlmostEqual(result['x'], 120, delta=1)
        self.assertEqual(result['src'], node['src'])

    def test_invalid_geometry_is_rejected(self):
        source, node = self.sample(); node['width'] = float('nan')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.png'; source.save(path)
            with self.assertRaises(ValueError):
                align_to_source(path, node)
