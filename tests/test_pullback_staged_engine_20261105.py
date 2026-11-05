import unittest
from docs.candidates.pullback_staged_engine_20261105 import run_account
class Tests(unittest.TestCase):
 def case(self,amount='20000',stop='98',bars=None):
  days=['2026-01-02','2026-01-05','2026-01-06','2026-01-07','2026-01-08'];values=bars or [('100','101','99','100'),('100','101','98.5','100'),('100','108','99','107'),('102','103','100','101')];ohlc={'A':{days[0]:dict(open='100',high='101',low='99',close='100')}}
  for d,vs in zip(days[1:],values):ohlc['A'][d]=dict(zip(('open','high','low','close'),vs))
  signals={d:dict(eligible=['A'],ema9={'A':'99' if d<days[3] else '101'},entries=[dict(security_id='A',stop=stop,rank_return='1')] if d==days[0] else []) for d in days[:-1]}
  return run_account(session_dates=days,ohlc=ohlc,signals=signals,actions=[],dividend_events=[],gate=lambda *a:dict(admitted=True),variant='staged_3r',initial_cash=amount)
 def test_initial_stop_until_profit_then_next_day_trail(self):
  b=self.case();self.assertEqual(b['status'],'COMPLETE');self.assertIn('A',b['daily_ledger'][1]['positions']);self.assertEqual([f['reason'] for f in b['order_log']],['PRIOR_BAR_PULLBACK','HALF_3R','STOP_INTRADAY']);self.assertEqual(b['order_log'][1]['date'],'2026-01-07');self.assertEqual(b['order_log'][2]['date'],'2026-01-08')
 def test_single_share_enters_stage_without_fake_half(self):
  b=self.case(amount='150',stop='99.9',bars=[('100','102','99.95','101'),('101','102','100','101'),('101','103','100','102'),('102','103','100','101')]);self.assertTrue(b['daily_ledger'][0]['positions']['A']['profit_stage']);self.assertFalse(b['daily_ledger'][0]['positions']['A']['partial_taken']);self.assertNotIn('HALF_3R',[f['reason'] for f in b['order_log']])
if __name__=='__main__':unittest.main()
