from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest
from scripts import run_local_scheduled_simulation as module


class LocalTests(unittest.TestCase):
    def setup_root(self,root,stack):
        pins={}
        for path in module.PINS:
            file=root/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'fixture')
            pins[path]=sha256(b'fixture').hexdigest()
        stack.enter_context(patch.object(module,'ROOT',root));stack.enter_context(patch.object(module,'PINS',pins))

    def test_readonly_and_durable_skip_fixed_command(self):
        with TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);self.setup_root(root,stack)
            with patch.object(module.subprocess,'run',side_effect=AssertionError('no child')):
                self.assertEqual(module.run()['status'],'PREFLIGHT_ONLY')
            self.assertFalse((root/module.LOGS).exists())
            def child(command,**kwargs):
                self.assertEqual(kwargs['cwd'],root)
                self.assertIn('--monthly-runtime-directory',command);self.assertEqual(command[-1],'--execute')
                self.assertNotIn('--clock',command)
                kwargs['stdout'].write(b'{"status":"SKIPPED","reason":"OUTSIDE_1000_NEW_YORK"}\n')
                return SimpleNamespace(returncode=0)
            with patch.object(module.subprocess,'run',side_effect=child) as process:
                result=module.run(execute=True)
            self.assertEqual(result['status'],'SKIPPED');self.assertEqual(process.call_count,1)
            runs=[p for p in (root/module.LOGS).iterdir() if p.is_dir()]
            self.assertEqual(len(runs),1);self.assertTrue((runs[0]/'started.json').is_file())
            self.assertEqual(json.loads((runs[0]/'finished.json').read_text())['status'],'SKIPPED')

    def test_pin_drift_and_existing_lock_never_start_child(self):
        with TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);self.setup_root(root,stack)
            (root/module.BOOTSTRAP).write_bytes(b'changed')
            with patch.object(module.subprocess,'run',side_effect=AssertionError('no child')):
                self.assertEqual(module.run(execute=True)['reason'],'PINNED_INPUT_CHANGED')
                lock=root/module.LOGS/'running.lock';lock.write_text('unknown prior process')
                self.assertEqual(module.run(execute=True)['status'],'SKIPPED')
                self.assertEqual(lock.read_text(),'unknown prior process')
            self.assertEqual(len(list((root/module.LOGS).glob('*/finished.json'))),2)

    def test_created_status_and_failure_no_retry(self):
        with TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);self.setup_root(root,stack)
            def child(command,**kwargs):
                kwargs['stdout'].write(b'{"status":"CREATED_ISOLATED_SIMULATION"}\n')
                return SimpleNamespace(returncode=0)
            with patch.object(module.subprocess,'run',side_effect=child):
                self.assertEqual(module.run(execute=True)['status'],'CREATED_ISOLATED_SIMULATION')
            with patch.object(module.subprocess,'run',side_effect=OSError('sensitive text')) as process:
                self.assertEqual(module.run(execute=True)['reason'],'LOCAL_RUN_FAILED')
                self.assertEqual(process.call_count,1)


if __name__=='__main__':unittest.main()
