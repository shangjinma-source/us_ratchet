from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_dated_split_accounting_readback_research as pure
from scripts import ndx_dated_account_independent_readback_20261003 as wrapper
from test_ndx_dated_account_execution_20261003 import state,core as synthetic_engine
from test_ndx_dated_account_independent_readback_20261003 import fixture

class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=state();cls.e=synthetic_engine.execute_engine(cls.s)
    def test_independent_cash_terminal_and_complete_split_trace(self):
        a=self.s['account'];e=self.e;r=pure.audit_account(execution=e,account_input=a)
        buys=e['trades'];spent=sum(Fraction(str(t['share_delta']))*Fraction(str(t['price_usd']))+Fraction(str(t['transaction_cost_usd'])) for t in buys)
        actual=Fraction(int(r['terminal_cash_exact']['numerator']),int(r['terminal_cash_exact']['denominator']))
        self.assertLessEqual(abs(actual-(25000-spent)),Fraction(1,10**7));self.assertFalse(r['integer_search_independently_recomputed'])
        for kind in ('delete_action','phantom_trade','risk_date','duplicate_fill'):
            bad=deepcopy(e)
            if kind=='delete_action':bad['corporate_actions'].pop()
            elif kind=='phantom_trade':bad['trades'].append(deepcopy(bad['trades'][0]))
            elif kind=='risk_date':bad['daily'][-1]['risk_chain_observation_dates'][next(iter(bad['daily'][-1]['shares']))]='2026-09-21'
            else:bad['executions'].append(deepcopy(bad['executions'][0]))
            with self.subTest(kind=kind),self.assertRaises(ValueError):pure.audit_account(execution=bad,account_input=a)
    def test_normalized_target_and_split_cash_do_not_change_saved_input(self):
        before=deepcopy(self.s['account']);pure.audit_account(execution=self.e,account_input=before);self.assertEqual(before,self.s['account'])
        for field in ('split_cash_flow_usd','split_fees_usd'):
            bad=deepcopy(self.e);bad['corporate_actions'][0][field]=1
            with self.assertRaises(ValueError):pure.audit_account(execution=bad,account_input=before)
    def test_wrapper_terminal_semantics_and_links(self):
        for kind in ('runtime','post_drift','boolean_count','shared_control'):
            a=fixture()
            if kind=='runtime':a[2]['runtime']={'changed':True}
            elif kind=='post_drift':a[1]['error']={'source':'changed'}
            elif kind=='boolean_count':a[2]['engine_call_attempt_count']=True
            else:a[7]['rows'][1]['common_incumbent_identity']='f'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):wrapper.validate_evidence(*a)
        a=fixture();a[2].update(status='ACCOUNT_EXCEPTION',account=None,error={'type':'Synthetic'},returned_account_count=0);a[1].update(status='ACCOUNT_EXCEPTION_NO_RETURNED_RESULT',error={'type':'Synthetic'})
        self.assertEqual(wrapper.validate_evidence(*a)[0],'ACCOUNT_EXCEPTION_NO_RETURNED_RESULT')
        a[1].update(status='VALIDATION_FAILURE_RECORDED',error={'type':'RuntimeDrift'})
        self.assertEqual(wrapper.validate_evidence(*a)[0],'VALIDATION_FAILURE_RECORDED')

if __name__=='__main__':unittest.main()
