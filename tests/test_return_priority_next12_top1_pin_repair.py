"""Tiny synthetic real TOP1/capital/provider/book wiring, no market data."""
import unittest,tempfile,json
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from scripts.return_priority_next12_top1_pin_repair import derive_input,SELECTOR
from scripts.return_priority_next12_monthly_comparison import execute_method
class RepairTests(unittest.TestCase):
 def fixture(self):
  day='2025-12-31';active='2026-01-02'
  args=dict(prices={'A':'10','B':'30'},metadata={'A':{'ticker':'AAA','issuer_id':'I'},'B':{'ticker':'BBB','issuer_id':'J'}},training_scenarios=[{'A':'1.1','B':'1.2'} for _ in range(12)],scenario_dates=[f'2025-{m:02d}-01' for m in range(1,13)],decision_date=day,entered_cash='20000',fee_bps=0,minimum_cash_buffer=0,max_objective_evaluations=8192,fixed_seed='fresh-quantity-20261014-v1',quote_as_of=day,price_basis='UNIT')
  pins={'raw':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':'b'*64}
  data=dict(ohlc={'A':{active:dict(open='10',high='11',low='9',close='10')},'B':{active:dict(open='30',high='31',low='29',close='30')}},source_hashes=pins)
  window=dict(decision_date=day,active_date=active,search_arguments=args,source_hashes=deepcopy(pins),valuation_quotes=[dict(security_id=s,price=p,as_of=day,price_basis='UNIT',source_references=['raw']) for s,p in args['prices'].items()])
  a=dict(session_dates=[day,active],monthly_inputs=[window],close_prices={'A':{day:'10'},'B':{day:'30'}},actions=[],provider_actions=[],cash_stock_merger_events=[],fractional_settlements={},price_source_references={'A':['raw'],'B':['raw']},distribution_events=[],distribution_fractional_cash_values={})
  return data,a
 def test_derived_only_pin_and_original_unchanged(self):
  data,_=self.fixture();old=deepcopy(data);r=derive_input(data,{'source_hashes':{SELECTOR:'c'*64}})
  self.assertEqual(data,old);self.assertEqual(r['ohlc'],old['ohlc']);r['source_hashes'].pop(SELECTOR);self.assertEqual(r,old)
  with self.assertRaises(ValueError):derive_input(derive_input(data,{'source_hashes':{SELECTOR:'c'*64}}),{'source_hashes':{SELECTOR:'c'*64}})
 def test_real_top1_wiring_missing_pin_then_repair(self):
  data,a=self.fixture()
  with tempfile.TemporaryDirectory() as tmp,patch('backtest.return_priority_fresh_cash_quantity_search.search_fresh_cash_quantities',side_effect=AssertionError('QUANTITY_MUST_NOT_RUN')):
   fail=execute_method('top1',data,a,Path(tmp)/'failed')
   self.assertFalse(fail['metrics']['complete_full_period']);self.assertEqual(fail['core_calls'],0)
   cb=json.loads((Path(tmp)/'failed/callback_2025-12-31.json').read_text(encoding='utf-8'))
   self.assertEqual(cb['response']['reason']['detail'],'Selector source pin required')
   derived=derive_input(data,{'source_hashes':{SELECTOR:'c'*64}})
   # Assembly copies the derived source closure into each monthly binding.
   a['monthly_inputs'][0]['source_hashes']=deepcopy(derived['source_hashes'])
   ok=execute_method('top1',derived,a,Path(tmp)/'repaired')
   self.assertTrue(ok['metrics']['complete_full_period']);self.assertEqual(ok['core_calls'],0);self.assertEqual(ok['selector_calls'],1);self.assertEqual(ok['capital_decision_attempts'],1)
   cb=json.loads((Path(tmp)/'repaired/callback_2025-12-31.json').read_text(encoding='utf-8'))
   self.assertEqual(cb['response']['target_shares'],{'B':666})
   self.assertEqual(ok['book_calls'],1)
if __name__=='__main__':unittest.main()
