import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_single_replacement_preparation_independent_readback_20261003 as reader
from backtest import ndx_single_replacement_domain_research as core
from test_ndx_single_replacement_preparation_independent_readback_20261003 import prepared


class IndependentReview(unittest.TestCase):
    def test_saved_domain_hand_count_without_core(self):
        with tempfile.TemporaryDirectory() as folder:
            with prepared(Path(folder)):
                # Each sale realizes $20 less $0.02. Available above buffer is
                # $29.98. Purchases at $5.005 and $10.01 admit 5 and 2 shares.
                # Two outgoing holdings yield 14 points per scenario.
                with patch.object(core, 'prepare_single_replacement_domain', side_effect=AssertionError('core forbidden')):
                    ref = reader.readback(execute=True)
                report = json.loads(Path(ref['path']).read_bytes())
                self.assertEqual(report['inspection']['integer_count'], 40 * 14)
                self.assertEqual(report['inspection']['pair_count'], 40 * 4)
                self.assertEqual(report['inspection']['structurally_excluded_integer_count'], 0)
                self.assertFalse(report['original_account_reopened'])

    def test_last_case_boolean_ordinal_rejected_after_resigning(self):
        with tempfile.TemporaryDirectory() as folder:
            with prepared(Path(folder)) as (refs, _):
                docs = {key: reader.decode(Path(refs[key]['path']).read_bytes()) for key in
                        ('policy', 'inputs', 'input_publication', 'inventory', 'inventory_publication', 'scenarios')}
                value = reader.decode((reader.PARENT / 'preparation.json').read_bytes())['preparation']
                value['document']['cases'][-1]['pairs'][0]['pair_index'] = False
                value['content_sha256'] = reader.digest(value['document'])
                with self.assertRaises(ValueError):
                    reader.inspect_domain(documents=docs, references=refs, saved_preparation=value)


if __name__ == '__main__':
    unittest.main()
