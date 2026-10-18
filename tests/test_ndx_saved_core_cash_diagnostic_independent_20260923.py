"""Boundary tests only; never execute main or generate the diagnostic artifact."""
import copy
import json
import unittest
from scripts import ndx_saved_core_cash_diagnostic_20260923 as reader


class IndependentCashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(reader.checked(reader.SNAPSHOT, reader.SNAPSHOT_SHA))
        reader.checked(reader.TACTICAL, reader.TACTICAL_SHA)
        reader.checked(reader.CORE, reader.CORE_SHA)

    def test_actual_prepare_explicit_saved_limit_and_quote_not_limit(self):
        arguments, provenance = reader.prepare(self.snapshot)
        self.assertEqual(arguments['max_names'], self.snapshot['execution_constraints']['buy_plan_compact_target'])
        row = self.snapshot['symbols'][0]
        self.assertEqual(arguments['price_by_ticker'][row['ticker']], row['price'])
        self.assertNotEqual(arguments['price_by_ticker'][row['ticker']], row['tactical']['limit'])
        self.assertEqual(provenance[row['ticker']]['field'], 'symbols.price')

    def test_missing_numeric_or_eligibility_field_rejected(self):
        for key in ('gap_amount', 'gap_ratio', 'gap_rank', 'core_deployment_eligible', 'frozen', 'reported_closed'):
            snapshot = copy.deepcopy(self.snapshot)
            del snapshot['account']['position_gaps']['rows'][0][key]
            with self.subTest(key=key), self.assertRaises((KeyError, ValueError)): reader.prepare(snapshot)

    def test_reported_closed_excluded_even_if_other_flag_claims_eligible(self):
        snapshot = copy.deepcopy(self.snapshot)
        row = snapshot['account']['position_gaps']['rows'][0]
        row.update(reported_closed=True, core_deployment_eligible=True)
        arguments, _ = reader.prepare(snapshot)
        self.assertIn(row['ticker'], arguments['excluded_tickers'])

    def test_non_usd_saved_constraints_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['execution_constraints']['currency'] = 'CNY'
        with self.assertRaises(ValueError): reader.prepare(snapshot)

    def test_missing_quote_provenance_not_silently_defaulted(self):
        snapshot = copy.deepcopy(self.snapshot)
        del snapshot['symbols'][0]['price_source']
        with self.assertRaises((KeyError, ValueError)): reader.prepare(snapshot)

    def test_finite_inputs_with_overflowing_lot_cost_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['execution_constraints']['lot_size'] = 10**10
        for row in snapshot['symbols']: row['price'] = 1e308
        with self.assertRaises(ValueError): reader.prepare(snapshot)

    def test_missing_saved_name_limit_not_defaulted_to_four(self):
        snapshot = copy.deepcopy(self.snapshot)
        del snapshot['execution_constraints']['buy_plan_compact_target']
        with self.assertRaises((KeyError, ValueError)): reader.prepare(snapshot)

    def test_explicit_cash_reserve_semantics_required(self):
        snapshot = copy.deepcopy(self.snapshot)
        del snapshot['execution_constraints']['cash_input_net_of_reserve']
        with self.assertRaises((KeyError, ValueError)): reader.prepare(snapshot)


if __name__ == '__main__': unittest.main()
