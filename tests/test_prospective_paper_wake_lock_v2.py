from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest
import json
from hashlib import sha256
from unittest.mock import patch
from core.strategy_account_ledger import canonical
from scripts.run_prospective_paper_diagnosed_v2 import exclusive_wake,run,SOURCE


class WakeLockTests(unittest.TestCase):
    def test_wrapper_pins_and_diagnostics_with_runtime_boundary(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            descriptor=canonical(dict(account_id='paper-current:test-wrapper',code_sha256={
                SOURCE:sha256(Path(SOURCE).read_bytes()).hexdigest()}))
            (root/'descriptor.json').write_bytes(descriptor)
            config=canonical(dict(descriptor=dict(path='descriptor.json',sha256=sha256(descriptor).hexdigest())))
            (root/'config.json').write_bytes(config)
            args=dict(root=root,configuration_path='config.json',expected_sha256=sha256(config).hexdigest())
            with patch('scripts.run_prospective_paper_diagnosed_v2.run_scheduled',return_value={
                    'status':'WAIT_REGISTERED_START','account_writes':False}) as runtime:
                self.assertEqual(run(**args)['status'],'WAIT_REGISTERED_START')
                runtime.assert_called_once()
            with patch('scripts.run_prospective_paper_diagnosed_v2.run_scheduled',side_effect=ValueError('PAPER_TEST_FAILURE')):
                self.assertEqual(run(**args)['reason'],'PAPER_TEST_FAILURE')
            receipts=[json.loads(p.read_bytes()) for p in (root/'data/local_scheduler').rglob('*.json')]
            self.assertEqual(len(receipts),2)
            self.assertEqual({r['result']['status'] for r in receipts},{'WAIT_REGISTERED_START','BLOCKED'})
            with self.assertRaisesRegex(ValueError,'PAPER_WAKE_SOURCE_CHANGED'):
                run(**dict(args,expected_sha256='0'*64))
            self.assertFalse(list(root.rglob('*.sqlite3')))

    def child(self,path):
        script="from scripts.run_prospective_paper_diagnosed_v2 import exclusive_wake\nimport sys\nwith exclusive_wake(sys.argv[1]) as owned: print(owned,flush=True)"
        return subprocess.run([sys.executable,'-B','-c',script,str(path)],capture_output=True,text=True,timeout=15,check=True).stdout.strip()

    def test_actual_process_exclusion_and_persistent_file_is_not_busy(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'wake.lock'
            with exclusive_wake(path) as owned:
                self.assertTrue(owned);self.assertEqual(self.child(path),'False')
            self.assertTrue(path.exists());self.assertEqual(self.child(path),'True')

    def test_process_termination_releases_lock(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'wake.lock'
            script="from scripts.run_prospective_paper_diagnosed_v2 import exclusive_wake\nimport sys,time\nwith exclusive_wake(sys.argv[1]) as owned:\n print(owned,flush=True)\n time.sleep(30)"
            process=subprocess.Popen([sys.executable,'-B','-c',script,str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(),'True')
                with exclusive_wake(path) as owned:self.assertFalse(owned)
            finally:
                process.terminate();process.communicate(timeout=10)
            with exclusive_wake(path) as owned:self.assertTrue(owned)


if __name__=='__main__':unittest.main()
