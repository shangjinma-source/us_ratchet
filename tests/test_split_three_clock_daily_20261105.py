"""Actual archive, split ledger, prepared SQLite risk and source reader integration."""
from copy import deepcopy
from contextlib import closing
from datetime import datetime
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from core.strategy_account_ledger import canonical
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from core.monthly_peak_exit import advance_monthly_exit
from docs.candidates.split_three_clock_coordinates_20261105 import prepare_split_risk,review_timing
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from docs.candidates.split_three_clock_daily_evidence_20261105 import project_split_frontier_daily
import test_saved_frontier_daily_evidence as fixture
ROOT=Path(__file__).resolve().parents[1]
def digest(v):return sha256(v).hexdigest()

class Tests(unittest.TestCase):
 def case(self,folder,basis,broker_confirmed_at=None,held_split=False,timing_overrides=None):
  c=fixture.joint_fixture(folder);files=deepcopy(c['files']);review=json.loads(c['review_bytes']);inputs=json.loads(files['normalized.json']);days=inputs['session_dates']
  accounts=SplitStrategyAccountStore(Path(folder)/'split-account.sqlite3',clock=lambda:datetime.fromisoformat(broker_confirmed_at or c['now']))
  accounts.initialize(c['state']['account_id'],operation_id='initialize')
  original=accounts.read()
  # initialize creates an empty journal; replay every original real event.
  for row in c['state']['events']:accounts.append(row['payload'],expected_revision=accounts.read()['revision'])
  if held_split:
   files['fixture-A']=canonical(dict(security_id='A',ticker='A'))
   accounts.append(dict(event_id='holding-A',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=2,price='100',fees='0',executed_at='2026-10-20T14:00:00+00:00',identity_evidence=dict(security_id='A',ticker='A',source_references=['fixture-A'],source_hashes={'fixture-A':digest(files['fixture-A'])})),expected_revision=accounts.read()['revision'])
  action=dict(event_id='split-A',kind='SPLIT_CONFIRMED',action_id='split-A',security_id='A',ratio=8,
   effective_at=days[1]+'T22:00:00+00:00',broker_confirmed_at=broker_confirmed_at or days[2]+'T13:31:00+00:00',old_unit_id='unit-A',new_unit_id='unit-A8',evidence_sha256='a'*64)
  body=canonical(dict(distribution=action['effective_at'],quote=days[2]+'T13:30:00+00:00',observed_actual_tradability=True))
  proof=dict(schema='SPLIT_THREE_CLOCK_EXECUTION_CONTENT_V2',action_id='split-A',recorded_action_sha256=digest(canonical(action)),distribution_at=action['effective_at'],quote_unit_effective_at=days[2]+'T13:30:00+00:00',broker_tradable_at=days[2]+'T13:30:00+00:00',tradable_evidence_received_at=days[2]+'T13:32:00+00:00',tradable_evidence_semantics='OBSERVED_ACTUALLY_TRADABLE_NOT_FUTURE_NOTICE',clock_source_references={k:['actual-timing.json'] for k in ('distribution_at','quote_unit_effective_at','broker_tradable_at','tradable_evidence_received_at')})
  proof.update(timing_overrides or {})
  calendar=json.loads(files['calendar.json'])
  timing=dict(calendar=calendar,calendar_sha256=digest(canonical(calendar)),review=proof,source_hex={'actual-timing.json':body.hex()},source_hashes={'actual-timing.json':digest(body)})
  accounts.append(action,expected_revision=accounts.read()['revision'])
  accounts.append(dict(event_id='post-split-cash',kind='CASH_CONFIRM',amount='19850',cash_basis='TOTAL_UNINVESTED'),expected_revision=accounts.read()['revision'])
  state=accounts.read();observations=[];risk=None
  for i,day in enumerate(days):
   prices={sid:str(F(h['closes'][i]['close'])/(8 if sid=='A' and i==2 else 1)) for sid,h in inputs['histories'].items()}
   units={sid:('unit-A8' if sid=='A' and i==2 else 'unit-'+sid) for sid in prices}
   row=dict(decision_date=days[0],session_date=day,closes=prices,unit_ids=units)
   row['evidence_sha256']=digest(json.dumps(row,sort_keys=True).encode());observations.append(row)
   if i<2:risk=advance_monthly_exit(state=risk,account_id=state['account_id'],baseline_targets=c['proposal']['payload']['proposed_target_quantities'],**{k:v for k,v in row.items() if k!='evidence_sha256'})['state']
  risk['target_month']='2026-10';path=c['research_root']/'prepared.sqlite3'
  prepared=prepare_split_risk(destination_path=path,account_after=state,action_id='split-A',risk_before=risk,target=c['target'],expected_proposal_id=c['proposal']['proposal_id'],observations=observations,expected_sessions=days,timing=timing)
  # Exact existing preparation envelope carries the immutable native transition.
  import sqlite3
  with closing(sqlite3.connect(path)) as con:transition=json.loads(con.execute('SELECT payload FROM split_preparation').fetchone()[0])['transition']
  inputs['base_target']['quantities']={s:transition['payload']['risk_projection']['target_quantities'].get(s,0) for s in inputs['histories']}
  for sid,h in inputs['histories'].items():
   unitpath=review['documents']['unit_reviews'][sid];rawpath=review['documents']['raw_by_security'][sid];unit=json.loads(files[unitpath]);doc=json.loads(files[rawpath]);series=doc['chart']['result'][0]
   schedule=[]
   if sid=='A':
    inputs['base_target']['price_units'][sid]='unit-A8';h['units']['basis_id']='unit-A8';unit['basis_id']='unit-A8'
    for r in h['closes']:r['close']=str(F(r['close'])/8)
    series['indicators']['quote'][0]['close']=[str(F(v)/(8 if basis=='SPLIT_ADJUSTED_TO_CURRENT_UNIT' or i==2 else 1)) for i,v in enumerate(series['indicators']['quote'][0]['close'])]
    epoch=int(datetime.fromisoformat(proof['quote_unit_effective_at']).timestamp());series['events']={'splits':{str(epoch):dict(date=epoch,numerator=8,denominator=1,splitRatio='8:1')}}
    schedule=[dict(action_id='split-A',security_id='A',ratio=8,old_unit_id='unit-A',new_unit_id='unit-A8',quote_unit_effective_at=proof['quote_unit_effective_at'])]
   for r in h['closes']:r['close']=str(F(r['close']))
   files[rawpath]=canonical(doc);h['source_reference']='sha256:'+digest(files[rawpath]);unit.update(schema='SPLIT_SAVED_FRONTIER_UNIT_REVIEW_V1',transition_id=transition['transition_id'],raw_sha256=digest(files[rawpath]),corporate_actions=schedule,
    raw_normalization=dict(security_id=sid,raw_sha256=digest(files[rawpath]),review_reference=unitpath,price_basis=basis if sid=='A' else 'AS_TRADED',basis_asof=review['source_received_at'],captured_at=review['source_received_at'],current_unit_id=unit['basis_id'],split_schedule=schedule,reviewed_dividends=[]))
   files[unitpath]=canonical(unit)
  files['normalized.json']=canonical(inputs);review.update(timing_sha256=digest(canonical(timing)),schema='SPLIT_SAVED_FRONTIER_DAILY_REVIEW_V1',transition_id=transition['transition_id'],account_revision=state['revision'],risk_state_sha256=digest(canonical(prepared['final_state'])),review_scope='FULL_WINDOW_EXPLICIT_SPLIT_UNITS',action_clocks=dict(distribution_at=action['effective_at'],quote_unit_effective_at=proof['quote_unit_effective_at'],broker_tradable_at=action['broker_confirmed_at']),source_sha256={n:digest(v) for n,v in files.items()})
  raw=canonical(review)
  return c,accounts,dict(research_root=c['research_root'],risk_path=path,target_id=c['target']['target_id'],state=state,review_bytes=raw,trusted_review_sha256=digest(raw),files=files,now=c['now'],enabled=True)
 def test_real_composition_quote_limits_cash_and_buy_data_wait(self):
  from contextlib import nullcontext
  from types import SimpleNamespace
  from unittest.mock import patch
  from functools import partial
  import test_saved_frontier_isolated_pipeline as pipeline
  from docs.candidates import split_three_clock_daily_composition_20261105 as composition
  from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider
  from docs.candidates.strategy_account_split_market_capture import StrategyAccountMarketCapture
  from docs.candidates.strategy_account_split_execution_limits import build_execution_limits
  from data.strategy_account_action_capture import StrategyAccountActionCapture
  from data.current_quantity_v2_paper_action_sources import daily_url
  for mode in ['cash','zero','missing_buy','cash_update','fill','held_split']:
   with self.subTest(mode=mode),TemporaryDirectory(dir=ROOT/'tmp') as folder:
    c,accounts,args=self.case(folder,'AS_TRADED',held_split=True)
    import sqlite3
    with closing(sqlite3.connect(args['risk_path'])) as con:original_preparation=con.execute('SELECT payload,digest FROM split_preparation').fetchone()
    accounts.append(dict(event_id='cancel-open-E',kind='CANCEL',order_id='old-open-E'),expected_revision=accounts.read()['revision'])
    if mode=='fill':
     accounts.append(dict(event_id='real-sale',kind='DIRECT_FILL',security_id='D',side='SELL',quantity=1,price='50',fees='0',executed_at='2026-10-23T13:32:00+00:00'),expected_revision=accounts.read()['revision'])
     accounts.append(dict(event_id='after-fill-cash',kind='CASH_CONFIRM',amount='19900',cash_basis='TOTAL_UNINVESTED'),expected_revision=accounts.read()['revision'])
    if mode=='cash_update':accounts.append(dict(event_id='cash-update',kind='CASH_CONFIRM',amount='15000',cash_basis='TOTAL_UNINVESTED'),expected_revision=accounts.read()['revision'])
    if mode=='zero':accounts.append(dict(event_id='zero',kind='CASH_CONFIRM',amount='0',cash_basis='TOTAL_UNINVESTED'),expected_revision=accounts.read()['revision'])
    # Current cash/order events extend the authenticated preparation prefix.
    rev=json.loads(args['review_bytes']);rev.update(account_revision=accounts.read()['revision'])
    args.update(state=accounts.read(),review_bytes=canonical(rev),trusted_review_sha256=digest(canonical(rev)))
    now=[datetime.fromisoformat(c['now'])]
    with patch.object(pipeline,'StrategyAccountEvidenceProvider',StrategyAccountEvidenceProvider),patch.object(pipeline,'StrategyAccountMarketCapture',StrategyAccountMarketCapture),patch.object(pipeline,'build_execution_limits',build_execution_limits):provider=pipeline.offline_provider(c,now)
    raw_fetch=provider.market.fetch
    def split_quote(ticker):
     doc=json.loads(raw_fetch(ticker))
     if ticker=='A':
      series=doc['chart']['result'][0];series['meta']['regularMarketPrice']/=8
      for key in ('open','high','low','close'):series['indicators']['quote'][0][key]=[v/8 for v in series['indicators']['quote'][0][key]]
     return canonical(doc)
    provider.market.fetch=split_quote
    epoch=int(datetime.fromisoformat('2026-10-22T13:30:00+00:00').timestamp())
    def fetch(ticker,start,end):
     events={'splits':{str(epoch):dict(date=epoch,numerator=8,denominator=1,splitRatio='8:1')}} if ticker=='A' else {}
     return dict(status=200,url=daily_url(ticker,start,end),body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events=events)]))))
    provider.actions=StrategyAccountActionCapture(fetch=fetch,clock=lambda:now[0],rss_fetch=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Fri, 23 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
    monthly=SimpleNamespace(accounts=accounts,current=lambda:deepcopy(c['target']),snapshot_operation=nullcontext,validate_current_target_pins=lambda:None)
    def reader(state,target,at,*,proposal):return project_split_frontier_daily(**dict(args,state=state,now=at.isoformat()))
    service=composition.SavedFrontierDailyComposition(monthly_service=monthly,monthly_view=SimpleNamespace(require_proposal=lambda **kw:deepcopy(c['proposal'])),evidence_reader=reader,execution_provider=provider.execution,clock=lambda:now[0],policy_execution_enabled=True,policy_id='SPLIT_SAVED_FRONTIER_CONTENT_ONLY_V1',fee_bps='1')
    original=accounts.read()
    with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')),(patch.object(composition.SavedFrontierPreviewService,'preview',side_effect=ValueError('MINUTE_GAP')) if mode=='missing_buy' else nullcontext()):
     answer=service.preview(expected_revision=original['revision'],target_id=c['target']['target_id'],expected_proposal_id=c['proposal']['proposal_id'])
    self.assertEqual(answer['status'],'READY');self.assertEqual(answer['risk_monthly_targets']['A'],792);self.assertEqual(answer['effective_target_quantities']['A'],0);self.assertEqual(accounts.read(),original)
    with closing(sqlite3.connect(args['risk_path'])) as con:self.assertEqual(con.execute('SELECT payload,digest FROM split_preparation').fetchone(),original_preparation)
    self.assertTrue(any(o['side']=='SELL' for o in answer['new_orders']))
    self.assertEqual(next(o['quantity'] for o in answer['new_orders'] if o['security_id']=='A'),16)
    if mode in {'zero','missing_buy'}:self.assertTrue(all(o['side']=='SELL' for o in answer['new_orders']))
 def test_independent_tradability_known_time_and_reconciliation(self):
  from unittest.mock import patch
  for change,reason in [({'tradable_evidence_semantics':'FUTURE_NOTICE'},'TIMING_ACTUAL_TRADABILITY_REQUIRED'),({'broker_tradable_at':'2026-10-23T14:30:00+00:00','tradable_evidence_received_at':'2026-10-23T14:31:00+00:00'},'TIMING_NOT_EXECUTABLE_YET'),({'quote_unit_effective_at':'2026-10-22T14:00:00+00:00'},'SPLIT_INTRADAY_UNIT_HISTORY_UNSUPPORTED')]:
   with self.subTest(change=change),TemporaryDirectory(dir=ROOT/'tmp') as folder:
    if reason in {'TIMING_ACTUAL_TRADABILITY_REQUIRED','SPLIT_INTRADAY_UNIT_HISTORY_UNSUPPORTED'}:
     with self.assertRaisesRegex(ValueError,reason):self.case(folder,'AS_TRADED',timing_overrides=change)
    else:
     c,accounts,args=self.case(folder,'AS_TRADED',timing_overrides=change)
     with self.assertRaisesRegex(ValueError,reason):project_split_frontier_daily(**args)
  with TemporaryDirectory(dir=ROOT/'tmp') as folder:
   c,accounts,args=self.case(folder,'AS_TRADED',held_split=True)
   accounts.append(dict(event_id='ambiguous-unit-fill',kind='DIRECT_FILL',security_id='A',side='SELL',quantity=1,price='50',fees='0',executed_at='2026-10-22T12:00:00+00:00'),expected_revision=accounts.read()['revision'])
   args['state']=accounts.read()
   with self.assertRaisesRegex(ValueError,'SPLIT_FILL_UNIT_RECONCILIATION_REQUIRED'):project_split_frontier_daily(**args)
 def test_early_confirmation_later_actual_tradability_and_adjusted_history(self):
  for basis in ['AS_TRADED','SPLIT_ADJUSTED_TO_CURRENT_UNIT']:
   with self.subTest(basis=basis),TemporaryDirectory(dir=ROOT/'tmp') as folder:
    c,accounts,args=self.case(folder,basis,broker_confirmed_at='2026-10-21T23:00:00+00:00',timing_overrides=dict(broker_tradable_at='2026-10-22T15:00:00+00:00',tradable_evidence_received_at='2026-10-22T15:01:00+00:00'))
    answer=project_split_frontier_daily(**args)
    self.assertEqual(answer['signal']['effective_target_quantities']['A'],0)
    self.assertEqual(answer['transition']['payload']['risk_projection']['risk_state']['unit_ids']['A'],'unit-A8')
 def test_friday_close_and_after_hours_map_to_monday_full_bar(self):
  from docs.candidates.split_three_clock_coordinates_20261105 import project_history_units
  action=dict(kind='SPLIT_CONFIRMED',action_id='x',security_id='A',ratio=2,old_unit_id='old',new_unit_id='new',effective_at='2026-11-05T22:00:00+00:00',broker_confirmed_at='2026-11-09T14:31:00+00:00')
  calendar=dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[dict(date=d,open=d+'T14:30:00+00:00',close=d+'T21:00:00+00:00') for d in ['2026-11-05','2026-11-06','2026-11-09']])
  sources={'actual':'actual tradable evidence'.encode()}
  for quote in ['2026-11-06T21:00:00+00:00','2026-11-06T23:00:00+00:00']:
   proof=dict(schema='SPLIT_THREE_CLOCK_EXECUTION_CONTENT_V2',action_id='x',recorded_action_sha256=digest(canonical(action)),distribution_at=action['effective_at'],quote_unit_effective_at=quote,broker_tradable_at='2026-11-09T14:30:00+00:00',tradable_evidence_received_at='2026-11-09T14:32:00+00:00',tradable_evidence_semantics='OBSERVED_ACTUALLY_TRADABLE_NOT_FUTURE_NOTICE',clock_source_references={k:['actual'] for k in ('distribution_at','quote_unit_effective_at','broker_tradable_at','tradable_evidence_received_at')})
   timing=dict(review=proof,source_hex={k:v.hex() for k,v in sources.items()},source_hashes={k:digest(v) for k,v in sources.items()},calendar=calendar,calendar_sha256=digest(canonical(calendar)))
   observations=[dict(decision_date='2026-11-06',session_date=d,closes={'A':v},unit_ids={'A':u},evidence_sha256='a'*64) for d,v,u in [('2026-11-06','100','old'),('2026-11-09','51','new')]]
   before=deepcopy(observations)
   result=project_history_units(observations=observations,action=action,expected_sessions=['2026-11-06','2026-11-09'],timing=timing)
   self.assertEqual([r['closes']['A'] for r in result['payload']['normalized_observations']],['50','51']);self.assertEqual(observations,before)
   self.assertEqual(review_timing(action=action,timing=timing,now='2026-11-09T14:33:00+00:00')['quote_bar_boundary_at'],'2026-11-09T14:30:00+00:00')
if __name__=='__main__':unittest.main()
