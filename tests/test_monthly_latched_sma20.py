import unittest
from copy import deepcopy
from unittest.mock import patch
from test_current_quantity_v2_risk_overlays import fixture
from test_current_quantity_v2_risk_next_open import fixture as book_fixture
from backtest.monthly_latched_sma20 import MonthlyLatchedSma20
from backtest.monthly_latched_next_open import run_monthly_latched_next_open


class MonthlyLatchTests(unittest.TestCase):
    def test_equality_latches_independently_and_only_actual_selection_resets(self):
        latch=MonthlyLatchedSma20()
        first=fixture({'A':[100]*20,'B':[100]*19+[101]},quantities={'A':7,'B':9})
        before=deepcopy(first)
        self.assertEqual(latch.target(actual_monthly_selection=True,**first)['target_quantities'],{'A':0,'B':9})
        self.assertEqual(first,before)
        first['histories']['A']['closes'][-1]['close']='120'
        self.assertEqual(latch.target(**first)['target_quantities'],{'A':0,'B':9})
        later=fixture({'A':[100]*20+[120],'B':[100]*20+[120]},quantities={'A':6,'B':8})
        for history in later['histories'].values():history['closes']=history['closes'][-20:]
        with self.assertRaisesRegex(ValueError,'MONTH_CHANGED_WITHOUT_SELECTION'):latch.target(**later)
        self.assertEqual(latch.target(actual_monthly_selection=True,**later)['target_quantities'],{'A':6,'B':8})
        with self.assertRaisesRegex(ValueError,'NEW_ACTUAL_MONTHLY_SELECTION'):latch.target(actual_monthly_selection=True,**later)

    def test_action_migration_or_merge_preserves_latch_and_termination(self):
        latch=MonthlyLatchedSma20();latch.latched={'A':True,'B':False};latch.monthly_decision_date='2026-01-29'
        latch.migrate([dict(security_id='A',new_security_id='B',target_after=3)])
        self.assertEqual(latch.latched,{'B':True})
        latch.latched['A']=False
        latch.migrate([dict(security_id='A',new_security_id='B',target_after=3)])
        self.assertEqual(latch.latched,{'B':True})
        latch.migrate([dict(security_id='B',new_security_id='B',target_after=6)])
        self.assertEqual(latch.latched,{'B':True})
        latch.migrate([dict(security_id='B',target_after=0,reason='TERMINATED_MIXED_ENTITLEMENT')])
        self.assertEqual(latch.latched,{})
        with self.assertRaisesRegex(ValueError,'ORIGIN_MISSING'):
            latch.migrate([dict(security_id='unknown',new_security_id='C',target_after=1)])

    def test_actual_account_book_exits_without_same_month_reentry(self):
        assembled,bars,resolver=book_fixture()
        run=lambda data:run_monthly_latched_next_open(assembled=assembled,ohlc=data,initial_cash='1000',
            fee_bps='0',slippage_bps='0',history_resolver=resolver)
        result=run(bars);self.assertEqual(result['status'],'COMPLETE')
        rows=result['provider_audit'];self.assertGreater(rows[0]['target_shares']['A'],0)
        self.assertEqual(rows[1]['target_shares']['A'],0)
        self.assertTrue(any(order['side']=='SELL' for order in rows[1]['orders']))
        self.assertEqual(rows[2]['target_shares']['A'],0)
        self.assertFalse(any(order['side']=='BUY' for row in rows[1:] for order in row['orders']))
        changed=deepcopy(bars);changed['A'][assembled['session_dates'][1]]=dict(open='999',high='999',low='8',close='8')
        self.assertEqual(run(changed)['provider_audit'][0],rows[0])
        self.assertEqual(result['selection_account_states'][0]['account_state']['cash'],'1000')

    def test_invalid_clock_units_do_not_mutate_latch(self):
        for mode in ('clock','unit'):
            latch=MonthlyLatchedSma20();args=fixture({'A':[100]*20})
            if mode=='clock':args['observed_at']=args['signal_date']+'T15:59:00-05:00'
            else:args['base_target']['price_units']['A']='wrong'
            with self.assertRaises(ValueError):latch.target(actual_monthly_selection=True,**args)
            self.assertEqual(latch.latched,{})

    def test_wait_post_action_migrates_before_early_return_without_reset(self):
        assembled,bars,resolver=book_fixture()
        day=assembled['session_dates'][0]
        replies=iter([
            dict(status='READY',target_shares={'A':1},target_decision_date=day,selection={}),
            dict(status='READY',action='WAIT_POST_ACTION_MARK',orders=[],selection=None,
                 target_adjustments=[dict(security_id='A',new_security_id='B',target_after=1)]),
        ])
        seen=[]
        def off_resolver(**kwargs):
            inputs=resolver(**kwargs)
            for row in inputs['histories']['A']['closes'][:-1]:row['close']='20'
            return inputs
        def fake_book(**kwargs):
            callback=kwargs['order_provider']
            for date in assembled['session_dates'][:2]:
                seen.append(callback(decision_date=date,active_date=assembled['session_dates'][-1],
                                     state={'shares':{},'cash':'1000'}))
            return dict(status='COMPLETE',daily_ledger=[])
        with patch('backtest.monthly_latched_next_open.build_monthly_quantity_provider_v4',return_value=lambda **kwargs:next(replies)), patch('backtest.monthly_latched_next_open.run_next_open_book',side_effect=fake_book):
            run_monthly_latched_next_open(assembled=assembled,ohlc=bars,initial_cash='1000',
                fee_bps='0',slippage_bps='0',history_resolver=off_resolver)
        self.assertEqual(seen[0]['status'],'READY')
        self.assertEqual(seen[1]['action'],'WAIT_POST_ACTION_MARK')
        self.assertEqual(seen[1]['latch_state'],{'B':True})
        self.assertEqual(seen[1]['latch_monthly_decision_date'],day)
        self.assertEqual(seen[1]['latch_migration']['before'],{'A':True})

    def test_real_second_selection_uses_branch_cash_and_unlocks(self):
        assembled,bars,resolver=book_fixture();day=assembled['session_dates'][-2]
        payload=deepcopy(assembled['monthly_inputs'][0]);payload['decision_date']=day
        payload['search_arguments'].update(decision_date=day,quote_as_of=day,prices={'A':'12'})
        payload['valuation_quotes'][0].update(as_of=day,price='12')
        assembled['monthly_inputs'].append(payload)
        result=run_monthly_latched_next_open(assembled=assembled,ohlc=bars,initial_cash='1000',
            fee_bps='0',slippage_bps='0',history_resolver=resolver)
        self.assertEqual(result['status'],'COMPLETE',result.get('reason'))
        self.assertEqual(len(result['selection_account_states']),2)
        state=result['selection_account_states'][-1]['account_state']
        self.assertEqual(state['shares']['A'],0)
        self.assertNotEqual(state['cash'],'1000')
        row=result['provider_audit'][-1]
        self.assertTrue(row['risk_overlay']['actual_monthly_reset'])
        self.assertGreater(row['target_shares']['A'],0)


if __name__=='__main__':unittest.main()
