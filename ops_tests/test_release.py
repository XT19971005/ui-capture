"""Real Git and a process-level Docker substitute; no production resources."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shijie-ops-', dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'repo'; self.repo.mkdir()
        self.config = self.root / 'config'; self.config.mkdir()
        self.data = self.root / 'data'; self.data.mkdir()
        (self.data / 'asset.txt').write_text('must survive failures')
        self.bin = self.root / 'bin'; self.bin.mkdir()
        self.calls = self.root / 'calls.jsonl'
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'], 'CALL_LOG': str(self.calls)}
        script = self.bin / 'docker'
        script.write_text('''#!/usr/bin/env python3
import json,os,sys,time
a=sys.argv[1:]
with open(os.environ['CALL_LOG'],'a') as f:f.write(json.dumps(a)+'\\n')
if os.environ.get('FAIL_ON') in a:sys.exit(1)
if os.environ.get('WAIT_FOR') and 'build' in a:
 while not os.path.exists(os.environ['WAIT_FOR']):time.sleep(.02)
if a[:2]==['ps','-q']:
 print('f'*64)
elif a[:2]==['exec','-i'] and 'psql' in a:
 email=next(s[6:] for s in a if s.startswith('email='))
 print('t' if json.load(open(os.environ['IDENTITIES'])).get(email) else 'f')
elif 'pg_dump' in a:print('-- synthetic consistent database')
elif 'psql' in a:print(os.environ.get('JOB_COUNT','0') if 'pipeline_job' in ' '.join(a) else '0')
elif a[:2]==['image','inspect']:print(json.dumps([{'Id':'sha256:'+'a'*64}]))
elif 'ps' in a and '--format' in a:print('[]')
elif 'ps' in a:print(os.environ.get('RUNNING_SERVICES','web\\nworker'))
elif 'logs' in a:print('authorization: Bearer hidden-synthetic-token')
''')
        script.chmod(0o755)
        (self.config / 'config.toml').write_text('[site]\nsecret_key="synthetic-secret-value"\n[database]\nurl="postgresql://shijie:synthetic-password@db/shijie"\n[deployment]\ndata_dir='+json.dumps(str(self.data))+'\n')
        (self.config / 'postgres-password').write_text('synthetic-password')
        self.git('init', '-b', 'main'); self.git('config','user.name','Fixture'); self.git('config','user.email','test@example.invalid')
        (self.repo / 'deploy').mkdir(); (self.repo / 'deploy/compose.yml').write_text('name: shijie\nservices: {}\n')
        (self.repo / 'shijie/accounts/migrations').mkdir(parents=True)
        (self.repo / 'shijie/accounts/migrations/0001.py').write_text('original migration')
        self.initial = self.commit('initial')
        self.origin = self.root / 'origin.git'
        subprocess.run(['git','clone','--bare',str(self.repo),str(self.origin)],check=True,capture_output=True)
        self.git('remote','add','origin',str(self.origin))
        (self.config / 'operations.json').write_text(json.dumps({'repository':str(self.repo),'remote_url':str(self.origin),'backup_dir':str(self.root/'backups')}))
        (self.config / 'deployment.json').write_text(json.dumps({'commit':self.initial,'release':str(self.repo),'image':'shijie:initial','phase':'ready'}))

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.repo),*args],stderr=subprocess.PIPE,text=True).strip()

    def commit(self,text):
        (self.repo / 'version.txt').write_text(text)
        self.git('add','.'); self.git('commit','-m',text)
        sha=self.git('rev-parse','HEAD')
        if hasattr(self,'origin'):self.git('push','origin','main')
        return sha

    def controller(self):
        from shijie_ops.release import Controller
        return Controller(self.config, env=self.env)

    def test_exact_commit_build_before_backup_and_preserve_source_checkout(self):
        requested=self.commit('requested'); self.commit('later')
        self.controller().perform('deploy',{'commit':requested})
        active=json.loads((self.config/'deployment.json').read_text())
        self.assertEqual(active['commit'],requested)
        self.assertEqual((Path(active['release'])/'version.txt').read_text(),'requested')
        self.assertEqual((self.repo/'version.txt').read_text(),'later')
        calls=[json.loads(s) for s in self.calls.read_text().splitlines()]
        self.assertLess(next(i for i,a in enumerate(calls) if 'build' in a),next(i for i,a in enumerate(calls) if 'stop' in a))
        self.assertTrue((Path(active['backup'])/'COMPLETE').is_file())
        self.assertFalse((self.config/'pending.json').exists())

    def test_build_failure_keeps_running_version_and_creates_no_pending(self):
        target=self.commit('broken-build'); self.env['FAIL_ON']='build'
        with self.assertRaises(subprocess.CalledProcessError):self.controller().perform('deploy',{'commit':target})
        self.assertFalse((self.config/'pending.json').exists())
        self.assertEqual(json.loads((self.config/'deployment.json').read_text())['commit'],self.initial)
        self.assertFalse(any('stop' in json.loads(s) for s in self.calls.read_text().splitlines()))

    def test_failed_migration_can_resume_or_use_successor_without_replacing_backup(self):
        broken=self.commit('broken-migration'); self.env['FAIL_ON']='migrate'
        with self.assertRaises(subprocess.CalledProcessError):self.controller().perform('deploy',{'commit':broken})
        pending=json.loads((self.config/'pending.json').read_text()); backup=Path(pending['backup'])
        before=(backup/'COMPLETE').read_bytes()
        fixed=self.commit('fixed'); self.env.pop('FAIL_ON')
        self.controller().perform('repair_deployment',{'commit':fixed,'pending_commit':broken})
        active=json.loads((self.config/'deployment.json').read_text())
        self.assertEqual(active['commit'],fixed); self.assertEqual(active['backup'],str(backup))
        self.assertEqual((backup/'COMPLETE').read_bytes(),before)

    def test_reject_bad_version_dirty_checkout_and_existing_migration_edits(self):
        ctl=self.controller()
        with self.assertRaises(ValueError):ctl.perform('deploy',{'commit':';id'})
        target=self.commit('target'); (self.repo/'version.txt').write_text('dirty')
        with self.assertRaises(ValueError):ctl.perform('deploy',{'commit':target})
        self.git('restore','version.txt'); self.env['FAIL_ON']='migrate'
        with self.assertRaises(subprocess.CalledProcessError):self.controller().perform('deploy',{'commit':target})
        (self.repo/'shijie/accounts/migrations/0001.py').write_text('edited migration'); fixed=self.commit('bad repair')
        self.env.pop('FAIL_ON')
        with self.assertRaisesRegex(ValueError,'迁移'):ctl.perform('repair_deployment',{'commit':fixed,'pending_commit':target})
        with self.assertRaises(ValueError):ctl.perform('resume_deployment',{'pending_commit':'0'*40})
        ctl.perform('resume_deployment',{'pending_commit':target})
        with self.assertRaises(ValueError):ctl.perform('deploy',{'commit':self.initial})

    def test_running_ai_job_and_concurrent_maintenance_block_writes(self):
        from shijie_ops.release import maintenance_lock
        target=self.commit('target')
        self.env['JOB_COUNT']='1'
        with self.assertRaisesRegex(ValueError,'拆图任务'):self.controller().perform('deploy',{'commit':target})
        self.assertFalse(any('stop' in json.loads(s) for s in self.calls.read_text().splitlines()))
        self.env.pop('JOB_COUNT')
        with maintenance_lock(self.config), self.assertRaisesRegex(ValueError,'维护操作'):
            self.controller().perform('control_service',{'operation':'restart','service':'all'})

    def test_backup_failure_never_marks_complete_or_restarts_writers(self):
        self.env['FAIL_ON']='pg_dump'
        with self.assertRaises(subprocess.CalledProcessError):self.controller().perform('backup',{})
        self.assertEqual(list((self.root/'backups').rglob('COMPLETE')),[])
        calls=[json.loads(s) for s in self.calls.read_text().splitlines()]
        self.assertTrue(any('stop' in a for a in calls)); self.assertFalse(any('start' in a or 'up' in a for a in calls))

    def test_backup_restores_only_previously_running_service_and_digest_matches(self):
        from shijie_ops.release import check_backup
        self.env['RUNNING_SERVICES']='web'
        self.controller().perform('backup',{})
        complete=list((self.root/'backups').rglob('COMPLETE'))
        self.assertEqual(len(complete),1); check_backup(complete[0].parent)
        calls=[json.loads(s) for s in self.calls.read_text().splitlines()]
        self.assertEqual(calls[-1][-4:],['up','-d','--wait','web'])
        (complete[0].parent/'database.sql').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'备份校验'):check_backup(complete[0].parent)

    def test_restart_one_service_does_not_start_another_service(self):
        self.controller().perform('control_service',{'operation':'restart','service':'web'})
        calls=[json.loads(s) for s in self.calls.read_text().splitlines()]
        writes=[a for a in calls if 'restart' in a or 'up' in a]
        self.assertEqual(len(writes),2); self.assertTrue(all('worker' not in a for a in writes))

    def test_start_worker_can_drain_jobs_queued_while_it_was_stopped(self):
        self.env['JOB_COUNT']='2'
        self.controller().perform('control_service',{'operation':'start','service':'worker'})
        calls=[json.loads(s) for s in self.calls.read_text().splitlines()]
        self.assertIn(['up','-d','--wait','worker'],[a[-4:] for a in calls])
        self.assertFalse(any('stop' in a or 'restart' in a for a in calls))
