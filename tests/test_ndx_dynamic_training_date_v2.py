import unittest
import hashlib
import json
from unittest.mock import patch,Mock
from scripts import ndx_dynamic_training_date_v2 as module


class LoadedDateTests(unittest.TestCase):
    def test_import_source_drift_rejected(self):
        key=next(iter(module._LOADED))
        with patch.dict(module._LOADED,{key:'0'*64}):
            with self.assertRaisesRegex(ValueError,'source changed'):
                module.prepare_date_v2(source_batch='x',universe_track='x',selection_date='2024-02-01')

    def test_real_date_binding_and_count(self):
        result=module.prepare_date_v2(source_batch='ndx_cardinality_real_runner_p2_exact_v2',
            universe_track='strict_technology',selection_date='2024-02-01')
        self.assertEqual(len(result['records']),884)
        self.assertTrue(set(module._LOADED)<=set(result['source_hashes']))
        self.assertFalse(result['all_base_candidates_included'])

    def test_empty_delta_not_claimed_empty_universe(self):
        raw=json.dumps(dict(source_hashes={},coordinates=[dict(source_batch='x',universe_track='x',
            selection_date='2024-02-01',status='NO_DELTA',planned=0,tasks=[])])).encode()
        with patch.object(module.original,'INDEX',Mock(read_bytes=lambda:raw)), \
             patch.object(module.original,'INDEX_SHA',hashlib.sha256(raw).hexdigest()), \
             patch.object(module.original,'_check_sources'):
            result=module.prepare_date_v2(source_batch='x',universe_track='x',selection_date='2024-02-01')
        self.assertEqual(result['status'],'DELTA_ONLY_NO_TASKS')
        self.assertFalse(result['all_base_candidates_included'])


if __name__=='__main__':
    unittest.main()
