import os,unittest
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from shijie_ops.install import issue_token


@unittest.skipIf(os.name=='nt', 'Linux deployment lifecycle requires Linux host')
class CredentialTest(unittest.TestCase):
    def test_private_token_rotation_and_revocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=issue_token(root,'admin@example.invalid')
            first=path.read_text().strip()
            record=json.loads((root/'operators.json').read_text())['admin@example.invalid']
            self.assertEqual(record['sha256'],hashlib.sha256(first.encode()).hexdigest())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            issue_token(root,'admin@example.invalid','read')
            self.assertNotEqual(first,path.read_text().strip())
            record=json.loads((root/'operators.json').read_text())['admin@example.invalid']
            self.assertEqual(record['role'],'read'); self.assertNotEqual(record['sha256'],hashlib.sha256(first.encode()).hexdigest())
            issue_token(root,'admin@example.invalid',revoke=True)
            self.assertEqual(json.loads((root/'operators.json').read_text()),{}); self.assertFalse(path.exists())
            with self.assertRaises(ValueError):issue_token(root,'../../outside')
