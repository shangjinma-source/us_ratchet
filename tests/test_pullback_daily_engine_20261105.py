import unittest
from docs.candidates.pullback_daily_engine_20261105 import run_account
from fractions import Fraction as F

class PullbackTests(unittest.TestCase):
    def run_case(self,bar,variant='full_trail',stop='98',nextbar=None,gate=None,initial_cash='20000'):
        days=['2026-01-02','2026-01-05']+(['2026-01-06'] if nextbar else [])
        bars={'A':{'2026-01-02':dict(open='100',high='101',low='98',close='100'),'2026-01-05':bar}}
        if nextbar:bars['A']['2026-01-06']=nextbar
        signals={d:dict(eligible=['A'],ema9={'A':'97'},entries=[dict(security_id='A',stop=stop,rank_return='1')]) for d in days[:-1]}
        return run_account(session_dates=days,ohlc=bars,signals=signals,actions=[],dividend_events=[],gate=gate or (lambda *a:dict(admitted=True)),variant=variant,initial_cash=initial_cash)
    def test_ambiguous_stop_first(self):
        result=self.run_case(dict(open='100',high='110',low='97',close='106'),'half_3r')
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual([x['reason'] for x in result['order_log']],['PRIOR_BAR_PULLBACK','STOP_INTRADAY'])
        self.assertEqual(F(result['order_log'][1]['price']),F(98)*F(1999,2000))
        self.assertLessEqual(F(result['order_log'][0]['planned_risk']),100)
    def test_gap_cancels_new_entry(self):
        result=self.run_case(dict(open='105',high='106',low='104',close='105'))
        self.assertEqual(result['order_log'],[])
    def test_existing_gap_uses_open(self):
        result=self.run_case(dict(open='100',high='101',low='99',close='100'),nextbar=dict(open='90',high='92',low='88',close='91'))
        self.assertEqual(result['order_log'][1]['reason'],'STOP_GAP');self.assertEqual(F(result['order_log'][1]['price']),F(90)*F(1999,2000))
    def test_invalid_entry_does_not_require_candidate_action_admission(self):
        calls=[]
        def gate(previous,day,shares,entries):
            calls.append(entries);return dict(admitted=not entries)
        result=self.run_case(dict(open='105',high='106',low='104',close='105'),gate=gate)
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual(calls,[[]])
    def test_actual_entry_gate_uses_positive_integer_quantity(self):
        calls=[]
        def gate(previous,day,shares,entries):
            calls.append(entries);return dict(admitted=True)
        result=self.run_case(dict(open='100',high='101',low='99',close='100'),gate=gate)
        self.assertEqual(calls[1][0]['quantity'],result['order_log'][0]['quantity'])
    def test_one_share_no_partial_completion(self):
        result=self.run_case(dict(open='100',high='120',low='99.95',close='110'),'half_3r',stop='99.9',initial_cash='150')
        self.assertEqual(len(result['order_log']),1);self.assertFalse(result['daily_ledger'][0]['positions']['A']['partial_taken'])
    def test_half_profit_keeps_remainder(self):
        result=self.run_case(dict(open='100',high='110',low='99',close='108'),'half_3r')
        buy,sell=result['order_log'];self.assertEqual(sell['reason'],'HALF_3R');self.assertEqual(sell['quantity'],buy['quantity']//2)

if __name__=='__main__':unittest.main()

