from copy import deepcopy
from datetime import date,timedelta
import unittest
from test_current_quantity_v2_simple253 import fixture
from test_simple253_cost_adapter import common
from scripts import run_simple253_cost as runner
from scripts import review_simple253_cost as reviewer

class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w,a,days=fixture();a.update(fee_bps='1',max_objective_evaluations=8192);c=common(w,a)
        day=days[-1];nextday=(date.fromisoformat(day)+timedelta(days=1)).isoformat()
        cls.assembled=dict(session_dates=[day,nextday],monthly_inputs=[dict(decision_date=day,search_arguments=c['search_arguments'],valuation_quotes=c['valuation_quotes'],source_hashes=c['source_hashes'])],close_prices={s:{day:p,nextday:p} for s,p in a['prices'].items()},provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements=[],price_source_references={s:['quote'] for s in a['prices']},distribution_events=[],distribution_fractional_cash_values={})
        cls.bars={s:{d:dict.fromkeys(('open','high','low','close'),p) for d in (day,nextday)} for s,p in a['prices'].items()}
        cls.training=[w];cls.pins={runner.CONTRACT:runner.CONTRACT_SHA}
        cls.outcome=runner.run_candidate(scenario='fee1_slippage10',assembled=cls.assembled,ohlc=cls.bars,training=cls.training,pins=cls.pins,progress=None,run_receipt_sha256='c'*64)
    def check(self,outcome):
        return reviewer.review(assembled=self.assembled,ohlc=self.bars,outcome=outcome,scenario='fee1_slippage10',expected_pins=self.pins,expected_receipt_sha256='c'*64,training_windows=self.training)
    def test_tiny_real_book(self):
        result=self.check(self.outcome)
        self.assertEqual(result['status'],'SIMPLE253_SAVED_EVIDENCE_VERIFIED')
        self.assertEqual(result['ledger_review']['status'],'SUPPORTED_SAVED_LEDGER_REPLAY_VERIFIED')
    def test_ranking_fee_quantity_and_binding_tamper(self):
        for kind in ('winner','ratio','fee','quantity','owncash','binding'):
            bad=deepcopy(self.outcome);sel=bad['provider_audit'][0]['selection']
            if kind=='winner':sel['search_result']['winner']='A'
            if kind=='ratio':sel['search_result']['endpoint_ratios']['B']='99'
            if kind=='fee':sel['search_result']['selected']['fees']='0'
            if kind=='quantity':sel['target_quantities']['B']=float(sel['target_quantities']['B'])
            if kind=='owncash':bad['selection_account_states'][0]['account_state']['cash']='123'
            if kind=='binding':sel['binding']['training_window_sha256']='f'*64
            with self.assertRaises(ValueError,msg=kind):self.check(bad)
    def test_fill_cash_and_missing_order(self):
        for kind in ('fee','cash_after','order'):
            bad=deepcopy(self.outcome)
            if kind=='order':bad['provider_audit'][0]['orders']=[]
            else:next(x for x in bad['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED')[kind]='999'
            with self.assertRaises(ValueError,msg=kind):self.check(bad)
    def test_nav_metrics_independently_checked(self):
        metrics=runner.summarize(self.outcome,self.assembled,self.bars)
        kwargs=dict(assembled=self.assembled,ohlc=self.bars,outcome=self.outcome,scenario='fee1_slippage10',expected_pins=self.pins,expected_receipt_sha256='c'*64,training_windows=self.training)
        result=reviewer.review(metrics=metrics,**kwargs)
        self.assertEqual(result['nav_review']['status'],'SAVED_STATE_NAV_AND_METRICS_VERIFIED')
        metrics['final_equity']='999'
        with self.assertRaises(ValueError):reviewer.review(metrics=metrics,**kwargs)

    def test_future_training_rejected(self):
        bad=deepcopy(self.training);bad[0]['training_dates'][-1]='2099-01-01'
        with self.assertRaises(ValueError):reviewer.review_selection(assembled=self.assembled,outcome=self.outcome,training_windows=bad,scenario='fee1_slippage10')

if __name__=='__main__':unittest.main()

