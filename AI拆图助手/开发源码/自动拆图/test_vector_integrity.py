"""Exercise the real tracer through native canvas, including small topology.

High overall IoU can hide a lost dot or filled counter. Check their actual
coverage separately and constrain smooth contours to a compact curve budget.
"""
import base64
import io
import json
import re
import subprocess
import unittest

import cv2
import numpy as np

from runtime import ROOT
from vector_trace import trace


def render(alpha, d):
    script = """
const cv=require('./依赖/构建工具/node_modules/@napi-rs/canvas');
const fs=require('fs'),n=JSON.parse(fs.readFileSync(0,'utf8'));
const c=cv.createCanvas(n.width,n.height),ctx=c.getContext('2d');
ctx.fillStyle='#ffffff';ctx.fill(new cv.Path2D(n.d),'evenodd');
process.stdout.write(Buffer.from(ctx.getImageData(0,0,n.width,n.height).data).toString('base64'));
"""
    result = subprocess.run(
        ['node', '-e', script], cwd=ROOT, input=json.dumps({
            'width': alpha.shape[1], 'height': alpha.shape[0], 'd': d,
        }), capture_output=True, text=True, check=True,
    )
    return np.frombuffer(base64.b64decode(result.stdout), np.uint8).reshape(
        (*alpha.shape, 4))[:, :, 3]


