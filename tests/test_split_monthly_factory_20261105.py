"""Real raw compiler/native search/publication in disposable isolated runtime."""
from copy import deepcopy
from datetime import datetime,timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from hashlib import sha256
import json,unittest
from unittest.mock import patch
from core.strategy_account_ledger import canonical
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from docs.candidates import split_monthly_factory_20261105 as factory
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView,SavedFrontierProposalStore
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.current_quantity_v2_paper_action_sources import daily_url
from backtest.current_quantity_v2_risk_overlays import UNIT_SCHEMA
import test_split_evidence_provider_v1 as fixtures
ROOT=Path(__file__).resolve().parents[1]
def digest(raw):return sha256(raw).hexdigest()

class Tests(unittest.TestCase):
 def case(self,folder,inside=False,basis='AS_TRADED'):
  provider,oldstate,now=fixtures.SplitEvidenceProviderTests().case(folder)
  root=provider.root;manifest=json.loads((root/'manifest.json').read_bytes());days=manifest['training_dates'];splitday=days[126] if inside else (datetime.fromisoformat(days[0])-timedelta(days=1)).date().isoformat()
  q=splitday+'T13:30:00+00:00'
  action=dict(event_id='split-B',kind='SPLIT_CONFIRMED',action_id='split-B',security_id='B',ratio=8,effective_at=splitday+'T12:00:00+00:00',broker_confirmed_at=q,old_unit_id='old',new_unit_id='new',evidence_sha256='a'*64)
  store=SplitStrategyAccountStore(root/'data/strategy_account/real_strategy.sqlite3',clock=lambda:now[0]);store.initialize('real-strategy-account-v1',operation_id='init')
  # Existing B order is cancelled by the actual split event. A remains unrelated.
  for row in oldstate['events']:
   event=row['payload']
   if event['kind'] not in {'SPLIT_CONFIRMED','CASH_CONFIRM','ORDER_OPEN'}:store.append(event,expected_revision=store.read()['revision'])
  store.append(action,expected_revision=store.read()['revision'])
  store.append(dict(event_id='cash-new',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),expected_revision=store.read()['revision'])
  raw=json.loads((root/'B.daily').read_bytes());series=raw['chart']['result'][0];series['meta']['exchangeName']='NMS'
  series['events']={}
  if inside:
   epoch=int(datetime.fromisoformat(q).timestamp());series['events']['splits']={str(epoch):dict(date=epoch,numerator=8,denominator=1,splitRatio='8:1')}
  if inside and basis=='SPLIT_ADJUSTED_TO_CURRENT_UNIT':
   for field in ('open','high','low','close'):series['indicators']['quote'][0][field]=[v/8 if i<126 else v for i,v in enumerate(series['indicators']['quote'][0][field])]
  body=canonical(raw);(root/'B.daily').write_bytes(body);manifest['source_hashes']['B.daily']=digest(body)
  row=manifest['candidates'][0];row['price_coordinate_factors']=([dict(date=splitday,factor='8',source_references=['calendar-source'])] if inside and basis!='AS_TRADED' else [])
  row['true_share_events']=([dict(date=splitday,ratio='8',source_references=['calendar-source'])] if inside else [])
  rawmanifest=canonical(manifest);(root/'manifest.json').write_bytes(rawmanifest)
  calendar=dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[dict(date=d,open=d+'T13:30:00+00:00',close=d+'T20:00:00+00:00') for d in sorted(set(days+[splitday]))])
  timing_body=b'controlled actual tradability';review=dict(schema='SPLIT_THREE_CLOCK_EXECUTION_CONTENT_V2',action_id=action['action_id'],recorded_action_sha256=digest(canonical(action)),distribution_at=action['effective_at'],quote_unit_effective_at=q,broker_tradable_at=q,tradable_evidence_received_at=q,tradable_evidence_semantics='OBSERVED_ACTUALLY_TRADABLE_NOT_FUTURE_NOTICE',clock_source_references={k:['timing'] for k in ('distribution_at','quote_unit_effective_at','broker_tradable_at','tradable_evidence_received_at')})
  timing=dict(review=review,source_hex={'timing':timing_body.hex()},source_hashes={'timing':digest(timing_body)},calendar=calendar,calendar_sha256=digest(canonical(calendar)))
  inputs=dict(base_target=dict(monthly_decision_date=days[0],quantities={'B':1},price_units={'B':'new'},origin_reference='controlled training review'),signal_date=days[-1],observed_at='2026-11-02T14:00:00+00:00',session_dates=days,session_close_times=dict(review_reference='controlled calendar',closes={d:d+'T20:00:00+00:00' for d in days}),histories={'B':dict(source_reference='raw',closes=[],units=dict(schema=UNIT_SCHEMA,unit_asof=days[-1],currency='USD',basis_id='new',review_reference='controlled review'))})
  normalization=dict(security_id='B',raw_sha256=digest(body),review_reference='server-approved-fixture',price_basis=basis,basis_asof='2026-11-02T14:00:00+00:00',captured_at='2026-11-02T14:00:00+00:00',current_unit_id='new',split_schedule=([dict(action_id=action['action_id'],security_id='B',ratio=8,old_unit_id='old',new_unit_id='new',quote_unit_effective_at=q)] if inside else []),reviewed_dividends=[])
  proof=canonical(dict(schema='SPLIT_MONTHLY_TRAINING_UNITS_CONTENT_V1',manifest_sha256=digest(rawmanifest),actions={action['action_id']:dict(scope='COMPLETE_253_CURRENT_UNITS',recorded_action_sha256=digest(canonical(action)),timing_sha256=digest(canonical(timing)),inputs=inputs,normalization=normalization,identity=dict(ticker='BBB',exchange='NMS'))}))
  pins={}
  for name in factory.RUNTIME_PATHS:
   source=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source);pins[name]=digest(source)
  config=dict(schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1',selector_profile=PROFILE_ID,target_month='2026-11',training_manifest='manifest.json',training_sha256=digest(rawmanifest),training_closed_at=provider.closed,identity_manifest='unused-test-identity',identity_sha256='a'*64,runtime_pins=pins)
  # Actual controlled action transport includes the historical split even before training.
  epoch=int(datetime.fromisoformat(q).timestamp())
  def fetch(ticker,start,end):
   events={'splits':{str(epoch):dict(date=epoch,numerator=8,denominator=1,splitRatio='8:1')}} if ticker=='BBB' else {}
   return dict(status=200,url=daily_url(ticker,start,end),body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events=events)]))))
  actions=StrategyAccountActionCapture(fetch=fetch,rss_fetch=provider.actions.rss_fetch,clock=lambda:now[0])
  # Action request must cover this already recorded split, independent of a later fill.
  monthly=factory.build_runtime(root=root,configuration=config,approval_pins=pins,timing_bundles={action['action_id']:timing},training_review_bytes=proof,training_review_sha256=digest(proof),clock=lambda:now[0],market_factory=lambda **kw:provider.market,action_factory=lambda **kw:actions)
  return monthly,store,proof
 def test_real_factory_selection_publication_both_history_bases(self):
  for inside,basis in [(False,'AS_TRADED'),(True,'AS_TRADED'),(True,'SPLIT_ADJUSTED_TO_CURRENT_UNIT')]:
   with self.subTest(inside=inside,basis=basis),TemporaryDirectory() as folder:
    monthly,store,proof=self.case(folder,inside,basis);before=store.read()
    view=SavedFrontierMonthlyView(monthly=monthly,proposals=SavedFrontierProposalStore(Path(folder)/'proposals.sqlite3'),validate_sources=monthly.selection._pins)
    with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
     result=view.generate(event_id='newmonth',reason='INITIAL',expected_revision=before['revision'],previous_target_id=None)
    self.assertEqual(result['payload']['target_month'],'2026-11');self.assertEqual(store.read(),before)
    self.assertEqual(result,view.current());self.assertIn('continuous_comparison',result['payload']['decision']['payload']['search_result'])
    self.assertEqual(result['payload']['decision']['core_calls'],1)
    self.assertEqual(result,view.generate(event_id='newmonth',reason='INITIAL',expected_revision=before['revision'],previous_target_id=None))
    # Exact next request is a genuine same-month reselection, not cached quantities.
    changed,_=store.append(dict(event_id='cash-change',kind='CASH_CONFIRM',amount='200',cash_basis='TOTAL_UNINVESTED'),expected_revision=before['revision'])
    again=view.generate(event_id='reconfigure',reason='EXPLICIT_RECONFIGURE',expected_revision=changed['revision'],previous_target_id=result['target_id'])
    self.assertNotEqual(again['target_id'],result['target_id'])
    self.assertEqual(again['payload']['decision']['payload']['input_binding']['account_revision'],changed['revision'])
 def test_training_certificate_rejects_wrong_adjustment_and_unknown_basis(self):
  for change,reason in [('basis','EXPLICIT_RAW_PRICE_BASIS_REQUIRED'),('adjustment','MONTHLY_HISTORY_COMPILER_DOUBLE_OR_MISSING_ADJUSTMENT')]:
   with self.subTest(change=change),TemporaryDirectory() as folder:
    monthly,store,rawproof=self.case(folder,True,'AS_TRADED')
    # Call the same reviewer with actual frozen package; no search required for failures.
    root=monthly.selection.root
    # Provider is captured by admitted_selection; retrieve its real closure object.
    provider=next(c.cell_contents for c in monthly.selection.provider.__closure__ if isinstance(c.cell_contents,factory.SplitProvider))
    package,historical=provider.training();proof=json.loads(rawproof)
    item=proof['actions']['split-B']
    if change=='basis':item['normalization']['price_basis']='UNKNOWN'
    else:item['normalization']['price_basis']='SPLIT_ADJUSTED_TO_CURRENT_UNIT'
    modified=canonical(proof)
    timing=next(c.cell_contents for c in provider._assemble.__func__.__closure__ if isinstance(c.cell_contents,dict) and 'split-B' in c.cell_contents)
    with self.assertRaisesRegex(ValueError,reason):factory.history_admission(package=package,manifest_path='manifest.json',state=store.read(),review_bytes=modified,review_sha256=digest(modified),timing_bundles=timing,now=provider.clock().isoformat())
if __name__=='__main__':unittest.main()
