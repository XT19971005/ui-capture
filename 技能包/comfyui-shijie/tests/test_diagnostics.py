import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagnostics import path_failure_context

class PathDiagnosticsTests(unittest.TestCase):
    def test_path_failure_includes_callsite_without_private_arguments(self):
        @path_failure_context
        def read_config(secret):
            return Path(None)
        with self.assertRaisesRegex(RuntimeError,r'test_diagnostics.py:\d+:read_config') as caught:
            read_config('private-input-do-not-print')
        self.assertNotIn('private-input-do-not-print',str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__,TypeError)

    def test_other_errors_and_success_are_unchanged(self):
        @path_failure_context
        def value(x):
            if x is None:raise ValueError('invalid advice')
            return x
        self.assertEqual(value(3),3)
        with self.assertRaises(ValueError):value(None)
