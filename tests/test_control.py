import contextlib
import io
from pathlib import Path
import runpy
import tempfile
import tomllib
from django.test import SimpleTestCase


class Controller(SimpleTestCase):
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
