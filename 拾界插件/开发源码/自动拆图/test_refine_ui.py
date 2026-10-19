import base64, copy, hashlib, io, json, os, threading, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageFont
import engine, server


def fixture():
    source = engine.png(Image.new('RGB', (180, 120), '#445566'))
    item = engine.png(Image.new('RGBA', (30, 45), '#dd9922'))
    scene = {'format': 'shijie-scene', 'version': 2, 'width': 180, 'height': 120,
             'source': source, 'edges': [], 'recognition': {'reviewStatus': 'NEEDS_REVIEW'},
             'nodes': [
                 {'id': 'bg', 'name': '背景', 'type': 'image', 'assetKind': 'background', 'x': 0, 'y': 0, 'width': 180, 'height': 120, 'src': source},
                 {'id': 'image', 'name': '完整图片', 'type': 'image', 'x': 15, 'y': 20, 'width': 30, 'height': 45, 'src': item,
                  'layerStyle': {'enabled': True, 'outerGlow': {'enabled': True, 'color': '#ffaa00', 'size': 2, 'opacity': .2}},
                  'displayMask': {'type': 'rect', 'x': 15, 'y': 20, 'width': 30, 'height': 45, 'enabled': True}},
                 {'id': 'text', 'name': '文案', 'type': 'text', 'text': '原文', 'fontSize': 14, 'fontFamily': 'Microsoft YaHei', 'fontWeight': 400,
                  'x': 70, 'y': 25, 'width': 80, 'height': 22, 'fill': '#ffffff', 'fitWidth': True},
                 {'id': 'panel', 'name': '简单面板', 'type': 'rect', 'x': 65, 'y': 60, 'width': 90, 'height': 30, 'fill': '#334455', 'radius': 3}],
             'groups': [{'id': 'parent', 'name': '父组', 'children': ['image'], 'opacity': .9,
                         'displayMask': {'type': 'rect', 'x': 0, 'y': 0, 'width': 180, 'height': 120, 'enabled': True}}]}
    return source, scene


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.source, self.scene = fixture()
        server.jobs.clear()

    def request(self, resume):
        return self.client.post('/jobs', json={'mode': 'refine-ui', 'image': self.source,
                               'original': self.source, 'resume': resume},
                               base_url='http://127.0.0.1:19217', headers={'X-Shijie-Token': server.TOKEN})

    def test_complete_refine_is_accepted(self):
        with patch.object(server.pool, 'submit') as submit:
            response = self.request(self.scene)
        self.assertEqual(response.status_code, 202, response.json)
        self.assertEqual(submit.call_args.args[4], 'refine-ui')
        self.assertEqual(server.jobs[response.json['id']]['partial'], self.scene)

    def test_partial_and_missing_refine_are_rejected(self):
        for value in (None, {**self.scene, '_partial': True}):
            with patch.object(server.pool, 'submit') as submit:
                self.assertEqual(self.request(value).status_code, 400)
                submit.assert_not_called()

    def test_refine_failure_and_cancel_keep_original_complete_snapshot(self):
        import refine_ui
        for exc, expected in ((RuntimeError('受控失败'), 'failed'), (InterruptedError('受控取消'), 'cancelled')):
            ident = expected
            server.jobs[ident] = {'status': 'queued', 'progress': 0, 'cancel': threading.Event(), 'partial': copy.deepcopy(self.scene)}
            with patch.object(refine_ui, 'process', side_effect=exc) as run, patch.object(server.logging, 'exception'):
                server.run(ident, self.source, '精修', 'refine-ui', self.source, self.scene)
            run.assert_called_once()
            self.assertEqual(server.jobs[ident]['status'], expected)
            self.assertEqual(server.jobs[ident]['partial'], self.scene)
            self.assertNotIn('_partial', server.jobs[ident]['partial'])

    def test_codex_dispatch_is_unchanged(self):
        import codex_pipeline
        server.jobs['old'] = {'status': 'queued', 'progress': 0, 'cancel': threading.Event()}
        with patch.object(codex_pipeline, 'process', return_value={'_sessionId': 'controlled'}) as run:
            server.run('old', self.source, '拆图', 'codex', self.source)
        run.assert_called_once()
        self.assertEqual(server.jobs['old']['status'], 'completed')

    def test_refine_eligibility_blocks_processing_images_and_locked_background_only(self):
        processing = copy.deepcopy(self.scene)
        processing['recognition']['reviewStatus'] = 'PROCESSING'
        only_images = copy.deepcopy(self.scene)
        only_images['nodes'] = only_images['nodes'][:2]
        locked = copy.deepcopy(self.scene)
        locked['nodes'] = [locked['nodes'][3]]
        locked['nodes'][0].update(locked=True, assetKind='background')
        for value in (processing, only_images, locked):
            with patch.object(server.pool, 'submit') as submit:
                self.assertEqual(self.request(value).status_code, 400)
                submit.assert_not_called()
        manual = copy.deepcopy(self.scene)
        manual.pop('recognition')
        with patch.object(server.pool, 'submit'):
            self.assertEqual(self.request(manual).status_code, 202)


