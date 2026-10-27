import unittest
from backtest.guidance_news_risk_research_v1 import GuidanceNewsRiskAdapter


class BaseRisk:
    state = {'decision_date': '2026-01-30', 'peaks': {}}
    exited = False

    def apply(self, **kwargs):
        return ({key: 0 if self.exited else value for key, value in kwargs['target'].items()}, {'base_preserved': True})


def event(identity='cut', kind='CUT', available='2026-01-30T21:00:01Z', key='same-fiscal-period'):
    return dict(id=identity, classification=kind, available_at=available,
                comparison_key=key, period_end='2026-02-02', security_id='A',
                review_reference='synthetic-only', source_hashes=['synthetic-source'])


class GuidanceOverlayTests(unittest.TestCase):
    def test_explicit_repair_does_not_release_on_unchanged_or_unrelated_good_news(self):
        for update in [event('unchanged', 'UNCHANGED', '2026-02-02T15:00:00Z'),
                       event('raised', 'RAISE', '2026-02-02T15:00:00Z'),
                       dict(event('repair', 'REPAIRED', '2026-02-02T15:00:00Z'), repairs_event_id='other-cut'),
                       dict(event('repair', 'REPAIRED', '2026-02-02T15:00:00Z', 'other-period'), repairs_event_id='cut')]:
            adapter = GuidanceNewsRiskAdapter(BaseRisk(), events=[event(), update],
                session_closes={'2026-02-02': '2026-02-02T21:00:00Z'},
                action_policy='BLOCK_NEW_BUYS', release_policy='EXPLICIT_REPAIR')
            result, _ = adapter.apply(day='2026-02-02', month='2026-02',
                target={'A': 10}, closes={'A': '100'}, shares={'A': 3})
            self.assertEqual(result['A'], 3)

    def test_exact_repair_restores_eligibility_but_not_original_exit(self):
        for exited, expected in [(False, 10), (True, 0)]:
            base = BaseRisk()
            base.exited = exited
            repair = dict(event('repair', 'REPAIRED', '2026-02-02T15:00:00Z'), repairs_event_id='cut')
            adapter = GuidanceNewsRiskAdapter(base, events=[event(), repair],
                session_closes={'2026-02-02': '2026-02-02T21:00:00Z'},
                action_policy='BLOCK_NEW_BUYS', release_policy='EXPLICIT_REPAIR')
            result, audit = adapter.apply(day='2026-02-02', month='2026-02',
                target={'A': 10}, closes={'A': '100'}, shares={'A': 3})
            self.assertEqual(result['A'], expected)
            self.assertEqual(audit['guidance_news']['active_event_ids'], [])

    def test_buy_block_preserves_positions_and_original_sells(self):
        for held, original, expected in [(10, 15, 10), (10, 5, 5), (10, 0, 0), (0, 5, 0)]:
            adapter = GuidanceNewsRiskAdapter(BaseRisk(), events=[event(available='2026-01-29T21:00:00Z')],
                session_closes={'2026-01-30': '2026-01-30T21:00:00Z'}, action_policy='BLOCK_NEW_BUYS')
            result, audit = adapter.apply(day='2026-01-30', month='2026-01',
                target={'A': original, 'B': 2}, closes={'A': '100', 'B': '50'}, shares={'A': held})
            self.assertEqual(result, {'A': expected, 'B': 2})
            self.assertEqual(audit['guidance_news']['action_policy'], 'BLOCK_NEW_BUYS')

    def test_buy_block_rejects_missing_holdings_before_consuming_event(self):
        adapter = GuidanceNewsRiskAdapter(BaseRisk(), events=[event(available='2026-01-29T21:00:00Z')],
            session_closes={'2026-01-30': '2026-01-30T21:00:00Z'}, action_policy='BLOCK_NEW_BUYS')
        for shares in (None, {'A': -1}, {'A': True}, {'A': 1.5}):
            with self.assertRaisesRegex(ValueError, 'CURRENT_NONNEGATIVE_INTEGER_SHARES_REQUIRED'):
                adapter.apply(day='2026-01-30', month='2026-01', target={'A': 3}, closes={'A': '100'}, shares=shares)
            self.assertEqual(adapter.position, 0)
            self.assertIsNone(adapter.last_day)

    def adapter(self, events):
        return GuidanceNewsRiskAdapter(BaseRisk(), events=events, session_closes={
            '2026-01-30': '2026-01-30T21:00:00Z',
            '2026-02-02': '2026-02-02T21:00:00Z',
            '2026-02-03': '2026-02-03T21:00:00Z'})

    def apply(self, adapter, day):
        return adapter.apply(day=day, month=day[:7], target={'A': 3, 'B': 2}, closes={'A': '100', 'B': '50'})

    def test_after_close_is_not_backdated_and_lock_crosses_month(self):
        adapter = self.adapter([event()])
        self.assertEqual(self.apply(adapter, '2026-01-30')[0]['A'], 3)
        result, audit = self.apply(adapter, '2026-02-02')
        self.assertEqual(result, {'A': 0, 'B': 2})
        self.assertTrue(audit['base_preserved'])
        self.assertFalse(audit['guidance_news']['order_execution_confirmed'])
        self.assertEqual(self.apply(adapter, '2026-02-03')[0]['A'], 3)

    def test_equal_cutoff_waits_and_preexisting_cut_applies(self):
        adapter = self.adapter([event(available='2026-01-30T21:00:00Z')])
        self.assertEqual(self.apply(adapter, '2026-01-30')[0]['A'], 3)
        adapter = self.adapter([event(available='2026-01-29T21:00:00Z')])
        self.assertEqual(self.apply(adapter, '2026-01-30')[0]['A'], 0)

    def test_release_never_clears_original_exit(self):
        adapter = self.adapter([event(available='2026-01-29T21:00:00Z'),
            event('release', 'UNCHANGED', '2026-02-02T15:00:00Z')])
        self.apply(adapter, '2026-01-30')
        adapter.base.exited = True
        result, audit = self.apply(adapter, '2026-02-02')
        self.assertEqual(result['A'], 0)
        self.assertEqual(audit['guidance_news']['blocked_security_ids'], [])

    def test_unknown_or_other_period_cannot_release(self):
        for replacement in [event('unknown', 'UNKNOWN', '2026-02-02T15:00:00Z'),
                            event('other', 'RAISE', '2026-02-02T15:00:00Z', 'other-period')]:
            adapter = self.adapter([event(), replacement])
            self.assertEqual(self.apply(adapter, '2026-02-02')[0]['A'], 0)

    def test_ambiguous_events_and_naive_time_rejected(self):
        for events in [[event(), event()], [event(), event('duplicate-time')],
                       [event(available='2026-01-30T21:00:00')]]:
            with self.assertRaises(ValueError):
                self.adapter(events)

    def test_repeated_day_cannot_consume_again(self):
        adapter = self.adapter([event()])
        self.apply(adapter, '2026-02-02')
        with self.assertRaises(ValueError):
            self.apply(adapter, '2026-02-02')

    def test_conflicting_period_end_and_untyped_identity_rejected(self):
        other = event('later', 'RAISE', '2026-02-02T15:00:00Z')
        other['period_end'] = '2026-03-31'
        malformed = event()
        malformed['security_id'] = ['A']
        for events in ([event(), other], [malformed], ['not-an-event']):
            with self.assertRaises(ValueError):
                self.adapter(events)

    def test_real_monthly_exit_survives_news_release_and_price_recovery(self):
        from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
        adapter = self.adapter([event(available='2026-01-29T21:00:00Z'),
            event('release', 'RAISE', '2026-02-02T15:00:00Z')])
        adapter.base = MonthlyExitCoreResearchAdapter()
        for day, price in [('2026-01-30', '100'), ('2026-02-02', '79'), ('2026-02-03', '100')]:
            result, audit = adapter.apply(day=day, month='2026-01-30', target={'A': 3}, closes={'A': price})
            self.assertEqual(result['A'], 0)
        self.assertEqual(adapter.state['exited'], ['A'])
        self.assertEqual(audit['guidance_news']['blocked_security_ids'], [])
