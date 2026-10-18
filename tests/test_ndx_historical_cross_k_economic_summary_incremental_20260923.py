import copy
import json
from pathlib import Path
import unittest

from scripts import ndx_historical_cross_k_economic_summary_incremental_20260923 as module


class IncrementalSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = json.loads(Path(module.SEED['path']).read_bytes())
        cls.previous = json.loads(module.base.AUDIT.read_bytes())
        path = next(iter(module.AUTHORIZED_AUDITS))
        cls.audit = json.loads(Path(path).read_bytes())
        cls.index = json.loads(Path(cls.audit['index_reference']['path']).read_bytes())

    def test_real_audited_prefix_without_ledger_reexecution(self):
        self.assertEqual(module.validate_extension(self.seed, self.previous, self.audit, self.index), 111)

    def test_prefix_and_benchmark_replacement_rejected(self):
        for key, value in [('shared_control_reference', {}), ('details', self.audit['details'][::-1]),
                           ('promotion_allowed', True), ('completed_account_task_count', True)]:
            bad = copy.deepcopy(self.audit)
            bad[key] = value
            with self.assertRaises(ValueError):
                module.validate_extension(self.seed, self.previous, bad, self.index)

    def test_index_omission_and_duplicate_rejected(self):
        for entries in (self.index['entries'][:-1], self.index['entries'][:-1] + self.index['entries'][:1]):
            bad = copy.deepcopy(self.index)
            bad['entries'] = entries
            with self.assertRaises(ValueError):
                module.validate_extension(self.seed, self.previous, self.audit, bad)

    def test_arbitrary_self_signed_audit_not_authority(self):
        with self.assertRaises(ValueError):
            module.build('invented.json', '0' * 64)
        with self.assertRaises(ValueError):
            module.build(next(iter(module.AUTHORIZED_AUDITS)), '0' * 64)


if __name__ == '__main__':
    unittest.main()
