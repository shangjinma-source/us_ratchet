import copy
import unittest

from scripts.ndx_saved_core_cash_diagnostic_20260923 import build, prepare


def fixture():
    return dict(snapshot_id='synthetic', ts='2026-09-23T08:27:00',
        state_freshness={'status': 'DAILY_UPDATE_REQUIRED'},
        execution_constraints=dict(currency='USD', cash_input_net_of_reserve=True, allow_fractional=False, lot_size=1, fee_bps=0,
            min_fee=5, buy_plan_compact_target=4),
        symbols=[dict(ticker='AAA', price=100, previous_close=99, price_source='synthetic')],
        account=dict(position_gaps=dict(rows=[dict(ticker='AAA', gap_amount=250,
            gap_ratio=1, gap_rank=1, target_amount=250, real_market_value=0,
            position_kind='pending_entry', core_deployment_eligible=True,
            frozen=False, reported_closed=False)])))


class SavedCoreDiagnosticTests(unittest.TestCase):
    def test_gap_fee_and_authority_stay_separate(self):
        source = fixture()
        before = copy.deepcopy(source)
        result = build(source)
        self.assertEqual(source, before)
        for scenario in result['scenarios']:
            draft = scenario['mathematical_core_draft']
            self.assertEqual(draft['lines'][0]['shares'], 2)
            self.assertEqual(draft['lines'][0]['estimated_fee'], 5)
            self.assertEqual(draft['cash_deployed'], 205)
            self.assertEqual(draft['status'], 'ACCOUNT_CONFIRMATION_REQUIRED')
            self.assertFalse(scenario['executable'])
        self.assertFalse(result['prices_equal_tactical_limits'])
        self.assertFalse(result['account_readiness_verified'])

    def test_reported_exit_does_not_reenter(self):
        source = fixture()
        source['account']['position_gaps']['rows'][0]['reported_closed'] = True
        self.assertEqual(build(source)['scenarios'][0]['mathematical_core_draft']['lines'], [])

    def test_missing_eligibility_is_not_default_true(self):
        source = fixture()
        del source['account']['position_gaps']['rows'][0]['core_deployment_eligible']
        with self.assertRaises(KeyError):
            prepare(source)

    def test_duplicate_and_missing_quotes_rejected(self):
        source = fixture()
        source['symbols'].append(dict(source['symbols'][0]))
        with self.assertRaises(ValueError):
            prepare(source)
        source['symbols'] = []
        with self.assertRaises(ValueError):
            prepare(source)

    def test_no_fractional_lot_or_nonfinite_default(self):
        for value in (0.5, float('nan'), float('inf'), True):
            source = fixture()
            source['execution_constraints']['lot_size'] = value
            with self.assertRaises(ValueError):
                prepare(source)


if __name__ == '__main__':
    unittest.main()
