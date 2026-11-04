import contextlib
import io
from pathlib import Path
import runpy
import tempfile
import tomllib
from unittest.mock import patch
from django.test import SimpleTestCase


class Controller(SimpleTestCase):
    def test_runtime_checks_use_an_isolated_stack_and_remove_only_that_stack(self):
        controller = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'shijiectl'))
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            folder, data = root / 'config', root / 'data'
            controller['configuration'](folder, 'http://service.example.test/shijie', data_dir=data)
            original = (folder / 'config.toml').read_bytes()
            calls = []

            def run(args, **kwargs):
                env = kwargs['env']
                config = tomllib.loads(Path(env['SHIJIE_CONFIG_FILE']).read_text())
                calls.append((args, dict(env), config))
                if 'manage.py' in args:
                    raise RuntimeError('simulated test failure')

            with patch('sys.argv', ['shijiectl', 'test', '--config-dir', str(folder)]), patch('subprocess.run', run):
                with self.assertRaisesRegex(RuntimeError, 'simulated test failure'):
                    controller['main']()
            for args, env, config in calls:
                self.assertIn('-p', args)
                self.assertTrue(args[args.index('-p') + 1].startswith('shijie-test-'))
                self.assertNotEqual(Path(env['SHIJIE_CONFIG_FILE']), folder / 'config.toml')
                self.assertNotEqual(Path(env['SHIJIE_DATA_DIR']), data)
                self.assertNotEqual(Path(env['SHIJIE_DB_PASSWORD_FILE']), folder / 'postgres-password')
                self.assertEqual(config['site']['public_url'], 'http://127.0.0.1:8093')
            self.assertEqual(calls[-1][0][-2:], ['down', '--volumes'])
            self.assertFalse(Path(calls[0][1]['SHIJIE_DATA_DIR']).exists())
            self.assertEqual((folder / 'config.toml').read_bytes(), original)

    def test_init_uses_separate_secrets_and_explicit_data_directory(self):
        controller = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'shijiectl'))
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            source = root / 'reference.toml'
            source.write_text('[oidc]\nmode="broker"\nclient_id="do-not-copy"\nclient_secret="do-not-copy"\nlogin_url="https://login.example.test/auth"\n')
            folder, data = root / 'config', root / 'data'
            controller['configuration'](folder, 'http://127.0.0.1:8093', source, data)
            config = tomllib.loads((folder / 'config.toml').read_text())
            self.assertEqual(config['deployment']['data_dir'], str(data.resolve()))
            self.assertEqual(config['oidc']['client_id'], '')
            self.assertEqual(config['oidc']['client_secret'], '')
            self.assertEqual(config['oidc']['login_url'], 'https://login.example.test/auth')
            self.assertGreater(len(config['site']['secret_key']), 50)
            self.assertEqual((folder / 'config.toml').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                controller['configuration'](folder, 'http://127.0.0.1:8093', data_dir=data)
