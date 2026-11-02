import io, unittest
from pathlib import Path
from unittest.mock import Mock, patch
import codex_client as codex

class CodexTemporaryTests(unittest.TestCase):
 def start_fixture(self):
  client=codex.CodexClient();client.selected_model='existing-selection'
  process=Mock();process.poll.return_value=None;process.stdin=io.StringIO()
  with patch.object(codex,'command',return_value=['codex.exe']), patch.object(codex.subprocess,'Popen',return_value=process) as launch, patch.object(codex.threading,'Thread'), patch.object(client,'call',return_value={}):
   client.start()
  return client,process,launch.call_args.kwargs
 def test_runtime_artifacts_have_owned_directory_and_are_removed_on_close(self):
  client,process,options=self.start_fixture()
  directory=Path(options['env']['TEMP'])
  self.assertNotEqual(directory.resolve(),codex.ROOT.joinpath('依赖/运行临时').resolve())
  self.assertEqual(options['env']['TMP'],str(directory));self.assertEqual(options['env']['TMPDIR'],str(directory))
  self.assertEqual(Path(options['cwd']),codex.ROOT)
  (directory/'worker-compiled.tmp').write_bytes(b'generated runtime script')
  self.assertTrue(client.close());self.assertFalse(directory.exists())
  self.assertEqual(client.selected_model,'existing-selection');process.stdin.close()
 def test_close_does_not_interrupt_another_pending_call(self):
  client,process,options=self.start_fixture();directory=Path(options['env']['TEMP'])
  client.pending[100]=object()
  self.assertFalse(client.close());self.assertTrue(directory.exists());process.wait.assert_not_called()
  client.pending.clear();self.assertTrue(client.close());self.assertFalse(directory.exists())

if __name__=='__main__':unittest.main()
