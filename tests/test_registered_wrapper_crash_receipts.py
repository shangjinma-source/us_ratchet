"""Independent crash-boundary admission checks; no transport or economic run."""
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import test_run_registered_quantity_v2_paper_simulation as fixtures
from scripts import run_registered_quantity_v2_paper_simulation as runner


class CrashReceiptTests(unittest.TestCase):
    def test_all_attempt_phases_reject_partial_receipts_before_dispatch(self):
        for name in ('bootstrap-attempt','daily-2026-10-15','finalize-attempt'):
            for missing in ('started.json','result.json','complete.json','all'):
                with self.subTest(phase=name,missing=missing),TemporaryDirectory() as folder:
                    args,_,now,store,_=fixtures.bundle(folder,True)
                    attempt=Path(folder)/'registration/runtime'/name;attempt.mkdir()
                    if missing!='all':
                        for part in ('started.json','result.json','complete.json'):
                            if part!=missing:(attempt/part).write_text('{}')
                    before=store.path.read_bytes()
                    args['clock']=lambda:now+timedelta(days=1)
                    with patch.object(runner.daily,'run_runtime',side_effect=AssertionError('must not dispatch')),patch.object(runner.terminal,'run',side_effect=AssertionError('must not finalize')):
                        with self.assertRaisesRegex(ValueError,'INCOMPLETE_EXECUTION_ATTEMPT'):
                            runner.run(**args,execute=True)
                    self.assertEqual(before,store.path.read_bytes())
                    self.assertTrue(attempt.exists())
                    self.assertFalse((Path(folder)/runner.registrar.LOCK).exists())

    def test_registration_incomplete_is_not_runtime_authority(self):
        for missing in ('started.json','receipt.json','complete.json','request.json'):
            with self.subTest(missing=missing),TemporaryDirectory() as folder:
                args,request,_,_,_=fixtures.bundle(folder)
                (Path(folder)/'registration'/missing).unlink()
                with self.assertRaises((ValueError,FileNotFoundError)):
                    runner.run(**args,execute=True)
                self.assertFalse(Path(request['identity']['database_path']).exists())
                self.assertFalse((Path(folder)/'registration/runtime').exists())

if __name__=='__main__':unittest.main()
