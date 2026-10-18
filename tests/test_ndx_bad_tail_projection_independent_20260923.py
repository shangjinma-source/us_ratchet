import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_bad_tail_five_input_projection_20260923 as projection


class IndependentProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parents = {}
        for role in projection.BOUND:
            reference = projection.reference(role)
            raw = Path(reference['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != reference['sha256']:
                raise ValueError('Independent fixture source differs')
            cls.parents[role] = json.loads(raw)

    def test_exact_identity_rows_and_selected_chain_scope(self):
        result = projection.project(self.parents)
        expected = [row for row in self.parents['identity']['rows'] if row['ticker'] in {'AMAT','AVGO','BKR','CDNS','FTNT'}]
        self.assertEqual(result['identity_projection']['rows'], sorted(expected, key=lambda row: row['security_id']))
        self.assertNotIn('risk_chains_by_decision', result)
        self.assertFalse(result['execution_risk_chain_union_verified'])
        self.assertFalse(result['target_schedule_validity_verified'])

    def test_missing_non_selected_parent_cell_is_not_silently_discarded(self):
        parents = copy.deepcopy(self.parents)
        parents['price']['matrices']['close']['2023-03-31'].pop('GOOGL')
        with self.assertRaises(ValueError):
            projection.project(parents)

    def test_nan_and_zero_selected_quotes_rejected(self):
        for value in ('NaN', 'Infinity', '0', '-1'):
            parents = copy.deepcopy(self.parents)
            parents['price']['matrices']['open']['2023-03-31']['FTNT'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                projection.project(parents)

    def test_parent_final_linkage_and_duplicate_json_rejected(self):
        parents = copy.deepcopy(self.parents)
        parents['price_final']['raw_reference']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            projection.project(parents)
        with self.assertRaises(ValueError):
            json.loads('{"same":1,"same":2}', object_pairs_hook=projection.unique)

    def test_source_drift_after_build_prevents_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'new' / 'projection.json'
            with patch.object(projection, 'OUTPUT', output), patch.object(projection, 'build', return_value={
                'historical_expected_source_hashes': {}, 'archive_resolution': {'old': True}}), \
                patch.object(projection.archive, 'load_contract', return_value={}), \
                patch.object(projection.archive, 'verify_expected_sources', return_value={'changed': True}):
                with self.assertRaises(ValueError):
                    projection.publish()
                self.assertFalse(output.parent.exists())


if __name__ == '__main__':
    unittest.main()