class PatchTests(unittest.TestCase):
    def setUp(self):
        import refine_ui
        self.refine = refine_ui
        self.source, self.scene = fixture()

    def impact_scene(self):
        font = ImageFont.truetype('C:/Windows/Fonts/impact.ttf', 100)
        left, top, right, bottom = font.getbbox('HELLO')
        self.assertEqual((right-left, bottom-top), (229, 81))
        scene = copy.deepcopy(self.scene)
        scene.update(width=600, height=300, groups=[])
        scene['nodes'] = [{'id': 'title', 'name': '标题', 'type': 'text', 'text': 'HELLO',
                           'fontFamily': 'Impact', 'fontSize': 100, 'fontWeight': 400,
                           'x': 20, 'y': 20, 'width': right-left, 'height': bottom-top,
                           'fill': '#ffffff', 'fitWidth': False, 'textSkew': .12,
                           'fontResolved': 'Impact'}]
        return scene

    def test_colour_position_or_unchanged_font_patch_preserves_existing_text_metrics(self):
        scene = self.impact_scene()
        for changes in ({'fill': '#112233'}, {'x': 35}, {'fill': '#112233', 'fontSize': 100}):
            with self.subTest(changes=changes):
                result, warnings = self.refine.apply_patches(scene, [{'id': 'title', 'changes': changes}])
                expected = {**scene['nodes'][0], **changes}
                self.assertEqual(result['nodes'][0], expected)
                self.assertEqual(warnings, [])

    def test_font_change_fits_visible_glyph_box_instead_of_em_height(self):
        scene = self.impact_scene()
        scene['nodes'][0].update(fontFamily='Arial', textSkew=0)
        result, warnings = self.refine.apply_patches(scene, [{'id': 'title', 'changes': {'fontFamily': 'Impact'}}])
        self.assertEqual(result['nodes'][0]['fontSize'], 100)
        self.assertEqual(result['nodes'][0]['fontFamily'], 'Impact')
        self.assertFalse(result['nodes'][0]['fitWidth'])
        self.assertEqual(warnings, [])

    def test_nested_parent_lock_blocks_patch_and_refine_eligibility(self):
        scene = copy.deepcopy(self.scene)
        scene['nodes'] = [scene['nodes'][2], scene['nodes'][3]]
        scene['groups'] = [{'id': 'outer', 'name': '锁定父组', 'children': ['inner'], 'locked': True},
                           {'id': 'inner', 'name': '子组', 'children': ['text', 'panel']}]
        result, warnings = self.refine.apply_patches(scene, [
            {'id': 'text', 'changes': {'fill': '#112233'}},
            {'id': 'panel', 'changes': {'fill': '#112233'}}])
        self.assertEqual(result, scene)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all('解锁' in w for w in warnings))
        self.assertFalse(self.refine.can_refine(scene))

    def test_model_editable_list_excludes_descendants_of_locked_group(self):
        from codex_client import CLIENT
        scene = copy.deepcopy(self.scene)
        scene['groups'].append({'id': 'locked-parent', 'name': '锁定父组', 'children': ['panel'], 'locked': True})

        def analyze(prompt, *args, **kwargs):
            editable = json.loads(prompt.split('已有可修改图层：', 1)[1])
            self.assertEqual([n['id'] for n in editable], ['text'])
            raise RuntimeError('受控停在模型清单检查')

        with patch.object(self.refine, '_export', return_value=Path(__file__)), \
             patch.object(CLIENT, 'analyze', side_effect=analyze), \
             patch.object(CLIENT, 'generate', side_effect=AssertionError('ImageGen forbidden')) as gen:
            with self.assertRaisesRegex(RuntimeError, '受控停在模型清单检查'):
                self.refine.process(self.source, '锁定过滤', lambda *_: None, lambda: False,
                                    original_source=self.source, resume_scene=scene)
            gen.assert_not_called()

    def test_frozen_images_groups_source_and_input(self):
        before = copy.deepcopy(self.scene)
        result, warnings = self.refine.apply_patches(self.scene, [
            {'id': 'text', 'changes': {'text': '修正文案', 'fontSize': 16, 'fontFamily': '未知字体', 'letterSpacing': 1}},
            {'id': 'panel', 'changes': {'fill': '#556677'}},
            {'id': 'image', 'changes': {'x': 22}},
            {'id': 'parent', 'changes': {'opacity': .3}},
            {'id': 'text', 'changes': {'type': 'image'}}])
        self.assertEqual(self.scene, before)
        self.assertEqual(result['nodes'][:2], before['nodes'][:2])
        self.assertEqual(result['groups'], before['groups'])
        self.assertEqual(result['source'], before['source'])
        # Ambiguous duplicate targets are both ignored rather than choosing one.
        self.assertEqual(result['nodes'][2], before['nodes'][2])
        self.assertEqual(result['nodes'][3]['fill'], '#556677')
        self.assertGreaterEqual(len(warnings), 3)

    def test_bad_patch_is_local_and_valid_text_does_not_stretch(self):
        result, warnings = self.refine.apply_patches(self.scene, [
            {'id': 'missing', 'changes': {'fill': '#000000'}},
            {'id': 'panel', 'changes': {'x': 170}},
            {'id': 'text', 'changes': {'text': '修正', 'fontSize': 16, 'fontFamily': '未知字体', 'letterSpacing': 1}}])
        self.assertEqual(result['nodes'][3], self.scene['nodes'][3])
        text = result['nodes'][2]
        self.assertEqual(text['text'], '修正')
        self.assertFalse(text['fitWidth'])
        self.assertIn(text['fontFamily'], ('Arial', 'Microsoft YaHei', 'SimHei'))
        self.assertGreaterEqual(len(warnings), 3)

    def test_identity_unsupported_fields_nonfinite_and_path_are_rejected(self):
        for changes in ({'id': 'new'}, {'layerStyle': {}}, {'x': float('nan')}, {'width': 0}, {'fill': '#fff'}, {'radius': 9000}):
            result, warnings = self.refine.apply_patches(self.scene, [{'id': 'panel', 'changes': changes}])
            self.assertEqual(result, self.scene)
            self.assertTrue(warnings)

    def test_cancel_and_bad_source_do_not_call_models_or_publish_ram(self):
        from codex_client import CLIENT
        from session_outputs import SESSIONS
        before = SESSIONS.count()
        with patch.object(CLIENT, 'analyze') as analyze, patch.object(CLIENT, 'generate') as generate:
            with self.assertRaises(InterruptedError):
                self.refine.process(self.source, '精修', lambda *_: None, lambda: True, resume_scene=self.scene)
            wrong = engine.png(Image.new('RGB', (180, 120), 'red'))
            with self.assertRaises(ValueError):
                self.refine.process(wrong, '精修', lambda *_: None, lambda: False, resume_scene=self.scene)
        analyze.assert_not_called()
        generate.assert_not_called()
        self.assertEqual(SESSIONS.count(), before)

    def test_bad_ui_stroke_and_native_effect_can_be_disabled_without_touching_raster(self):
        text = self.scene['nodes'][2]
        text.update(stroke='#aa00ff', strokeWidth=10, layerStyle={'enabled': True, 'blendMode': 'normal',
                    'dropShadow': {'enabled': True, 'opacity': .9, 'color': '#9900ff', 'size': 9, 'angle': 120, 'distance': 5}})
        before = copy.deepcopy(self.scene)
        result, warnings = self.refine.apply_patches(self.scene, [{'id': 'text', 'changes': {'strokeWidth': 0, 'layerStyle': {'enabled': False}}}])
        self.assertEqual(result['nodes'][2]['strokeWidth'], 0)
        self.assertFalse(result['nodes'][2]['layerStyle']['enabled'])
        self.assertEqual(result['nodes'][2]['layerStyle']['dropShadow'], text['layerStyle']['dropShadow'])
        self.assertEqual(result['nodes'][:2], before['nodes'][:2])
        self.assertEqual(result['groups'], before['groups'])
        self.assertFalse(warnings)

    def test_locked_ui_and_background_and_new_shadow_are_skipped(self):
        self.scene['nodes'][2]['locked'] = True
        self.scene['nodes'][3]['assetKind'] = 'background'
        result, warnings = self.refine.apply_patches(self.scene, [
            {'id': 'text', 'changes': {'text': '别修改'}}, {'id': 'panel', 'changes': {'fill': '#778899'}}])
        self.assertEqual(result, self.scene)
        self.assertEqual(len(warnings), 2)
        self.assertIn('解锁', warnings[0])
        self.scene['nodes'][2]['locked'] = False
        result, warnings = self.refine.apply_patches(self.scene, [{'id': 'text', 'changes': {'layerStyle': {'enabled': True, 'dropShadow': {'enabled': True, 'color': '#000000', 'size': 2, 'opacity': .5}}}}])
        self.assertEqual(result, self.scene)
        self.assertTrue(warnings)

    def test_ambiguous_scene_ids_leave_every_node_unchanged(self):
        self.scene['nodes'][2]['id'] = 'image'
        result, warnings = self.refine.apply_patches(self.scene, [
            {'id': 'image', 'changes': {'text': '误改'}}, {'id': 'panel', 'changes': {'fill': '#ffffff'}}])
        self.assertEqual(result, self.scene)
        self.assertTrue(warnings)

    def test_new_overlap_of_different_text_is_rejected_but_old_overlap_is_preserved(self):
        other = copy.deepcopy(self.scene['nodes'][2])
        other.update(id='other', name='另一段', text='另一段', y=75)
        self.scene['nodes'].append(other)
        result, warnings = self.refine.apply_patches(self.scene, [{'id': 'text', 'changes': {'y': 75}}])
        self.assertEqual(result, self.scene)
        self.assertTrue(warnings)
        other['y'] = 25
        result, warnings = self.refine.apply_patches(self.scene, [{'id': 'text', 'changes': {'fill': '#dddddd'}}])
        self.assertEqual(result['nodes'][2]['fill'], '#dddddd')
        self.assertFalse(warnings)

    @unittest.skipUnless(os.environ.get('SHIJIE_NATIVE_TEST') == '1', 'local native path kernel is opt-in')
    def test_local_path_coordinates_cannot_escape_valid_node_box(self):
        self.scene['nodes'].append({'id': 'path', 'name': '图标', 'type': 'path', 'x': 100, 'y': 90, 'width': 20, 'height': 20, 'fill': '#ffffff', 'd': 'M0 0 L20 0 L20 20 Z'})
        for d in ('M0 0 L99999 0 L20 20 Z', 'M0 0 C0 -100 20 -100 20 20 Z', 'M0 0 L2 Z'):
            result, warnings = self.refine.apply_patches(self.scene, [{'id': 'path', 'changes': {'d': d}}])
            self.assertEqual(result, self.scene)
            self.assertTrue(warnings)

    @unittest.skipUnless(os.environ.get('SHIJIE_NATIVE_TEST') == '1', 'actual local native PSD integration is opt-in')
    def test_real_psd_ram_download_cleanup_and_no_generation(self):
        from codex_client import CLIENT
        from psd_tools import PSDImage
        from session_outputs import SESSIONS
        root = Path(__file__).resolve().parents[3]
        report_dir = root / '测试结果/拾界_精修'
        report_dir.mkdir(parents=True, exist_ok=True)
        snapshots, calls, native_frozen = [], [], []
        self.scene['nodes'][2].update(stroke='#aa00ff', strokeWidth=10,
                   sourceTextId='ordinary-text', reviewIssue='旧坏文案和描边', assetReviewStatus='NEEDS_REVIEW',
                   layerStyle={'enabled': True, 'blendMode': 'normal', 'dropShadow': {'enabled': True, 'opacity': .9, 'color': '#9900ff', 'size': 9, 'angle': 120, 'distance': 5}})

        def analyze(prompt, images, schema, cancelled, **kwargs):
            self.assertFalse(cancelled())
            self.assertTrue(all(Path(p).is_file() for p in images))
            calls.append(list(map(str, images)))
            qa = next(Path(p).parent for p in images if Path(p).name == '合成预览.png')
            p = PSDImage.open(next((qa.parents[1] / '2_输出').glob('*.psd')))
            frozen = {}
            for layer in p.descendants():
                if layer.name in ('背景', '完整图片', '完整图片 · 显示蒙版', '父组'):
                    frozen[layer.name] = hashlib.sha256(layer._record.tobytes()).hexdigest()
            native_frozen.append(frozen)
            if 'patches' in schema['properties']:
                return {'patches': [{'id': 'text', 'changes': {'text': '已修正', 'fontSize': 15, 'letterSpacing': 1, 'strokeWidth': 0, 'layerStyle': {'enabled': False}}},
                                    {'id': 'panel', 'changes': {'fill': '#667788'}}], 'notes': ['受控模型，仅验证流程']}
            return {'status': 'PASS', 'summary': '受控观察，只验证调用与实际输入', 'issues': []}

        original = copy.deepcopy(self.scene)
        with patch.object(CLIENT, 'analyze', side_effect=analyze), patch.object(CLIENT, 'generate', side_effect=AssertionError('ImageGen forbidden')) as gen:
            result = self.refine.process(self.source, '受控精修', lambda *_: None, lambda: False,
                                         original_source=self.source, on_scene=lambda s: snapshots.append(s), resume_scene=self.scene)
            gen.assert_not_called()
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls[0]), 3)
        self.assertEqual(len(calls[1]), 4, 'QA should only add the two modified native UI layers')
        self.assertEqual(native_frozen[0], native_frozen[1], 'native raster/effect/mask/group records changed')
        self.assertTrue(all(not Path(p).exists() for call in calls for p in call))
        self.assertEqual(self.scene, original)
        self.assertEqual(result['nodes'][:2], original['nodes'][:2])
        self.assertEqual(result['groups'], original['groups'])
        self.assertEqual(result['source'], original['source'])
        self.assertEqual(result['nodes'][2]['text'], '已修正')
        self.assertEqual(result['recognition']['reviewStatus'], 'NEEDS_REVIEW')
        self.assertEqual(result['recognition']['refinementStatus'], 'PASS')
        self.assertEqual(result['nodes'][2]['strokeWidth'], 0)
        self.assertFalse(result['nodes'][2]['layerStyle']['enabled'])
        self.assertNotIn('reviewIssue', result['nodes'][2])
        self.assertEqual(result['nodes'][2]['assetReviewStatus'], 'PASS')
        from incremental_assets import preserve_native
        future = copy.deepcopy(original)
        future['nodes'][2]['id'] = 'new-text-id'
        preserve_native(future, result)
        self.assertEqual(future['nodes'][2]['text'], '已修正', 'resume must preserve the verified refined native text')
        self.assertEqual(future['nodes'][2]['id'], 'new-text-id')
        self.assertFalse(snapshots, 'unfinished refinement must not replace the editor snapshot')
        stored = SESSIONS.get(result['_sessionId'])
        raw = stored['psd']
        self.assertEqual(raw[:4], b'8BPS')
        sha = hashlib.sha256(raw).hexdigest()
        self.assertEqual(sha, result['delivery']['psdSHA256'])
        self.assertEqual(sha, stored['audit']['psdSHA256'])
        psd = PSDImage.open(io.BytesIO(raw))
        leaves = {l.name: l for l in psd.descendants() if not l.is_group()}
        self.assertEqual(leaves['文案'].text.replace('\r', ''), '已修正')
        self.assertEqual(tuple(leaves['文案'].transform[:4]), (1, 0, 0, 1))
        self.assertFalse(leaves['文案'].effects.enabled)
        self.assertEqual(leaves['完整图片'].bbox, (15, 20, 45, 65))
        expected = Image.open(io.BytesIO(base64.b64decode(original['nodes'][1]['src'].split(',', 1)[1]))).convert('RGBA')
        self.assertEqual(leaves['完整图片'].topil().convert('RGBA').tobytes(), expected.tobytes())
        self.assertEqual(len(leaves), 4)
        psd.composite(force=True).save(report_dir / '实际精修回读.png')
        client = server.app.test_client()
        response = client.get('/sessions/' + result['_sessionId'] + '/psd', base_url='http://127.0.0.1:19217', headers={'X-Shijie-Token': server.TOKEN})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, raw)
        self.assertIsNone(SESSIONS.get(result['_sessionId']))
        report = {'status': 'PASS_CONTROLLED_LOCAL_FLOW', 'externalMocked': ['CLIENT.analyze only'], 'noImageGen': True,
                  'modelCalls': len(calls), 'frozenImagesGroupsSource': True, 'actualSignature': '8BPS', 'nativeText': leaves['文案'].text,
                  'nativeImageGeometryAndPixelsPreserved': True, 'nativeTextHasNoHorizontalStretch': True,
                  'nativeImageMaskEffectAndGroupRecordsUnchanged': True, 'qaOnlyModifiedUILayers': True,
                  'oldLegacyPurpleStrokeRemoved': True, 'oldNativeShadowDisabledButEditable': True, 'refinementStatus': result['recognition']['refinementStatus'],
                  'psdSHA256': sha, 'downloadSameSHA': True, 'temporaryCleanup': True, 'reviewStatus': 'NEEDS_REVIEW',
                  'limits': ['Controlled model responses prove the local pipeline, not a paid real artwork refinement.']}
        (report_dir / '后台受控精修复验.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')

    @unittest.skipUnless(os.environ.get('SHIJIE_NATIVE_TEST') == '1', 'actual local failure cleanup is opt-in')
    def test_real_export_then_model_failure_cancel_and_qa_fallback_cleanup(self):
        from codex_client import CLIENT
        from session_outputs import SESSIONS
        counts, workspace_paths = {}, []
        before_count = SESSIONS.count()
        original = copy.deepcopy(self.scene)
        for mode in ('patch-error', 'cancel-after-patch', 'qa-error', 'qa-empty'):
            event = threading.Event()
            counts[mode] = 0
            def analyze(prompt, images, schema, cancelled, **kwargs):
                counts[mode] += 1
                workspace_paths.append(next(Path(p).parents[3] for p in images if Path(p).name == '合成预览.png'))
                if 'patches' in schema['properties']:
                    if mode == 'patch-error':
                        raise RuntimeError('受控模型中断')
                    if mode == 'cancel-after-patch':
                        event.set()
                    return {'patches': [{'id': 'text', 'changes': {'text': '受控校正'}}], 'notes': []}
                if mode == 'qa-empty':
                    return {'status': 'PASS', 'summary': '', 'issues': []}
                raise RuntimeError('受控 QA 中断')
            with patch.object(CLIENT, 'analyze', side_effect=analyze), patch.object(CLIENT, 'generate', side_effect=AssertionError('ImageGen forbidden')) as gen:
                if mode in ('qa-error', 'qa-empty'):
                    result = self.refine.process(self.source, '精修异常清理', lambda *_: None, event.is_set, resume_scene=self.scene)
                    stored = SESSIONS.take(result['_sessionId'])
                    self.assertEqual(stored['psd'][:4], b'8BPS')
                    self.assertEqual(result['recognition']['refinementStatus'], 'NEEDS_REVIEW')
                    self.assertEqual(stored['audit']['visualStatus'], 'NEEDS_REVIEW')
                else:
                    with self.assertRaises(InterruptedError if mode == 'cancel-after-patch' else RuntimeError):
                        self.refine.process(self.source, '精修异常清理', lambda *_: None, event.is_set, resume_scene=self.scene)
                gen.assert_not_called()
            self.assertEqual(self.scene, original)
            self.assertEqual(SESSIONS.count(), before_count)
        self.assertEqual(counts, {'patch-error': 1, 'cancel-after-patch': 1, 'qa-error': 2, 'qa-empty': 2})
        self.assertTrue(all(not p.exists() for p in workspace_paths))


if __name__ == '__main__':
    unittest.main()
