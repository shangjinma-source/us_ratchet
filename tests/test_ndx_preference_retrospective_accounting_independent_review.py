"""Independent input-only rejection checks; deliberately never run the account."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import ndx_preference_retrospective_accounting_research as runner


class RetrospectiveInputReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = runner.ROOT / 'data/cache/research/preference_price_action_supplement_20260912_v1/nominal_quotes_20260912.json'
        cls.raw = cls.path.read_bytes()
        cls.digest = hashlib.sha256(cls.raw).hexdigest()
        cls.report = json.loads(cls.raw)

    def reject_resigned(self, mutation):
        changed = deepcopy(self.report)
        mutation(changed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'resigned.json'
            raw = json.dumps(changed).encode()
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                runner.prepare_inputs(path, hashlib.sha256(raw).hexdigest())

    def test_real_inputs_exact_schedule_and_cash_contract_without_execution(self):
        arguments, sources = runner.prepare_inputs(self.path, self.digest)
        self.assertEqual(arguments['opens'].shape, (295, 4))
        self.assertEqual(arguments['closes'].shape, (295, 4))
        self.assertEqual(len(arguments['schedule']), 15)
        self.assertEqual(arguments['initial_cash_usd'], 25000)
        self.assertEqual(arguments['minimum_cash_buffer_usd'], 100)
        self.assertEqual(arguments['transaction_cost_bps'], 10)
        self.assertEqual(arguments['corporate_actions'], [])
        self.assertGreater(len(sources), 32000)
        runner.verify(sources)
        self.assertEqual(self.path.read_bytes(), self.raw)

    def test_resigned_quote_cannot_escape_bound_raw(self):
        def change(report):
            report['by_ticker']['AMAT']['rows'][0]['nominal_open'] *= 2
        self.reject_resigned(change)

    def test_resigned_empty_closure_is_rejected(self):
        self.reject_resigned(lambda report: report.update(source_hashes={}))

    def test_resigned_split_factor_is_rejected(self):
        def change(report):
            report['by_ticker']['AVGO']['rows'][0]['split_factor'] = 1
        self.reject_resigned(change)

    def test_resigned_raised_certification_is_rejected(self):
        self.reject_resigned(lambda report: report.update(point_in_time_verified=True))


if __name__ == '__main__':
    unittest.main()
