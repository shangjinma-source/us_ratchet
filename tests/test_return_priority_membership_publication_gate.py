import unittest
from backtest.return_priority_membership_publication_gate import evaluate_membership_event, propose_membership_update


class PublicationGateTests(unittest.TestCase):
    def event(self):
        return dict(event_id='sndk', source_reported_published_at='2026-04-10T20:00:00-04:00',
                    effective_date='2026-04-20', effective_phase='BEFORE_MARKET_OPEN',
                    add=['SNDK'], remove=['TEAM'], source_references=['official-observation'])

    def test_known_and_effective_are_distinct(self):
        e = self.event()
        self.assertEqual(evaluate_membership_event(e, decision_at='2026-04-10T16:00:00-04:00')['status'], 'NOT_YET_KNOWN')
        self.assertEqual(evaluate_membership_event(e, decision_at='2026-04-11T12:00:00-04:00')['status'], 'KNOWN_NOT_EFFECTIVE')
        # Explicit caller-supplied synthetic regular-open boundary, not inferred.
        boundary = {'sndk': '2026-04-20T09:30:00-04:00'}
        r = propose_membership_update(['TEAM','AAPL'], [e], decision_at='2026-04-20T16:00:00-04:00', effective_boundaries=boundary)
        self.assertEqual(r['members'], ['AAPL','SNDK'])
        self.assertFalse(r['complete_pit_universe_certified'])

    def test_missing_timestamps_never_become_midnight(self):
        e = self.event(); e.pop('source_reported_published_at')
        self.assertEqual(evaluate_membership_event(e,decision_at='2026-04-30T16:00:00-04:00')['status'],'UNKNOWN_PUBLICATION_TIME')
        with self.assertRaises(ValueError): evaluate_membership_event(self.event(),decision_at='2026-04-10')
        self.assertEqual(evaluate_membership_event(self.event(),decision_at='2026-04-20T16:00:00-04:00')['status'],'UNKNOWN_INTRADAY_EFFECTIVE_BOUNDARY')

    def test_duplicate_and_wrong_boundary_reject(self):
        e=self.event()
        with self.assertRaises(ValueError):propose_membership_update(['TEAM'],[e,e],decision_at='2026-04-30T12:00:00-04:00')
        with self.assertRaises(ValueError):evaluate_membership_event(e,decision_at='2026-04-20T12:00:00-04:00',effective_at='2026-04-21T09:30:00-04:00')


if __name__ == '__main__': unittest.main()
