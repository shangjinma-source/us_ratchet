import unittest
from backtest.dynamic_switch_provider import build_dynamic_provider
from backtest.current_quantity_v2_next_open_book import run_next_open_book


class NontradableCapitalTests(unittest.TestCase):
    def run_case(self, *, oversized=False, corrupt=False, timing='BEFORE_OPEN', bad_review=False):
        import test_dynamic_switch_multiday as fixtures
        fixture = fixtures.MultidayTests()
        days = fixture.days

        def builder(**arguments):
            inputs = fixture.build_inputs(**arguments)
            first = arguments['decision_date'] == days[0]
            inputs['candidate'] = {} if first else {'B': 3 if oversized else 1}
            if first:
                inputs['scenarios'] = [{'A': '1', 'B': '1'}]
            if corrupt and not first:
                inputs['prices']['B'] = '99'  # Full history comparison rejects conflicting marks.
            return inputs

        series = {'A': ['100', '80', '110', '110'], 'B': ['100']*4, 'C': ['10000']*4}
        bars = {sid: {day: dict(open=value, high=value, low=value, close=value)
                      for day, value in zip(days, values)} for sid, values in series.items()}
        event = dict(event_id='distribution', effective_date=days[1], timing=timing,
                     parent_sid='A', post_parent_sid='A', child_sid='C', child_ratio='1', parent_ratio='1',
                     eligibility_confirmed=True, ordered_steps_confirmed=True, parent_delivered_units_confirmed=True,
                     eligibility_rule='ACTUAL_HOLDINGS_IMMEDIATELY_BEFORE_EVENT', source_references=['fixture'])
        reviewed = dict(event, child_ratio='2') if bad_review else event
        provider, audit = build_dynamic_provider(builder, nontradable_policy='SELECT_TRADABLE_REPORT_TOTAL',
            reviewed_post_close_distributions=[reviewed] if timing == 'AFTER_CLOSE' else [])
        result = run_next_open_book(session_dates=days, ohlc=bars, initial_cash='300',
                                   initial_shares={'A': 1}, fee_bps='0', slippage_bps='0',
                                   distribution_events=[event], order_provider=provider,
                                   price_source_references={sid: ['fixture'] for sid in series})
        return result, audit

    def test_rights_count_in_equity_but_never_selection_cash(self):
        result, audit = self.run_case()
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        self.assertEqual(audit[1]['capital_basis']['tradable_equity'], '380')
        self.assertEqual(audit[1]['capital_basis']['nontradable_equity_excluded_from_selection'], '10000')
        self.assertEqual(result['daily_ledger'][0]['equity'], '10380')
        self.assertEqual(result['cash'], '310')
        self.assertEqual(result['shares'].get('C', 0), 0)
        self.assertEqual(result['distribution_rights'][0]['units'], '1')
        self.assertEqual(result['daily_ledger'][-1]['equity'], '10410')

    def test_rights_cannot_inflate_fifty_percent_target_limit(self):
        with self.assertRaisesRegex(ValueError, 'CAP50'):
            self.run_case(oversized=True)

    def test_marks_must_match_history(self):
        with self.assertRaisesRegex(ValueError, 'PRICE_MISMATCH'):
            self.run_case(corrupt=True)

    def test_after_close_distribution_uses_regular_close_then_values_rights(self):
        result, audit = self.run_case(timing='AFTER_CLOSE')
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        self.assertEqual(audit[1]['post_close_events_replayed'], ['distribution'])
        self.assertTrue(audit[1]['input_account']['distribution_rights'])
        self.assertEqual(audit[1]['decision_account']['distribution_rights'], [])
        self.assertEqual(audit[1]['capital_basis']['tradable_equity'], '380')
        self.assertEqual(result['daily_ledger'][0]['equity'], '380')
        self.assertEqual(result['daily_ledger'][1]['equity'], '10410')
        self.assertEqual(result['cash'], '310')
        self.assertEqual(result['shares'].get('C', 0), 0)
        self.assertEqual(audit[2]['capital_basis']['nontradable_equity_excluded_from_selection'], '10000')

    def test_after_close_wrong_entitlement_review_rejected(self):
        with self.assertRaisesRegex(ValueError, 'EVENT_OR_ELIGIBILITY_MISMATCH'):
            self.run_case(timing='AFTER_CLOSE', bad_review=True)


if __name__ == '__main__':
    unittest.main()
