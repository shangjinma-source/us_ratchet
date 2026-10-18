from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timedelta
from hashlib import sha256
from types import SimpleNamespace
import json,unittest
from core.strategy_account_ledger import canonical
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.strategy_account_target_inputs import build_target_inputs
from data.current_research_capital_decision_v2 import REQUIRED_PINS
from data.current_quantity_v2_paper_action_sources import daily_url
from test_strategy_account_target_inputs import setup

class ProviderTests(unittest.TestCase):
 def test_valuation_allows_unconfirmed_cash_without_selector_or_limit_evaluation(self):
  from unittest.mock import Mock
  from core.strategy_account_ledger import apply_event,create_account,replay
  with TemporaryDirectory() as d:
   provider,state,_,_=self.fixture(d)
   events=[row['payload'] for row in state['events']]
   for event in events:
    if event['kind']=='ORDER_OPEN':event['identity_evidence']=dict(ticker='BBB',security_id='B',source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
   state=replay(state['account_id'],events)
   state,_=apply_event(state,dict(event_id='valuation-fill',kind='FILL',order_id='buy',quantity=1,price='10',fees='0',executed_at='2026-11-02T14:59:00Z'),expected_revision=state['revision'])
   self.assertFalse(state['cash_confirmation_valid'])
   provider.limits=Mock(side_effect=AssertionError('valuation must never evaluate limits'))
   marks=provider.valuation(state)
   self.assertEqual(set(marks),{sid for sid,q in state['shares'].items() if q})
   provider.limits.assert_not_called()
   provider.training=Mock(side_effect=AssertionError('empty holdings need no training'))
   self.assertEqual(provider.valuation(create_account('empty')),{} )
 def fixture(self,d,mode=None):
  args=setup(d);root=Path(d)/'sources';p=args['source_package']
  for path,raw in p['files'].items():
   file=root/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
  runtime_pins={}
  for path in REQUIRED_PINS:
   raw=(Path(__file__).resolve().parents[1]/path).read_bytes()
   destination=root/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
   runtime_pins[path]=sha256(raw).hexdigest()
  now=[datetime.fromisoformat(args['now'])]
  class Identity:
   def __call__(self,ticker):return dict(ticker=ticker,security_id={'AAA':'A','BBB':'B'}[ticker],source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
   def _read(self,path,h):return b'id'
  # Existing synthetic A fill has no persisted identity; bind candidate-independent held identity for this transport fixture.
  identity=dict(ticker='AAA',security_id='A',source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
  from core.strategy_account_ledger import replay
  events=[e['payload'] for e in args['state']['events']];events[0]['identity_evidence']=identity;state=replay('real-strategy',events)
  def raw(ticker):
   start=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp());last=start+1800
   if mode=='older_selection':last-=123
   return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),timestamp=[last-60],indicators=dict(quote=[dict(open=[10],high=[11],low=[9],close=[10],volume=[10])]))])))
  realmarket=StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=raw,clock=lambda:now[0],max_mark_age=900 if mode=='older_selection' else 120)
  def market(**kwargs):
   value=realmarket.capture(**kwargs)
   if mode=='domain':del value['marks']['A']
   if mode=='marks':value['marks']['B']['price']='1000'
   if mode=='conflict':value['files']['calendar-source']=b'other';value['source_hashes']['calendar-source']=sha256(b'other').hexdigest()
   return value
  def actions(t,start,end):
   if mode=='action':raise OSError('no transport')
   return dict(status=200,url=daily_url(t,start,end),body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=t,currency='USD',instrumentType='EQUITY'),events={})]))))
  action=StrategyAccountActionCapture(fetch=actions,rss_fetch=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'),clock=lambda:now[0])
  def limits(**kwargs):
   self.assertIn(kwargs['target_quantities'],(None,{'B':2}));self.assertEqual(kwargs['quote_domain'],{'A','B'} if kwargs['target_quantities'] is None else None)
   if mode=='late':now[0]+=timedelta(seconds=121)
   return {'limits':{sid:dict(security_id=sid,price_basis=m['price_basis'],observed_at=m['observed_at'],buy='9',sell='11') for sid,m in kwargs['market_capture']['marks'].items()}}
  provider=StrategyAccountEvidenceProvider(root=root,manifest_path='manifest.json',manifest_sha256=p['source_hashes']['manifest.json'],training_closed_at='2026-10-30T20:00:00Z',market_capture=SimpleNamespace(capture=market),action_capture=action,limits_builder=limits,output_root=Path(d)/'capture',runtime_pins=runtime_pins,clock=lambda:now[0])
  return provider,state,now,root
 def test_actual_compiler_market_actions_review_and_target_inputs(self):
  with TemporaryDirectory() as d:
   provider,state,now,_=self.fixture(d);output=provider(state)
   inputs=build_target_inputs(state=state,now=now[0].isoformat(),maximum_mark_age_seconds=120,**{k:v for k,v in output.items() if k!='limits'})
   self.assertEqual(inputs['status'],'INPUTS_READY_NOT_EXECUTED');self.assertEqual(set(inputs['binding']['marks']),{'A','B'})
   for path,expected in provider.runtime_pins.items():
    self.assertEqual(inputs['binding']['source_hashes'][path],expected)
    self.assertEqual(sha256(output['source_package']['files'][path]).hexdigest(),expected)
   self.assertEqual(len(list((Path(d)/'capture').glob('*/complete.json'))),1)
 def test_runtime_pins_required_copied_and_source_drift_rejected(self):
  with TemporaryDirectory() as d:
   provider,state,now,root=self.fixture(d)
   options=dict(root=root,manifest_path=provider.manifest_path,manifest_sha256=provider.manifest_hash,
       training_closed_at=provider.closed,market_capture=provider.market,action_capture=provider.actions,
       limits_builder=provider.limits,output_root=provider.output,clock=lambda:now[0])
   with self.assertRaisesRegex(ValueError,'SELECTION_RUNTIME_PINS_REQUIRED'):
    StrategyAccountEvidenceProvider(**options)
   pins=dict(provider.runtime_pins);missing=dict(pins);missing.pop(REQUIRED_PINS[0])
   with self.assertRaisesRegex(ValueError,'SELECTION_RUNTIME_PINS_REQUIRED'):
    StrategyAccountEvidenceProvider(**options,runtime_pins=missing)
   copied=StrategyAccountEvidenceProvider(**options,runtime_pins=pins)
   pins[REQUIRED_PINS[0]]='0'*64
   self.assertNotEqual(copied.runtime_pins[REQUIRED_PINS[0]],pins[REQUIRED_PINS[0]])
   manifest_before=(root/provider.manifest_path).read_bytes()
   copied.training()
   self.assertEqual((root/provider.manifest_path).read_bytes(),manifest_before)
   (root/REQUIRED_PINS[0]).write_bytes(b'changed runtime source')
   with self.assertRaisesRegex(ValueError,'TRAINING_SOURCE_CHANGED'):copied.selection(state)
   self.assertFalse(provider.output.exists(),'Reject source drift before fetching or writing evidence')
 def test_assembled_runtime_pins_reach_actual_tiny_selector(self):
  from data.strategy_account_target_decision import decide_target
  with TemporaryDirectory() as d:
   provider,state,now,_=self.fixture(d)
   evidence=provider.selection(state)
   result=decide_target(state=state,now=now[0].isoformat(),maximum_mark_age_seconds=900,**evidence)
   self.assertEqual(result['status'],'TARGET_READY');self.assertEqual(result['core_calls'],1)
   for path,expected in provider.runtime_pins.items():
    self.assertEqual(result['payload']['input_binding']['source_hashes'][path],expected)
 def test_older_selection_marks_cannot_escape_execution_gate(self):
  with TemporaryDirectory() as d:
   provider,state,now,_=self.fixture(d,'older_selection')
   evidence=provider.selection(state)
   inputs=build_target_inputs(state=state,now=now[0].isoformat(),maximum_mark_age_seconds=900,**evidence)
   self.assertEqual(inputs['status'],'INPUTS_READY_NOT_EXECUTED')
   payload=dict(input_binding=inputs['binding'],input_id=inputs['input_id'],target_quantities={'B':2})
   target={'payload':{'decision':dict(status='TARGET_READY',payload=payload,decision_id=sha256(canonical(payload)).hexdigest())}}
   with self.assertRaisesRegex(ValueError,'LAST_QUOTE_STALE'):provider.execution(state,target)
   with self.assertRaisesRegex(ValueError,'LAST_QUOTE_STALE'):provider(state)

 def test_selection_does_not_evaluate_entry_limits(self):
  from unittest.mock import Mock
  with TemporaryDirectory() as d:
   provider,state,now,_=self.fixture(d)
   provider.limits=Mock(side_effect=AssertionError('selection must not evaluate BUY minutes'))
   evidence=provider.selection(state)
   self.assertEqual(set(evidence),{'source_package','manifest_path','marks_path','unit_review_path'})
   inputs=build_target_inputs(state=state,now=now[0].isoformat(),maximum_mark_age_seconds=120,**evidence)
   self.assertEqual(set(inputs['binding']['marks']),{'A','B'})
   provider.limits.assert_not_called()

 def test_execution_reuses_target_without_compiler_and_ignores_client_clock(self):
  from unittest.mock import patch
  from data.strategy_account_target_inputs import build_target_inputs
  from core.strategy_account_ledger import apply_event
  with TemporaryDirectory() as d:
   provider,state,now,_=self.fixture(d);evidence=provider(state)
   inputs=build_target_inputs(state=state,now=now[0].isoformat(),maximum_mark_age_seconds=120,**{k:v for k,v in evidence.items() if k!='limits'})
   payload=dict(input_binding=inputs['binding'],input_id=inputs['input_id'],target_quantities={'B':2})
   decision=dict(status='TARGET_READY',payload=payload,decision_id=sha256(canonical(payload)).hexdigest())
   target={'payload':{'decision':decision}}
   state,_=apply_event(state,dict(event_id='partial',kind='FILL',order_id='buy',quantity=1,price='10',fees='0',executed_at='2026-11-02T14:59:00Z'),expected_revision=state['revision'])
   state,_=apply_event(state,dict(event_id='reconfirm',kind='CASH_CONFIRM',amount='80',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=state['revision'])
   from functools import partial
   from data.strategy_account_execution_limits import build_execution_limits
   from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
   caps=LazyPullbackCapStore(Path(d)/'daily-caps.db',clock=lambda:now[0].isoformat(),max_history_rows=32,max_history_bytes=1024*1024)
   provider.limits=partial(build_execution_limits,cap_store=caps)
   with patch('data.strategy_account_evidence_provider.compile_saved_training',side_effect=AssertionError('no compile')):
    result=provider.execution(state,target,now='2099-01-01T00:00:00Z')
   self.assertEqual(set(result),{'marks','limits'});self.assertEqual(set(result['marks']),{'A','B'})
   self.assertEqual(result['marks']['B']['captured_at'],now[0].isoformat())
   self.assertEqual(state['orders']['buy']['remaining_quantity'],1)
   self.assertFalse(result['limits']['A']['buy_evaluated'])

 def test_failures_reject_without_success_receipt(self):
  for mode in ('training','action','domain','marks','conflict','late'):
   with self.subTest(mode=mode),TemporaryDirectory() as d:
    provider,state,_,root=self.fixture(d,mode)
    if mode=='training':(root/'B.daily').write_bytes(b'changed')
    with self.assertRaises(ValueError):provider(state)
    self.assertEqual(list((Path(d)/'capture').glob('*/complete.json')),[])

if __name__=='__main__':unittest.main()
