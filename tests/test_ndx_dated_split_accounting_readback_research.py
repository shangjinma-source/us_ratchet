"""Synthetic frozen-engine ledgers only; no saved historical account readback."""
from copy import deepcopy
import unittest
from backtest import ndx_dated_split_accounting_readback_research as m
from test_ndx_dated_account_execution_20261003 import state,core as fixture_engine


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=state()
        cls.execution=fixture_engine.execute_engine(cls.state)
        cls.cancel_state=deepcopy(cls.state)
        cls.cancel_state['account']['corporate_actions'][0]['session']=cls.cancel_state['calendar'][1]
        cls.cancel_execution=fixture_engine.execute_engine(cls.cancel_state)

    def test_full_synthetic_split_ledger_and_mutation_rejection(self):
        a=self.state['account'];e=self.execution
        r=m.audit_account(execution=e,account_input=a)
        self.assertEqual(r['split_event_count'],2)
        self.assertEqual(r['execution_statuses'],['FILLED'])
        self.assertEqual(r['terminal_shares']['security:1:BKNG'],e['daily'][1]['shares']['security:1:BKNG']*25)
        self.assertEqual(r['terminal_shares']['security:2:KLAC'],e['daily'][1]['shares']['security:2:KLAC']*10)
        for kind in ('double','cash','event','risk','fee'):
            bad=deepcopy(e)
            if kind=='double':bad['daily'][-1]['shares']['security:1:BKNG']*=25
            elif kind=='cash':bad['corporate_actions'][0]['cash_usd']+=1
            elif kind=='event':bad['corporate_actions'][0]['applied_events'][0]['post_shares']+=1
            elif kind=='risk':bad['daily'][-1]['risk']['checks']['MIN_SINGLE_WEIGHT']=False
            else:bad['trades'][0]['transaction_cost_usd']+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.audit_account(execution=bad,account_input=a)

    def test_entry_split_cancels_pending_without_replacement_buy(self):
        e=self.cancel_execution;a=self.cancel_state['account']
        r=m.audit_account(execution=e,account_input=a)
        self.assertEqual(r['execution_statuses'],['CANCELLED_SPLIT'])
        self.assertEqual(r['trade_count'],0);self.assertEqual(r['terminal_shares'],{})
        self.assertEqual(r['terminal_cash_exact'],dict(numerator='25000',denominator='1'))
        for kind in ('pending','cancel','shares'):
            bad=deepcopy(e)
            if kind=='pending':bad['corporate_actions'][0]['pending_plan']=bad['decisions'][0]
            elif kind=='cancel':bad['executions']=[]
            else:bad['corporate_actions'][0]['shares']['security:1:BKNG']=25
            with self.subTest(kind=kind),self.assertRaises((ValueError,KeyError)):m.audit_account(execution=bad,account_input=a)

    def test_no_plan_preserved_without_claiming_global_infeasibility(self):
        a=deepcopy(self.state['account']);e=deepcopy(self.execution);a['corporate_actions']=[];e['corporate_actions']=[]
        d=e['decisions'][0]
        for k in ('desired_shares','delta','decision_risk','projected_cash_usd','projected_fees_usd'):d.pop(k)
        d.update(status='NO_PLAN',projection=dict(search_complete=False,feasible_projection_found=False))
        e['executions']=[];e['trades']=[]
        first=deepcopy(e['daily'][0]);e['daily']=[dict(deepcopy(first),session=day) for day in a['matrices']['close']['index']]
        e['summary'].update(terminal_value_usd=25000.,path_return_net=0.,path_max_drawdown=0.,all_cash_session_count=127)
        r=m.audit_account(execution=e,account_input=a)
        self.assertEqual(r['decision_status'],'NO_PLAN');self.assertFalse(r['integer_search_independently_recomputed'])
        e['decisions'][0]['projection'].update(search_complete=True,feasible_projection_found=True)
        with self.assertRaises(ValueError):m.audit_account(execution=e,account_input=a)


if __name__=='__main__':unittest.main()
