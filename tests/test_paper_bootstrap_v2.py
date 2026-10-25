from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backtest.current_strategy_paper_bootstrap_v2 import initialize_registered_paper,SOURCE
from data.strategy_paper_execution_preview_v1 import _local_import_closure
from prospective_paper_v2_fixture import fixture


class BootstrapTests(unittest.TestCase):
    def test_initialize_once_and_preserve_state(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder,extra_code_paths=_local_import_closure({SOURCE}))
            args=dict(root=folder,authority=daily['authority'],clock=lambda:datetime.fromisoformat('2026-11-03T15:00:00+00:00'))
            first=initialize_registered_paper(**args)
            self.assertEqual((first['status'],first['cash']),('INITIALIZED','20000'))
            self.assertEqual(initialize_registered_paper(**args)['status'],'ALREADY_INITIALIZED')

    def test_before_window_does_not_create_account(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder,extra_code_paths=_local_import_closure({SOURCE}))
            with self.assertRaisesRegex(ValueError,'OUTSIDE_FIRST_WINDOW'):
                initialize_registered_paper(root=folder,authority=daily['authority'],
                    clock=lambda:datetime.fromisoformat('2026-11-03T14:59:30+00:00'))
            self.assertFalse((Path(folder)/'data/current_strategy_paper').exists())

    def test_interruption_preserves_evidence_and_blocks_retry(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder,extra_code_paths=_local_import_closure({SOURCE}))
            args=dict(root=folder,authority=daily['authority'],clock=lambda:datetime.fromisoformat('2026-11-03T15:00:00+00:00'))
            def fail(phase):raise RuntimeError('synthetic interruption')
            with self.assertRaisesRegex(RuntimeError,'synthetic interruption'):
                initialize_registered_paper(**args,fault=fail)
            self.assertEqual(len(list(Path(folder).rglob('bootstrap.failed.json'))),1)
            with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'):
                initialize_registered_paper(**args)


if __name__=='__main__':unittest.main()
