from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from core.strategy_account_ledger import create_account,apply_event,canonical
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.strategy_account_target_inputs import build_target_inputs
from test_current_quantity_v2_monthly_training import fixture


def setup(folder):
 _,_,package,_=fixture(folder)
 state=create_account('real-strategy')
 def add(event):
  nonlocal state
  state,_=apply_event(state,event,expected_revision=state['revision'])
 add(dict(event_id='fill',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=2,price='10',fees='0',executed_at='2026-10-30T19:00:00Z'))
 add(dict(event_id='cash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'))
 add(dict(event_id='open',kind='ORDER_OPEN',order_id='buy',security_id='B',side='BUY',quantity=2,limit_price='10',fee_per_share='0'))
 add(dict(event_id='confirm',kind='CASH_CONFIRM',amount='80',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
 historical=compile_saved_training(package,'manifest.json')['input']['search_arguments']
 now='2026-11-02T15:00:00+00:00';marks={sid:dict(security_id=sid,currency='USD',price=price,price_basis='CURRENT_UNIT',observed_at=now,source_references=['calendar-source']) for sid,price in [('A','20'),('B','10')]}
 def put(path,value):
  raw=canonical(value);package['files'][path]=raw;package['source_hashes'][path]=sha256(raw).hexdigest()
 put('current-marks.json',marks)
 review=dict(schema='STRATEGY_TARGET_UNIT_REVIEW_V1',status='CONDITIONAL_CURRENT_UNITS_REVIEWED',account_revision=state['revision'],training_manifest_sha256=package['source_hashes']['manifest.json'],historical_search_arguments_sha256=sha256(canonical(historical)).hexdigest(),marks_sha256=package['source_hashes']['current-marks.json'],training_cutoff_date='2026-10-30',training_closed_at='2026-10-30T20:00:00+00:00',reviewed_at=now,source_references=['calendar-source'],unresolved=[],pending_rights=[],securities={})
 for sid,mark in marks.items():
  review['securities'][sid]=dict(security_id=sid,current_price_basis='CURRENT_UNIT',current_mark_sha256=sha256(canonical(mark)).hexdigest(),historical_price_basis=historical['price_basis'],training_manifest_sha256=package['source_hashes']['manifest.json'],historical_scenarios_usable_in_current_units=True,held_quantities_in_current_units=True,covered_through=now,source_references=['calendar-source'])
 put('review.json',review)
 return dict(state=state,source_package=package,manifest_path='manifest.json',marks_path='current-marks.json',unit_review_path='review.json',now=now,maximum_mark_age_seconds=120)

class TargetInputTests(unittest.TestCase):
 def test_actual_raw_compiler_current_capital_and_pending_no_mutation(self):
  with TemporaryDirectory() as d:
   args=setup(d);before=deepcopy(args);result=build_target_inputs(**args);b=result['binding']
   self.assertEqual(b['strategy_equity'],'140');self.assertEqual(b['strategy_shares'],{'A':2})
   self.assertEqual(b['training_cutoff_date'],'2026-10-30');self.assertEqual(b['valuation_date'],'2026-11-02')
   self.assertEqual(b['search_arguments']['prices'],{'B':'10'});self.assertEqual(b['search_arguments']['entered_cash'],'140')
   self.assertEqual(b['historical_search_arguments']['prices']['B'],'352')
   self.assertEqual(b['search_arguments']['training_scenarios'],b['historical_search_arguments']['training_scenarios'])
   self.assertEqual(b['execution_context']['reserved_cash'],'20');self.assertEqual(b['execution_context']['available_cash'],'80')
   self.assertEqual(len(b['execution_context']['pending_orders']),1);self.assertEqual(result['core_calls'],0);self.assertEqual(args,before)
 def test_missing_held_stale_future_and_unit_binding_rejected(self):
  for mode in ('missing','stale','future','unit','traininghash','pendingrights','unclosed','cash'):
   with self.subTest(mode=mode),TemporaryDirectory() as d:
    a=setup(d);p=a['source_package'];review=json.loads(p['files']['review.json'])
    if mode=='missing':
     marks=json.loads(p['files']['current-marks.json']);del marks['A'];p['files']['current-marks.json']=canonical(marks);p['source_hashes']['current-marks.json']=sha256(p['files']['current-marks.json']).hexdigest()
    elif mode=='stale':a['now']='2026-11-02T15:03:00+00:00'
    elif mode=='future':a['now']='2026-10-29T15:00:00+00:00'
    elif mode=='unit':review['securities']['A']['current_mark_sha256']='0'*64
    elif mode=='traininghash':review['historical_search_arguments_sha256']='0'*64
    elif mode=='pendingrights':review['pending_rights']=['unresolved']
    elif mode=='unclosed':review['training_closed_at']='2026-11-02T16:00:00Z'
    else:
     s=a['state'];a['state'],_=apply_event(s,dict(event_id='another-fill',kind='FILL',order_id='buy',quantity=1,price='10',fees='0',executed_at='2026-11-02T14:00:00Z'),expected_revision=s['revision'])
    p['files']['review.json']=canonical(review);p['source_hashes']['review.json']=sha256(p['files']['review.json']).hexdigest()
    with self.assertRaises(ValueError):build_target_inputs(**a)

if __name__=='__main__':unittest.main()
