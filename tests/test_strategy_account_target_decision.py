from copy import deepcopy
from hashlib import sha256
import json,unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from core.strategy_account_ledger import create_account,apply_event,canonical
from data.current_research_capital_decision_v2 import REQUIRED_PINS
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.strategy_account_target_decision import decide_target,preview_target,validate_result
from data.strategy_account_preview import preview_scoped_account
from test_strategy_account_target_inputs import setup

ROOT=Path(__file__).resolve().parents[1]

def fixture(folder,partial=False):
 a=setup(folder);p=a['source_package'];state=create_account('strategy')
 def event(e):
  nonlocal state
  state,_=apply_event(state,e,expected_revision=state['revision'])
 event(dict(event_id='open',kind='ORDER_OPEN',order_id='sndk-14',security_id='B',side='BUY',quantity=14,limit_price='1322.21',fee_per_share='0'))
 if partial:event(dict(event_id='fill',kind='FILL',order_id='sndk-14',quantity=5,price='1322.21',fees='0',executed_at='2026-11-02T14:59:00Z'))
 # Hypothetical fixture cash, not a statement of the user's balance. Fees zero explicitly.
 event(dict(event_id='cash',kind='CASH_CONFIRM',amount='500',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
 a['state']=state
 for path in REQUIRED_PINS:
  raw=(ROOT/path).read_bytes();p['files'][path]=raw;p['source_hashes'][path]=sha256(raw).hexdigest()
 # Bind the synthetic issuer ticker to SNDK; this is not real market data.
 raw=json.loads(p['files']['B.daily']);raw['chart']['result'][0]['meta']['symbol']='SNDK'
 p['files']['B.daily']=canonical(raw);p['source_hashes']['B.daily']=sha256(p['files']['B.daily']).hexdigest()
 manifest=json.loads(p['files']['manifest.json'].decode().replace('BBB','SNDK'));manifest['source_hashes']['B.daily']=p['source_hashes']['B.daily']
 p['files']['manifest.json']=canonical(manifest);p['source_hashes']['manifest.json']=sha256(p['files']['manifest.json']).hexdigest()
 historical=compile_saved_training(p,'manifest.json')['input']['search_arguments']
 marks=json.loads(p['files']['current-marks.json']);marks={'B':dict(marks['B'],price='1322.21')}
 p['files']['current-marks.json']=canonical(marks);p['source_hashes']['current-marks.json']=sha256(p['files']['current-marks.json']).hexdigest()
 review=json.loads(p['files']['review.json']);review.update(account_revision=state['revision'],marks_sha256=p['source_hashes']['current-marks.json'],training_manifest_sha256=p['source_hashes']['manifest.json'],historical_search_arguments_sha256=sha256(canonical(historical)).hexdigest())
 review['securities']={'B':review['securities']['B']};review['securities']['B']['training_manifest_sha256']=p['source_hashes']['manifest.json'];review['securities']['B']['current_mark_sha256']=sha256(canonical(marks['B'])).hexdigest()
 p['files']['review.json']=canonical(review);p['source_hashes']['review.json']=sha256(p['files']['review.json']).hexdigest()
 limits={'B':dict(security_id='B',price_basis='CURRENT_UNIT',observed_at=a['now'],buy='1322.21',sell='1322.21')}
 return a,limits

class DecisionTests(unittest.TestCase):
 def test_real_v2_pending_14_and_partial_fill_do_not_duplicate(self):
  for partial in (False,True):
   with self.subTest(partial=partial),TemporaryDirectory() as d:
    args,limits=fixture(d,partial);before=deepcopy(args);result=decide_target(**args)
    self.assertEqual(result['payload']['target_quantities'],{'B':14});self.assertEqual(result['core_calls'],1)
    difference=preview_target(decision=result,state=args['state'],limits=limits,now=args['now'],maximum_mark_age_seconds=120,execution_fee_bps='0',legacy_shares={'B':80})
    self.assertEqual(difference['new_orders'],[]);self.assertEqual(difference['spendable_cash'],'500')
    self.assertEqual(result['payload']['input_binding']['strategy_equity'],'950547/50')
    self.assertEqual(args,before)
 def test_reverse_target_requires_cancel_and_stale_target_rejected(self):
  with TemporaryDirectory() as d:
   args,limits=fixture(d);decision=decide_target(**args)
   difference=preview_scoped_account(state=args['state'],legacy_shares={},marks={'B':decision['payload']['input_binding']['marks']['B']},limits=limits,target_quantities={},now=args['now'],maximum_mark_age_seconds=120,fee_bps='0')
   self.assertEqual(difference['status'],'CANCEL_THEN_RECALCULATE');self.assertEqual(difference['new_orders'],[])
   changed,_=apply_event(args['state'],dict(event_id='newcash',kind='CASH_CONFIRM',amount='501',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=args['state']['revision'])
   with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_TARGET'):
    preview_target(decision=decision,state=changed,limits=limits,now=args['now'],maximum_mark_age_seconds=120,execution_fee_bps='0',legacy_shares={})
   with self.assertRaisesRegex(ValueError,'STALE_OR_FUTURE_MARK'):
    preview_target(decision=decision,state=args['state'],limits=limits,now='2026-11-02T15:03:00Z',maximum_mark_age_seconds=120,execution_fee_bps='0',legacy_shares={})
 def test_result_arithmetic_and_core_pin_mutations_rejected(self):
  with TemporaryDirectory() as d:
   args,_=fixture(d);decision=decide_target(**args);p=decision['payload']
   for key,value in [('notional','1'),('fees','1'),('residual_cash','1'),('actual_weights',{'B':'1'})]:
    bad=deepcopy(p['search_result']);bad['selected'][key]=value
    with self.assertRaises(ValueError):validate_result(bad,p['input_binding']['search_arguments'])
   path=REQUIRED_PINS[0];args['source_package']['files'][path]+=b'\n';args['source_package']['source_hashes'][path]=sha256(args['source_package']['files'][path]).hexdigest()
   with self.assertRaisesRegex(ValueError,'V2_RUNTIME_SOURCE_CHANGED|MANIFEST_SOURCE_CHANGED'):decide_target(**args)

if __name__=='__main__':unittest.main()
