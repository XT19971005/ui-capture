import ast
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch
from django.conf import settings
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from shijie.accounts.models import User
from shijie.pipeline.models import Job
from shijie.pipeline.storage import job_root, user_root, write_json


class WorkerReceipt(TransactionTestCase):
    def test_failure_diagnostics_include_only_safe_receipt_fields(self):
        from shijie.pipeline.views import job_data
        with tempfile.TemporaryDirectory() as folder, override_settings(DATA_ROOT=Path(folder)):
            user = User.objects.create_user(username='diagnostic-test')
            job = Job.objects.create(owner=user, mode='assistant-plan', status='failed')
            root = job_root(job)
            write_json(root/'finished.json', {'status':'failed','elapsedSeconds':421.2,'message':'private text'})
            write_json(root/'failure.json', {'exception':'_TygptError','stage':'process','frames':[{'file':'private-path'}]})
            value = job_data(job, include_result=True)
            self.assertEqual(value['diagnostic'], {'status':'failed','elapsedSeconds':421.2,'exception':'_TygptError','stage':'process'})
            self.assertNotIn('private', json.dumps(value))

    def test_real_job_update_accepts_runner_timing_metadata(self):
        # Execute the production coordinator function without importing Linux fcntl.
        source = Path(settings.BASE_DIR, 'shijie/pipeline/worker.py').read_text(encoding='utf8')
        function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        process = Mock(); process.poll.return_value = 0
        scope = dict(__package__='shijie.pipeline', job_root=job_root, user_root=user_root,
                     json=json, time=time, timezone=timezone, settings=settings, Job=Job,
                     start=Mock(return_value=process), stop=Mock(), allowed=lambda user: True,
                     write_json=write_json)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<production-worker>', 'exec'), scope)
        with tempfile.TemporaryDirectory() as folder, override_settings(DATA_ROOT=Path(folder)):
            user = User.objects.create_user(username='receipt-test')
            for status in ('completed', 'failed'):
                job = Job.objects.create(owner=user, mode='assistant-plan', status='running')
                root = job_root(job)
                write_json(root/'connection.json', {'provider':'tygpt', 'needsCodex':False})
                write_json(root/'finished.json', {'status':status, 'message':'original outcome', 'elapsedSeconds':12.5})
                with patch('shijie.pipeline.providers.job_credentials', return_value={'needsCodex':False}):
                    scope['run'](job)
                job.refresh_from_db()
                self.assertEqual(job.status, status)
                self.assertEqual(job.message, 'original outcome')
                self.assertIsNotNone(job.finished_at)
                self.assertEqual(json.loads((root/'finished.json').read_text())['elapsedSeconds'], 12.5)
