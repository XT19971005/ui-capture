import json
import time
import unittest
from . import test_release as fixtures


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.host = fixtures.ReleaseTest(); self.host.setUp(); self.addCleanup(self.host.doCleanups)
        from shijie_ops.runtime import Operations
        self.ops = Operations(self.host.config, self.host.root / 'ops', env=self.host.env)
        self.addCleanup(self.ops.close)

    def finish(self, job):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            row = self.ops.dispatch('admin@example.invalid', 'get_job', {'job_id':job['id']})
            if row['status'] not in ('queued', 'running'): return row
            time.sleep(.02)
        self.fail('operation timed out')

    def test_retry_persists_one_job_and_survives_client_disconnect(self):
        sha=self.host.commit('new'); params={'commit':sha,'request_id':'release-one'}
        first=self.ops.dispatch('admin@example.invalid','deploy',params)
        retries=[self.ops.dispatch('admin@example.invalid','deploy',params) for _ in range(5)]
        self.assertEqual({row['id'] for row in retries},{first['id']})
        self.assertEqual(self.finish(first)['status'],'succeeded')
        with self.assertRaises(ValueError):self.ops.dispatch('admin@example.invalid','deploy',{**params,'commit':'0'*40})
        self.assertEqual(self.ops.dispatch('admin@example.invalid','get_project_status',{})['active']['commit'],sha)

    def test_failed_task_records_pending_and_redacts_service_credentials(self):
        sha=self.host.commit('bad'); self.ops.env['FAIL_ON']='migrate'
        first=self.ops.dispatch('admin@example.invalid','deploy',{'commit':sha,'request_id':'broken'})
        self.assertEqual(self.finish(first)['status'],'failed')
        self.assertEqual(self.ops.dispatch('admin@example.invalid','diagnose',{})['pending']['commit'],sha)
        logs=self.ops.dispatch('admin@example.invalid','get_logs',{'service':'web'})
        self.assertNotIn('hidden-synthetic-token',logs['text']); self.assertIn('[REDACTED]',logs['text'])
        self.ops.env.pop('FAIL_ON')
        resumed=self.ops.dispatch('admin@example.invalid','resume_deployment',{'pending_commit':sha,'request_id':'resume'})
        self.assertEqual(self.finish(resumed)['status'],'succeeded')

    def test_allowlisted_controls_and_input_validation_have_no_side_effects(self):
        for action,params in [('shell',{}),('deploy',{'commit':'--help','request_id':'bad'}),
                              ('get_logs',{'service':'../config.toml'}),('get_job',{'job_id':'../db'}),
                              ('control_service',{'operation':'down','service':'db','request_id':'bad'})]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.ops.dispatch('admin@example.invalid',action,params)
        self.assertIsNone(self.ops.snapshot()['latest_job'])
        task=self.ops.dispatch('admin@example.invalid','control_service',{'operation':'restart','service':'web','request_id':'restart-one'})
        self.assertEqual(self.finish(task)['status'],'succeeded')

    def test_redaction_fails_closed_when_private_config_is_missing(self):
        from shijie_ops.runtime import Redactor
        redact=Redactor(self.host.config)
        self.assertNotIn('synthetic-secret-value',redact('synthetic-secret-value'))
        self.assertNotIn('private-code',redact('GET /callback?code=private-code&state=private-state'))
        (self.host.config/'config.toml').unlink()
        self.assertNotIn('untrusted raw log',Redactor(self.host.config)('untrusted raw log'))
