import copy
import unittest
from datetime import date, timedelta
from backtest.annual_identity_history_eligibility import assess_eligibility, assess_observed_domain


class EligibilityTests(unittest.TestCase):
    def fixture(self):
        days = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(270)]
        binding = dict(ticker='X', security_id='verified:X', role='SELECTION',
                       mode='DATED_EVIDENCE', valid_from=days[0], valid_through=days[-1],
                       known_asof=days[0], source_references=['reviewed-source'], regular_way_start=days[0])
        channel = dict(binding, channel='ORDINARY_REGULAR_WAY', currency='USD', source_id='raw-sha')
        return dict(ticker='X', security_id='verified:X', decision_date=days[252],
                    regular_way_start=days[0], sessions=days, closes=dict.fromkeys(days, '10'),
                    identity_binding=binding, channel_binding=channel)

    def test_253_and_future_do_not_help(self):
        args = self.fixture()
        self.assertEqual(assess_eligibility(**args)['status'], 'READY_CONDITIONAL_IDENTITY_HISTORY')
        args['decision_date'] = args['sessions'][251]
        self.assertEqual(assess_eligibility(**args)['valid_regular_closes'], 252)
        self.assertIn('INSUFFICIENT_253_REGULAR_SESSION_CLOSES', assess_eligibility(**args)['reasons'])

    def test_no_ticker_exemption_even_with_enough_history(self):
        for ticker in ('SPCX', 'HONA', 'X'):
            args = self.fixture(); args.update(ticker=ticker, security_id=None)
            self.assertIn('SECURITY_ID_UNRESOLVED', assess_eligibility(**args)['reasons'])

    def test_when_issued_not_counted_and_later_reevaluates(self):
        args = self.fixture(); args['regular_way_start'] = args['sessions'][5]
        args['identity_binding']['regular_way_start'] = args['regular_way_start']
        self.assertEqual(assess_eligibility(**args)['valid_regular_closes'], 248)
        args['decision_date'] = args['sessions'][257]
        self.assertFalse(assess_eligibility(**args)['reasons'])

    def test_gap_not_replaced_with_older_observation(self):
        args = self.fixture(); args['decision_date'] = args['sessions'][260]
        del args['closes'][args['sessions'][50]]
        self.assertEqual(assess_eligibility(**args)['valid_regular_closes'], 252)

    def test_passive_child_and_identity_channel_scope(self):
        for field, value, expected in [('role', 'PASSIVE_CHILD', 'IDENTITY_NOT_SELECTION_ADMITTED'),
                ('valid_from', '2024-02-01', 'IDENTITY_DATE_SCOPE_INSUFFICIENT'),
                ('source_references', [], 'IDENTITY_EVIDENCE_MISSING')]:
            args = self.fixture(); args['identity_binding'][field] = value
            self.assertIn(expected, assess_eligibility(**args)['reasons'])
        args = self.fixture(); args['channel_binding']['channel'] = 'WHEN_ISSUED'
        self.assertIn('CHANNEL_NOT_ORDINARY_REGULAR_WAY', assess_eligibility(**args)['reasons'])

    def test_retrospective_requires_explicit_condition(self):
        args = self.fixture(); args['identity_binding']['known_asof'] = args['sessions'][-1]
        self.assertIn('IDENTITY_FUTURE_EVIDENCE_REQUIRES_CONDITIONAL_DECLARATION', assess_eligibility(**args)['reasons'])
        args['identity_binding']['mode'] = 'DECLARED_CONDITIONAL_LINK'
        self.assertIn('IDENTITY_CONDITIONAL_ASSUMPTION_MISSING', assess_eligibility(**args)['reasons'])
        args['identity_binding']['assumption'] = 'Retrospective reviewed continuity; not PIT.'
        result = assess_eligibility(**args)
        self.assertFalse(result['reasons']); self.assertFalse(result['execution_admitted'])

    def test_all_101_observed_members_retained(self):
        args = self.fixture(); members = ['X' + str(i) for i in range(101)]
        result = assess_observed_domain(members=members, records={}, decision_date=args['decision_date'], sessions=args['sessions'])
        self.assertEqual([r['ticker'] for r in result['rows']], members)
        self.assertEqual(result['ready_identity_history_count'], 0)
        self.assertTrue(all('INSUFFICIENT_253_REGULAR_SESSION_CLOSES' in r['reasons'] for r in result['rows']))

    def test_invalid_calendar_and_prices(self):
        args = self.fixture(); args['sessions'].append(args['sessions'][-1])
        with self.assertRaises(ValueError): assess_eligibility(**args)
        for price in ('nan', 'Infinity', 0, -1, True, None):
            args = self.fixture(); args['closes'][args['sessions'][30]] = price
            self.assertEqual(assess_eligibility(**args)['valid_regular_closes'], 252)


if __name__ == '__main__':
    unittest.main()