class VectorIntegrityTests(unittest.TestCase):
    def solid_with_counter(self):
        alpha = np.zeros((80, 100), np.uint8)
        alpha[5:70, 5:90] = 255
        alpha[30:50, 30:50] = 0
        return alpha

    def test_disconnected_dot_survives_alongside_nonempty_main_contour(self):
        alpha = self.solid_with_counter()
        alpha[75, 94] = 255
        actual = render(alpha, trace(alpha))
        self.assertGreater(actual[75, 94], 240, 'nonempty main path must not hide a lost ink dot')
        self.assertLess(actual[74, 94], 10, 'tiny ink fallback must not enlarge the source mark')

    def test_one_pixel_counter_stays_transparent(self):
        alpha = self.solid_with_counter()
        alpha[15, 15] = 0
        actual = render(alpha, trace(alpha))
        self.assertLess(actual[15, 15], 10, 'small counters must not be filled by the spline tracer')
        self.assertGreater(actual[15, 16], 240)

    def test_one_pixel_island_inside_counter_survives(self):
        alpha = self.solid_with_counter()
        alpha[39, 39] = 255
        actual = render(alpha, trace(alpha))
        self.assertGreater(actual[39, 39], 240)
        self.assertLess(actual[39, 38], 10)

    def test_smooth_contour_keeps_curves_without_per_pixel_vector_expansion(self):
        alpha = np.zeros((80, 100), np.uint8)
        cv2.circle(alpha, (45, 40), 30, 255, -1)
        d = trace(alpha)
        actual = render(alpha, d) > 128
        expected = alpha > 128
        self.assertGreater(np.count_nonzero(actual & expected) / np.count_nonzero(actual | expected), .97)
        self.assertIn('C', d)
        self.assertLess(len(re.findall('[MLCQHVZ]', d)), 35)

    def test_native_psd_roundtrip_preserves_tiny_topology_and_original_fill(self):
        from psd_tools import PSDImage
        alpha = self.solid_with_counter()
        alpha[15, 15] = 0
        alpha[39, 39] = 255
        alpha[75, 94] = 255
        cv2.line(alpha, (31, 32), (35, 36), 255, 1)
        script = """
const fs=require('fs'),cv=require('./依赖/构建工具/node_modules/@napi-rs/canvas');
globalThis.document={createElement:()=>cv.createCanvas(1,1)};
globalThis.Path2D=cv.Path2D;globalThis.ShijieNodeCanvas=cv;
require('./依赖/构建工具/node_modules/ag-psd').initializeCanvas(cv.createCanvas);
const S=require('./开发源码/自动拆图/scene-native.cjs'),n=JSON.parse(fs.readFileSync(0,'utf8'));
S.psd({format:'shijie-scene',version:2,title:'traced ink',width:100,height:80,
nodes:[{id:'ink',name:'ink',type:'path',x:0,y:0,width:100,height:80,fill:'#1f6789',d:n.d}],edges:[]})
.then(b=>process.stdout.write(Buffer.from(b).toString('base64'))).catch(e=>{console.error(e);process.exit(1)});
"""
        result = subprocess.run(['node', '-e', script], cwd=ROOT,
            input=json.dumps({'d': trace(alpha)}), capture_output=True, text=True, check=True)
        document = PSDImage.open(io.BytesIO(base64.b64decode(result.stdout)))
        layer = document[0]
        self.assertTrue(layer.has_vector_mask())
        self.assertEqual(len(list(layer.effects)), 0, 'tracing must not invent stroke/shadow effects')
        image = document.composite(force=True)
        for point in [(15, 15), (38, 39), (40, 40)]:
            self.assertLess(image.getpixel(point)[3], 10)
        for point in [(16, 15), (39, 39), (94, 75), (31, 32), (33, 34), (35, 36)]:
            pixel = image.getpixel(point)
            self.assertGreater(pixel[3], 240)
            self.assertTrue(all(abs(a-b)<2 for a,b in zip(pixel[:3], (31, 103, 137))), pixel)

    def test_touching_thin_second_ink_is_not_recoloured_as_dominant_ink(self):
        from engine import flat_ink_parts
        patch = np.full((40, 70, 3), (240, 150, 110), np.uint8)
        ink = np.zeros((40, 70), np.uint8)
        patch[10:30, 10:40] = (255, 255, 255)
        ink[10:30, 10:41] = 255
        patch[10:30, 40] = (30, 80, 220)
        parts = flat_ink_parts(patch, ink)
        blue = [(part, color) for part, color in parts if np.linalg.norm(color-(30, 80, 220)) < 5]
        self.assertEqual(len(blue), 1, 'touching a main silhouette does not turn a stable blue ink into antialiasing')
        self.assertEqual(int(np.count_nonzero(blue[0][0])), 20)

    def test_material_antialias_transition_is_not_an_extra_flat_ink(self):
        from engine import flat_ink_parts
        material = np.array((240, 150, 110), np.uint8)
        patch = np.full((40, 70, 3), material, np.uint8)
        ink = np.zeros((40, 70), np.uint8)
        patch[10:30, 10:40] = (255, 255, 255)
        patch[10:30, 40] = (material.astype(float) + 255) / 2
        ink[10:30, 10:41] = 255
        parts = flat_ink_parts(patch, ink)
        self.assertEqual(len(parts), 1)

    def test_touching_diagonal_second_ink_keeps_every_blue_pixel(self):
        from engine import flat_ink_parts
        patch = np.full((40, 40, 3), 255, np.uint8)
        patch[5:25, 5:25] = (200, 20, 20)
        for i in range(10):
            patch[24+i, 24+i] = (20, 20, 200)
        ink = np.any(patch != 255, axis=2).astype('uint8') * 255
        parts = flat_ink_parts(patch, ink)
        blue = [(part, color) for part, color in parts if np.linalg.norm(color-(20, 20, 200)) < 5]
        self.assertEqual(len(blue), 1, 'diagonal connectivity is genuine second ink, not an axial-run requirement')
        np.testing.assert_array_equal(blue[0][0], np.all(patch == (20, 20, 200), axis=2))

    def test_touching_small_solid_accent_keeps_original_colour(self):
        from engine import flat_ink_parts
        patch = np.full((40, 40, 3), 255, np.uint8)
        patch[5:25, 5:25] = (200, 20, 20)
        patch[10:13, 24:27] = (20, 20, 200)
        ink = np.any(patch != 255, axis=2).astype('uint8') * 255
        parts = flat_ink_parts(patch, ink)
        blue = [(part, color) for part, color in parts if np.linalg.norm(color-(20, 20, 200)) < 5]
        self.assertEqual(len(blue), 1, 'a solid 3x3 detail must not require a 5x5 interior or five-pixel run')
        self.assertEqual(np.count_nonzero(blue[0][0]), 9)

    def test_diagonal_and_compact_antialias_components_do_not_create_ink_layers(self):
        from engine import flat_ink_parts
        for shape in ['diagonal', 'compact']:
            with self.subTest(shape=shape):
                patch = np.full((40, 40, 3), 255, np.uint8)
                patch[5:25, 5:25] = (200, 20, 20)
                transition = (227, 137, 137)
                if shape == 'diagonal':
                    for i in range(10):
                        patch[24+i, 24+i] = transition
                else:
                    patch[10:13, 24:27] = transition
                ink = np.any(patch != 255, axis=2).astype('uint8') * 255
                self.assertEqual(len(flat_ink_parts(patch, ink)), 1)

    def test_one_pixel_diagonal_renders_as_one_complete_boundary_not_degenerate_curves(self):
        alpha = np.zeros((80, 100), np.uint8)
        cv2.line(alpha, (5, 5), (70, 65), 255, 1)
        d = trace(alpha)
        actual = render(alpha, d)
        np.testing.assert_array_equal(actual, alpha, 'a nonempty but zero-area spline must not publish missing ink')
        self.assertEqual(d.count('M'), 1, 'one connected thin strip must not become one rectangle per pixel')
        self.assertLessEqual(len(re.findall('[MLCQHVZ]', d)), 270)

    def test_diagonal_fallback_does_not_replace_good_smooth_main_contour(self):
        alpha = np.zeros((100, 150), np.uint8)
        cv2.circle(alpha, (40, 40), 28, 255, -1)
        cv2.line(alpha, (90, 10), (130, 55), 255, 1)
        d = trace(alpha)
        actual = render(alpha, d)
        expected = np.zeros_like(alpha)
        cv2.line(expected, (90, 10), (130, 55), 255, 1)
        np.testing.assert_array_equal(actual[:, 85:], expected[:, 85:])
        self.assertIn('C', d, 'the good smooth contour must retain its original spline')

    def test_excessive_degenerate_outline_fails_explicitly_instead_of_publishing_missing_ink(self):
        alpha = np.zeros((1100, 1100), np.uint8)
        cv2.line(alpha, (5, 5), (1090, 1090), 255, 1)
        with self.assertRaisesRegex(ValueError, '细线.*校对'):
            trace(alpha)


if __name__ == '__main__':
    unittest.main()
