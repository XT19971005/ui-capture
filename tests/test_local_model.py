import json
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TransactionTestCase, override_settings
from shijie.accounts.models import User
from shijie.pipeline.models import Job
from shijie.pipeline.storage import job_root
from .test_service import png
from PIL import Image


class LocalModel(TransactionTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.queue = self.root / 'model'
        self.queue.mkdir()
        self.override = override_settings(DATA_ROOT=self.root / 'data', LOCAL_MODEL_ROOT=self.queue, MIN_FREE=1)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user(username='local', email='local@example.test')
        self.user.groups.add(Group.objects.get_or_create(name='使用者')[0])
        self.client.force_login(self.user)

    def ready(self, age=0):
        (self.queue / 'status.json').write_text(json.dumps({'heartbeat': time.time() - age, 'ready': True, 'busy': False}))

    def submit(self, **extra):
        return self.client.post('/api/engine/jobs', {'image': png(), 'mode': 'local-layered', **extra}, content_type='application/json')

    def test_explicit_local_split_does_not_require_or_call_cloud(self):
        self.ready()
        with patch('shijie.pipeline.ai.status', side_effect=AssertionError('no cloud')):
            response = self.submit()
        self.assertEqual(response.status_code, 202, response.content)
        job = Job.objects.get()
        self.assertEqual(json.loads((job_root(job) / 'connection.json').read_text()), {'provider':'local','analysisProvider':'local','imageProvider':'codex','needsCodex':False,'codexModel':self.user.codex_model})

    def test_stopped_native_worker_rejects_before_creating_job(self):
        self.ready(age=60)
        response = self.submit()
        self.assertEqual(response.status_code, 503, response.content)
        self.assertIn('本机', response.json()['error'])
        self.assertFalse(Job.objects.exists())

    def test_running_service_reports_incomplete_model_download(self):
        (self.queue / 'status.json').write_text(json.dumps({'heartbeat': time.time(), 'ready': False, 'busy': False}))
        response = self.client.get('/api/engine/local-model/status')
        self.assertFalse(response.json()['ready'])
        self.assertIn('模型文件尚未齐全', response.json()['message'])

    def test_local_split_cannot_discard_partial_cloud_work(self):
        self.ready()
        resume = {'format': 'shijie-scene', 'version': 2, 'width': 4, 'height': 3,
                  'nodes': [], 'recognition': {'extractionStatus': 'INCOMPLETE'}}
        response = self.submit(resume=resume)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Job.objects.exists())

    def test_transparent_layers_survive_real_job_runner_and_keep_original(self):
        from shijie.pipeline.worker import claim, run
        from shijie.pipeline.storage import read_scene
        self.ready()
        self.assertEqual(self.submit().status_code, 202)
        errors = []
        def model():
            try:
                for _ in range(100):
                    requests = list(self.queue.glob('jobs/*/request.json'))
                    if requests:
                        folder = requests[0].parent
                        Image.new('RGBA', (4, 3), 'white').save(folder / 'layer_0.png')
                        layer = Image.new('RGBA', (4, 3), (0, 0, 0, 0))
                        layer.putpixel((1, 1), (255, 0, 0, 255))
                        layer.save(folder / 'layer_1.png')
                        from shijie.pipeline.storage import write_json
                        write_json(folder / 'result.json', {'layers': ['layer_0.png', 'layer_1.png']})
                        return
                    time.sleep(.1)
                raise AssertionError('native request never arrived')
            except Exception as exc:
                errors.append(exc)
        producer = threading.Thread(target=model)
        producer.start()
        progress_path = job_root(Job.objects.get()) / 'progress.json'
        read_text, interrupted = Path.read_text, []
        def transient_read(path, *args, **kwargs):
            if path == progress_path and not interrupted:
                interrupted.append(True)
                raise FileNotFoundError(path)
            return read_text(path, *args, **kwargs)
        with patch.object(Path, 'read_text', transient_read):
            run(claim())
        producer.join(timeout=12)
        self.assertTrue(interrupted, 'the transient progress-file read must be exercised')
        self.assertFalse(errors, errors)
        job = Job.objects.get()
        self.assertEqual(job.status, 'completed', job.message)
        scene = read_scene(job_root(job) / 'result.json')
        self.assertEqual(scene['source'], png())
        self.assertEqual(scene['originalSource'], png())
        self.assertEqual(len(scene['nodes']), 2)
        self.assertEqual(scene['recognition']['reviewStatus'], 'NOT_REVIEWED')
        self.assertTrue(scene['recognition']['rasterOnly'])
        self.assertEqual(len(scene['recognition']['warnings']), 2)
        self.assertIn('文字仍为图片', scene['recognition']['reviewSummary'])

    def test_result_rejects_opaque_outputs_and_external_paths(self):
        from shijie.pipeline.local_model import scene_from_result, LocalModelError
        value = {'source': png(), 'original': png(), 'title': 'original'}
        for name in ('layer_0.png', 'layer_1.png'):
            Image.new('RGBA', (4, 3), 'white').save(self.queue / name)
        with self.assertRaises(LocalModelError):
            scene_from_result(self.queue, value, {'layers': ['layer_0.png', 'layer_1.png']})
        with self.assertRaises(LocalModelError):
            scene_from_result(self.queue, value, {'layers': ['../private.png', 'layer_1.png']})
        (self.queue / 'layer_1.png').unlink()
        (self.queue / 'layer_1.png').symlink_to(self.queue / 'layer_0.png')
        with self.assertRaises(LocalModelError):
            scene_from_result(self.queue, value, {'layers': ['layer_0.png', 'layer_1.png']})

    def test_native_request_limits_before_loading_model(self):
        from tools.local_model import validate_request
        valid = {'layers': 3, 'steps': 20, 'resolution': 640, 'seed': 42}
        self.assertEqual(validate_request(valid), valid)
        for change in ({'layers': 100}, {'layers': True}, {'steps': 0}, {'resolution': 8192}, {'seed': -1}, {'path': '/private'}):
            with self.assertRaises(ValueError):
                validate_request({**valid, **change})

    def test_cancelled_bridge_notifies_native_worker(self):
        from shijie.pipeline.local_model import process
        self.ready()
        with self.assertRaises(InterruptedError):
            process({'source': png()}, self.queue, lambda *args: None, lambda: True)
        self.assertEqual(len(list(self.queue.glob('jobs/*/cancel'))), 1)

    def test_transient_heartbeat_read_does_not_abort_inference(self):
        from shijie.pipeline.local_model import process
        def complete(_):
            folder = next(self.queue.glob('jobs/*/request.json')).parent
            Image.new('RGBA', (4, 3), 'white').save(folder / 'layer_0.png')
            layer = Image.new('RGBA', (4, 3), (0, 0, 0, 0))
            layer.putpixel((1, 1), (255, 0, 0, 255))
            layer.save(folder / 'layer_1.png')
            (folder / 'result.json').write_text(json.dumps({'layers': ['layer_0.png', 'layer_1.png']}))
        with patch('shijie.pipeline.local_model.status', side_effect=[{'ready': True}, {'ready': False}]), patch('shijie.pipeline.local_model.time.sleep', complete):
            scene = process({'source': png(), 'original': png(), 'title': 'test'}, self.queue, lambda *args: None, lambda: False)
        self.assertEqual(len(scene['nodes']), 2)
        self.assertFalse(list(self.queue.glob('jobs/*/cancel')))
