"""Adversarial saved-ledger checks; synthetic engine fixture only."""
import copy
import unittest

from test_ndx_frozen_accounting_independent_audit_research import fixture
from backtest import ndx_frozen_accounting_independent_audit_research as audit
from test_ndx_frozen_accounting_independent_audit_research import engine, pd


class LedgerReviewTests(unittest.TestCase):
    def test_risk_only_rejection_keeps_account_then_new_composition_fills(self):
        args = fixture()
        args['prices'][args['calendar'][1]]['A']['open'] = 1.
        frames = {kind: pd.DataFrame({s: [args['prices'][d][s][kind] for d in args['calendar']]
            for s in 'ABCDE'}, index=pd.DatetimeIndex(args['calendar'])) for kind in ('open', 'close')}
        args['execution'] = engine.simulate_dynamic_frozen_execution_research(
            opens=frames['open'], closes=frames['close'], schedule=args['schedule'],
            risk_chains_by_decision=args['risk_chains_by_decision'], corporate_actions=[],
            valuation_end_date=args['calendar'][-1], max_repair_evaluations=64, **args['contract'])
        first = args['execution']['executions'][0]
        self.assertIn('MIN_SINGLE_WEIGHT', first['failure_reasons'])
        self.assertNotIn('CASH_BUFFER', first['failure_reasons'])
        report = audit.audit(**args)
        self.assertEqual(report['rejected_count'], 1)
        self.assertEqual(set(report['terminal_shares']), set('BCDE'))

    def test_saved_risk_metadata_must_match_independent_calculation(self):
        base = fixture()
        for container, field in [('decisions', 'decision_risk'), ('executions', 'risk'), ('daily', 'risk')]:
            with self.subTest(container=container):
                args = copy.deepcopy(base)
                row = args['execution'][container][1 if container == 'daily' else 0]
                row[field]['checks']['MAX_SINGLE_WEIGHT'] = False
                row[field]['all_passed'] = False
                row[field]['actual_weights']['A'] = .99
                with self.assertRaises(ValueError):
                    audit.audit(**args)

    def test_integer_types_not_python_numeric_equality(self):
        base = fixture()
        for container, field in [('daily', 'shares'), ('executions', 'shares_after')]:
            with self.subTest(container=container):
                args = copy.deepcopy(base)
                row = args['execution'][container][1 if container == 'daily' else 0]
                row[field]['A'] = float(row[field]['A'])
                with self.assertRaises(ValueError):
                    audit.audit(**args)

    def test_saved_risk_boolean_and_trade_delta_types_are_strict(self):
        base = fixture()
        changes = [lambda a: a['execution']['executions'][0]['risk']['checks'].update(MAX_SINGLE_WEIGHT=1),
            lambda a: a['execution']['decisions'][0]['decision_risk'].update(all_passed=1),
            lambda a: a['execution']['trades'][0].update(share_delta=float(a['execution']['trades'][0]['share_delta']))]
        for change in changes:
            with self.subTest(change=change):
                args = copy.deepcopy(base)
                change(args)
                with self.assertRaises(ValueError):
                    audit.audit(**args)

    def test_no_plan_cannot_claim_frozen_order_payload(self):
        args = fixture(expensive=True)
        args['execution']['decisions'][0].update(desired_shares={'A': 1}, delta={'A': 1})
        with self.assertRaises(ValueError):
            audit.audit(**args)

    def test_summary_denominators_are_observed_not_arbitrary(self):
        base = fixture()
        for field, value in [('session_count', 400), ('all_cash_session_count', 0), ('k_path', [5, 5])]:
            with self.subTest(field=field):
                args = copy.deepcopy(base)
                args['execution']['summary'][field] = value
                with self.assertRaises(ValueError):
                    audit.audit(**args)


if __name__ == '__main__':
    unittest.main()
