from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data.current_quantity_v2_pullback_cap_store import PullbackCapStore
from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
from test_current_quantity_v2_pullback_cap_store import arguments


class LazyPullbackRuntimeTests(unittest.TestCase):
    def test_construction_no_io_first_explicit_candidate_creates_only_temp_store(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'new-research-directory'/'caps.sqlite3'
            with (patch('pathlib.Path.mkdir', side_effect=AssertionError('constructor mkdir')),
                  patch('sqlite3.connect', side_effect=AssertionError('constructor sqlite'))):
                store = LazyPullbackCapStore(path, clock=lambda:'2026-10-15T09:32:30-04:00',
                    max_history_rows=100,max_history_bytes=1000000)
            self.assertFalse(path.parent.exists())
            with patch('data.current_quantity_v2_pullback_runtime.PullbackCapStore',
                       wraps=PullbackCapStore) as factory:
                first = store.candidate(**arguments())
                second = store.candidate(**arguments(1,1450))
                self.assertEqual(factory.call_count,1)
            self.assertTrue(path.is_file())
            self.assertEqual(first['candidate']['limit_price'],second['candidate']['limit_price'])
            self.assertFalse(second['cap_store_receipt']['production_enabled'])


if __name__=='__main__':
    unittest.main()
