"""Protect causal book admission against omitted exposed corporate actions."""
import unittest
from scripts.run_recent_continuous_probe import exposed_action_blockers, gross_dividend_events, canonical_day


class ExposureGateTests(unittest.TestCase):
    def setUp(self):
        self.arguments = dict(decision_date='2021-01-29', account_state=dict(shares={'old':2,'zero':0}))
        self.selection = dict(target_quantities={'new':3,'unused':0})
        self.prices = dict(action_stream_missing=[],provider_event_inventory=[])

    def check(self):
        return exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices)

    def test_new_target_action_on_last_day_blocks(self):
        self.prices['provider_event_inventory'] = [dict(security_id='new',date='2021-02-26',kind='splits')]
        self.assertFalse(self.check()['admitted'])

    def test_existing_holdings_require_action_stream_even_if_not_targeted(self):
        self.prices['action_stream_missing'] = ['old']
        self.assertEqual(self.check()['missing_action_streams'],['old'])

    def test_unheld_actions_and_past_events_do_not_block(self):
        self.prices['action_stream_missing'] = ['unused']
        self.prices['provider_event_inventory'] = [dict(security_id='unused',date='2021-02-01'),
                                                  dict(security_id='old',date='2021-01-29')]
        self.assertTrue(self.check()['admitted'])

    def test_period_review_cannot_extend_to_a_different_month(self):
        self.prices['action_stream_missing']=['new']
        evidence=dict(rows=[dict(security_id='new',status='REVIEWED_NO_ACTION_FOR_PERIOD',
            start_exclusive='2021-01-29',end_inclusive='2021-02-26')])
        self.assertTrue(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence)['admitted'])
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-03-31',self.prices,evidence)['admitted'])

    def test_period_review_never_overrides_observed_action(self):
        self.prices['action_stream_missing']=['new']
        self.prices['provider_event_inventory']=[dict(security_id='new',date='2021-02-15',kind='dividends')]
        evidence=dict(rows=[dict(security_id='new',status='REVIEWED_NO_ACTION_FOR_PERIOD',
            start_exclusive='2021-01-29',end_inclusive='2021-02-26')])
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence)['admitted'])

    def test_liquidated_old_holding_needs_review_through_next_open(self):
        self.prices['action_stream_missing']=['old']
        evidence=dict(rows=[dict(security_id='old',status='REVIEWED_NO_ACTION_FOR_PERIOD',
            start_exclusive='2021-01-29',end_inclusive='2021-02-01')])
        self.prices['provider_event_inventory']=[dict(security_id='old',date='2021-02-15',kind='dividends')]
        result=exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence,'2021-02-01')
        self.assertTrue(result['admitted'])
        self.assertEqual(result['exposure_end_by_security']['old'],'2021-02-01')
        self.assertEqual(result['exposure_end_by_security']['new'],'2021-02-26')

    def test_liquidation_day_action_still_blocks(self):
        self.prices['provider_event_inventory']=[dict(security_id='old',date='2021-02-01',kind='splits')]
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,
            active_date='2021-02-01')['admitted'])

    def test_reviewed_full_month_covers_short_liquidation_exposure(self):
        self.prices['action_stream_missing']=['old']
        evidence=dict(rows=[dict(security_id='old',status='REVIEWED_NO_ACTION_FOR_PERIOD',
            start_exclusive='2021-01-29',end_inclusive='2021-02-26')])
        self.assertTrue(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,
            evidence,'2021-02-01')['admitted'])

    def test_ex_date_new_purchase_has_zero_reviewed_ordinary_dividend(self):
        event=dict(security_id='new',date='2021-02-01',kind='dividends')
        self.prices['provider_event_inventory']=[event]
        evidence=dict(rows=[dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id='new',ex_date='2021-02-01')])
        result=exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence,'2021-02-01')
        self.assertTrue(result['admitted'])
        self.assertEqual(result['ignored_zero_entitlement'][0]['opening_quantity'],0)
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,
            active_date='2021-02-01')['admitted'])
        self.arguments['account_state']['shares']['new']=1
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence,'2021-02-01')['admitted'])

    def test_zero_dividend_rule_never_waives_split(self):
        self.prices['provider_event_inventory']=[dict(security_id='new',date='2021-02-01',kind='splits')]
        evidence=dict(rows=[dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id='new',ex_date='2021-02-01')])
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,evidence,'2021-02-01')['admitted'])

    def dividend_fixture(self):
        row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id='old',ex_date='2021-02-02',
            payment_date='2021-02-26',record_date='2021-02-03',amount_per_share='0.04',currency='USD')
        review=dict(source_hashes={'raw':'abc'},rows=[row])
        self.prices['provider_event_inventory']=[dict(security_id='old',date='2021-02-02',kind='dividends',source='raw',source_sha256='abc',provider_event={'amount':0.004})]
        return review,['2021-01-29','2021-02-01','2021-02-02','2021-02-26']

    def test_held_dividend_maps_official_amount_and_preserves_provider(self):
        review,sessions=self.dividend_fixture()
        events=gross_dividend_events(review,self.prices,sessions)
        self.assertEqual(events[0]['amount_per_share'],'1/25')
        self.assertEqual(events[0]['withholding_rate'],'0')
        self.selection['target_quantities']['old']=2
        gate=exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,review,'2021-02-01',events)
        self.assertTrue(gate['admitted'])
        self.assertEqual(gate['mapped_ordinary_dividends'][0]['provider_event']['provider_event']['amount'],0.004)
        self.assertFalse(exposed_action_blockers(self.arguments,self.selection,'2021-02-26',self.prices,review)['admitted'])
        from backtest.historical_dividend_next_open_book_research import run_next_open_book
        bars={'old':{day:dict(open='10',high='10',low='10',close='10') for day in sessions}}
        book=run_next_open_book(session_dates=sessions,orders=[],ohlc=bars,initial_cash='100',initial_shares={'old':2},fee_bps='0',slippage_bps='5',dividend_events=events)
        self.assertEqual(book['status'],'COMPLETE')
        self.assertEqual(book['dividend_ledger']['paid_cash'],'2/25')

    def test_dates_duplicate_and_source_fail_closed(self):
        for bad in ('20210202','2021-2-02','2021-02-30'):
            with self.assertRaises(ValueError):canonical_day(bad)
        review,sessions=self.dividend_fixture();review['rows'][0]['payment_date']='2021-02-01'
        with self.assertRaises(ValueError):gross_dividend_events(review,self.prices,sessions)
        review,sessions=self.dividend_fixture();review['rows'].append(dict(review['rows'][0]))
        with self.assertRaises(ValueError):gross_dividend_events(review,self.prices,sessions)
        review,sessions=self.dividend_fixture();review['source_hashes']['raw']='wrong'
        with self.assertRaises(ValueError):gross_dividend_events(review,self.prices,sessions)


if __name__ == '__main__':
    unittest.main()
