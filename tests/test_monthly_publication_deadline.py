"""Publication window checks occur under the account writer reservation."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from test_bind_monthly_simulation_runtime import setup
from scripts.bind_monthly_simulation_runtime import bind, publication_guard

class DeadlineTests(unittest.TestCase):
    def test_elapsed_while_waiting_for_lock_writes_neither_candidate_nor_slot(self):
        with TemporaryDirectory() as folder:
            args,config=setup(folder); before=Path(config['database_path']).read_bytes()
            expired=[False]
            @contextmanager
            def delayed_lock(*values):
                with publication_guard(*values):
                    expired[0]=True
                    yield
            def check():
                if expired[0]: raise ValueError('ROLLING_WINDOW_ELAPSED')
            with patch('scripts.bind_monthly_simulation_runtime.publication_guard',delayed_lock):
                with self.assertRaisesRegex(ValueError,'ROLLING_WINDOW_ELAPSED'):
                    bind(**args,monthly_runtime_directory=str(Path(folder)/'releases'),publication_time_guard=check)
            self.assertFalse(args['output'].exists()); self.assertFalse((Path(folder)/'releases').exists())
            self.assertEqual(Path(config['database_path']).read_bytes(),before)

    def test_deadline_after_candidate_does_not_publish_slot(self):
        with TemporaryDirectory() as folder:
            args,config=setup(folder); before=Path(config['database_path']).read_bytes(); calls=[]
            def check():
                calls.append(1)
                if len(calls)==2: raise ValueError('ROLLING_WINDOW_ELAPSED')
            with self.assertRaisesRegex(ValueError,'ROLLING_WINDOW_ELAPSED'):
                bind(**args,monthly_runtime_directory=str(Path(folder)/'releases'),publication_time_guard=check)
            self.assertEqual(len(calls),2); self.assertTrue(args['output'].exists())
            self.assertFalse((Path(folder)/'releases').exists()); self.assertEqual(Path(config['database_path']).read_bytes(),before)

if __name__=='__main__': unittest.main()
