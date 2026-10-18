from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from scripts import ndx_cash_topup_neighbor_preparation_20261003 as w
from backtest import ndx_cash_topup_neighbor_preparation_research as core
from test_ndx_cash_topup_neighbor_preparation_research import fixture
class Tests(unittest.TestCase):
    def test_stream_shards_and_full_counts(self):
        p=core.prepare_scenario(**fixture())
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'SHARD_SIZE',2):
            row=w.write_scenario(p,core,Path(tmp)/'scenario');tasks=[]
            for shard in row['shards']:
                b=Path(shard['path']).read_bytes();self.assertEqual(w.sha(b),shard['sha256']);tasks.extend(json.loads(x) for x in b.splitlines());self.assertLessEqual(shard['stop']-shard['start'],2)
            self.assertEqual(len(tasks),row['statistics']['new_candidate_count']);self.assertEqual(row['old_feasible_seed_count'],2);self.assertEqual(row['statistics']['unprocessed_move_count'],0)
    def test_namespace_rejects_before_loading(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'OUTPUT',Path(tmp)),patch.object(w,'load') as load:
            with self.assertRaises(ValueError):w.run(execute=True)
            load.assert_not_called()
    def test_failure_marker_kept(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'OUTPUT',Path(tmp)/'new'),patch.object(w,'load',return_value=({}, {}, {}, [(0,{})],core)),patch.object(w,'guard'):
            with self.assertRaises(KeyError):w.run(execute=True)
            self.assertTrue((w.OUTPUT/'started.json').exists());self.assertTrue((w.OUTPUT/'failure.json').exists())
if __name__=='__main__':unittest.main()
