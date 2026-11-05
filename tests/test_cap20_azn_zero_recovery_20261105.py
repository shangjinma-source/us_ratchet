import unittest,importlib.util
from pathlib import Path
from docs.candidates.cap20_azn_zero_recovery_20261105 import *
from backtest.return_priority_ads_conversion import ACCOUNT_MODEL
ROOT=Path(__file__).resolve().parents[1]
def event():return dict(type='ads_conversion',date=DAY,event_id=EVENT,security_id=OLD,new_security_id=NEW,new_shares='1',old_shares='2',delivery_model=ACCOUNT_MODEL,source_references=['fixture:official'])
def bar(p):return dict(open=p,high=p,low=p,close=p)
class Tests(unittest.TestCase):
 def test49_cancel_then_next_session_integer_exit_permanent_half(self):
  spec=importlib.util.spec_from_file_location('test_zero_book',ROOT/'backtest/historical_dividend_next_open_book_research.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);install_book_module(m)
  def provider(**kw):
   state=kw['state'];day=kw['decision_date'];active=kw['active_date'];sid=OLD if day=='2026-01-30' else NEW;q=state['shares'].get(sid,0)
   return dict(status='READY',orders=[dict(id=day,security_id=sid,side='SELL',quantity=q,decision_date=day,active_date=active,decision_mark='100')] if q else [])
  r=m.run_next_open_book(session_dates=['2026-01-30',DAY,'2026-02-03','2026-02-04'],ohlc={NEW:{DAY:bar('200'),'2026-02-03':bar('201'),'2026-02-04':bar('202')}},initial_cash='100',initial_shares={OLD:49},fee_bps='0',slippage_bps='5',order_provider=provider,events=[event()],account_model=ACCOUNT_MODEL,price_source_references={NEW:['fixture:quote']})
  self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['daily_ledger'][0]['cash'],'100');self.assertEqual(r['daily_ledger'][0]['shares'][NEW],24);validate_rights(r['distribution_rights']);self.assertEqual(F(r['cash']),100+24*F(201)*F(1999,2000));fills=[x for x in r['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED'];self.assertEqual([(x['date'],x['quantity']) for x in fills],[('2026-02-03',24)]);self.assertTrue(any(x['event']=='CANCELLED_ADS_CONVERSION' for x in r['order_log']))
 def test_missing_other_or_wrong_units_refused(self):
  r=dict(event_id=EVENT,kind=KIND,security_id=NEW,units='1/2',effective_date=DAY,origin='ADS_CONVERSION',tradable=False,payment_date=None,delivery_date=None)
  for rights in [[],[dict(r,units='0')],[dict(r,units='1/3')],[dict(r,event_id='other')],[r,r]]:
   with self.assertRaises(ValueError):validate_rights(rights)
  state=dict(cash='100',shares={NEW:24},distribution_rights=[r]);v=sizing_view(state);self.assertEqual(v['cash'],state['cash']);self.assertEqual(v['shares'],state['shares']);self.assertEqual(v['distribution_rights'],[]);self.assertEqual(len(state['distribution_rights']),1)
if __name__=='__main__':unittest.main()
