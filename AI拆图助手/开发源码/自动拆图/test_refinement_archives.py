"""Historical manual versions stay outside every automatic correction path."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import refine_ui
import selected_refine
from test_refine_ui import fixture


class RefinementArchiveTests(unittest.TestCase):
    def setUp(self):
        self.source, self.scene = fixture()
        text = copy.deepcopy(self.scene['nodes'][2])
        text.update(id='archive-text', name='文案 · 修正前版本 1', versionArchived=True,
                    versionOf='text', visible=False, hidden=True,
                    reviewIssue='old observation', fontResolved='old metadata')
        image = copy.deepcopy(self.scene['nodes'][1])
        image.update(id='archive-image', name='图片 · 修正前版本 1', versionArchived=True,
                     versionOf='image', visible=False, hidden=True,
                     generationRecord={'actualImageGeneration': True, 'hash': 'original bytes'})
        self.scene['nodes'].extend([text, image])
        self.archives = copy.deepcopy(self.scene['nodes'][-2:])

    def test_manifest_contains_only_current_editable_nodes(self):
        self.assertEqual({n['id'] for n in refine_ui._editable_nodes(self.scene)}, {'text', 'panel'})

    def test_actual_patch_request_does_not_send_archives_as_editable(self):
        observed = []
        def stop_after_manifest(prompt, *args, **kwargs):
            observed.append(prompt)
            raise RuntimeError('stop after captured manifest')
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(refine_ui, '_export', side_effect=lambda scene, project, cancelled: project/'1_过程/03_检查/模型输入工作图.png'), \
             patch.object(refine_ui.CLIENT, 'analyze', side_effect=stop_after_manifest), \
             patch.object(refine_ui.CLIENT, 'generate', side_effect=AssertionError('no generation')):
            with self.assertRaisesRegex(RuntimeError, 'captured manifest'):
                refine_ui._process(self.source, 'archives', lambda *_: None, lambda: False,
                                   self.source, Path(tmp), self.scene)
        self.assertEqual(len(observed), 1)
        self.assertNotIn('archive-text', observed[0])
        self.assertNotIn('archive-image', observed[0])

    def test_forged_patch_cannot_change_historical_native_layer(self):
        self.scene['nodes'][-2]['text'] = '历史文字'
        original_archives = copy.deepcopy(self.scene['nodes'][-2:])
        result, warnings = refine_ui.apply_patches(self.scene, [
            {'id': 'archive-text', 'changes': {'fill': '#123456'}},
            {'id': 'panel', 'changes': {'fill': '#456789'}},
        ])
        self.assertEqual(result['nodes'][-2:], original_archives)
        self.assertEqual(result['nodes'][3]['fill'], '#456789')
        self.assertTrue(any('历史版本' in warning for warning in warnings), warnings)

    def test_archive_only_scene_cannot_enable_whole_ui_refinement(self):
        scene = {**self.scene, 'nodes': [copy.deepcopy(self.archives[0])], 'groups': []}
        self.assertFalse(refine_ui.can_refine(scene))

    def test_hidden_history_does_not_reject_valid_live_text_patch_as_duplicate(self):
        result, warnings = refine_ui.apply_patches(self.scene, [{'id': 'text', 'changes': {'fill': '#123456'}}])
        self.assertEqual(warnings, [])
        self.assertEqual(result['nodes'][2]['fill'], '#123456')
        self.assertEqual(result['nodes'][-2:], self.archives)

    def test_forged_selected_archive_request_fails_before_any_review_or_repair(self):
        for ids in (['archive-image'], ['image', 'archive-image'], ['archive-text']):
            with self.subTest(ids=ids), tempfile.TemporaryDirectory() as tmp, \
                 patch('acceptance.review_asset', return_value={'status': 'PASS', 'issues': []}) as review, \
                 patch('incremental_assets.extract_once') as generate, \
                 patch('incremental_assets.check_resume_native', side_effect=lambda source, scene, *a, **k: scene) as native:
                with self.assertRaisesRegex(ValueError, '历史版本'):
                    selected_refine._process(self.source, 'archives', lambda *_: None, lambda: False,
                                             self.source, Path(tmp), self.scene, ids)
                review.assert_not_called()
                generate.assert_not_called()
                native.assert_not_called()

    def test_valid_selected_current_image_preserves_historical_layers_exactly(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('acceptance.review_asset', return_value={'status': 'PASS', 'issues': []}) as review, \
             patch('incremental_assets.extract_once') as generate:
            result = selected_refine._process(self.source, 'archives', lambda *_: None, lambda: False,
                                             self.source, Path(tmp), self.scene, ['image'])
        self.assertEqual(review.call_count, 1)
        generate.assert_not_called()
        self.assertEqual(result['nodes'][-2:], self.archives)


if __name__ == '__main__':
    unittest.main()
