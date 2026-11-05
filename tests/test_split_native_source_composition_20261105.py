"""Actual native daily archive/raw/risk output into genuine execution composition."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,unittest
import test_split_native_month_daily_20261105 as fixture
from core.strategy_account_ledger import canonical
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView,SavedFrontierProposalStore
from data.saved_frontier_policy_archive import read_saved_frontier_policy
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from docs.candidates import split_native_month_daily_20261105 as native
from docs.candidates.split_native_daily_composition_20261105 import build_composition
from docs.candidates.split_native_daily_execution_bridge_20261105 import DailyMixedExecutionBridge,DailyBuyDataWaitExecutionBridge

class Tests(unittest.TestCase):
 def test_raw_archive_risk_to_actual_execution(self):
  with TemporaryDirectory(dir=fixture.ROOT/'tmp') as folder:
   monthly,store,target,proposal,args=fixture.Tests().case(folder)
   provider=monthly.execution_provider.__self__
   clockvalues=next(c.cell_contents for c in provider.clock.__closure__ if isinstance(c.cell_contents,list));clockvalues[0]=datetime.fromisoformat(args['now'])
   market=next(c.cell_contents for c in provider.market.capture.__closure__ if hasattr(c.cell_contents,'fetch'));original=market.fetch
   def fetch(ticker):
    raw=json.loads(original(ticker));row=raw['chart']['result'][0];last=int(provider.clock().timestamp());start=int(provider.clock().replace(hour=14,minute=30,second=0).timestamp())
    row['meta']['regularMarketTime']=last;row['meta']['currentTradingPeriod']['regular'].update(start=start,end=start+23400)
    row['timestamp']=list(range(start,last,60));row['indicators']['quote'][0]={k:[v]*len(row['timestamp']) for k,v in dict(open=10,high=11,low=9,close=10,volume=10).items()}
    return canonical(raw)
   market.fetch=fetch
   view=SavedFrontierMonthlyView(monthly=monthly,proposals=SavedFrontierProposalStore(Path(folder)/'proposals.sqlite3'),validate_sources=monthly.selection._pins)
   def reader(state,target,at,*,proposal):
    local=deepcopy(args);local['state']=state;local['now']=at.isoformat();review=json.loads(local['review_bytes'])
    review['account_revision']=state['revision'];review['risk_state_sha256']=fixture.digest(canonical(MonthlyPeakExitStore(local['risk_path']).read(state['account_id'])))
    checked=native.verify_native_units(state=state,target=target,archived=read_saved_frontier_policy(research_root=local['research_root'],target_id=target['target_id']),review=review,now=local['now'])
    for name in review['documents']['unit_reviews'].values():
     unit=json.loads(local['files'][name]);unit['native_unit_proof_sha256']=checked['proof_sha256'];local['files'][name]=canonical(unit)
    review['source_sha256']={n:fixture.digest(r) for n,r in local['files'].items()};local.update(review_bytes=canonical(review),trusted_review_sha256=fixture.digest(canonical(review)))
    return native.project_native_month_daily(**local)
   service=build_composition(mixed_execution_bridge=DailyMixedExecutionBridge,buy_wait_execution_bridge=DailyBuyDataWaitExecutionBridge,monthly_service=monthly,monthly_view=view,evidence_reader=reader,execution_provider=monthly.execution_provider,clock=provider.clock,policy_execution_enabled=True,policy_id='SPLIT_NATIVE_MONTH_CONTENT_ONLY_V1',fee_bps=monthly.selection.fees)
   for cash in (100,0):
    if cash==0:store.append(dict(event_id='native-zero',kind='CASH_CONFIRM',amount='0',cash_basis='TOTAL_UNINVESTED'),expected_revision=store.read()['revision'])
    state=store.read()
    with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
     result=service.preview(expected_revision=state['revision'],target_id=target['target_id'],expected_proposal_id=proposal['proposal_id'])
    self.assertEqual(result['status'],'READY',result);self.assertTrue(result['new_orders'])
    if cash==0:self.assertTrue(all(order['side']=='SELL' for order in result['new_orders']))
    self.assertEqual(store.read(),state);self.assertEqual(view.current()['target_id'],target['target_id'])
   # Same actual evidence reader through routes and genuine news context binding.
   from fastapi import FastAPI
   from fastapi.testclient import TestClient
   from data.news_risk_skill_v1 import PINS
   from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
   from docs.candidates.split_runtime_routes_20261105 import build_routes
   import socket
   for name in PINS:
    path=Path(folder)/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((fixture.ROOT/name).read_bytes())
   bundles=json.loads(args['review_bytes'])['timing_bundles']
   start=self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.start_worker'));stop=self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.stop_worker'))
   prepared=build_routes(root=Path(folder),monthly_view=view,daily_service=service,journal=DailyAdviceJournalV1(Path(folder)/'journal.sqlite'),clock=provider.clock,validate_sources=monthly.selection._pins,policy_references={'scope':'CONTROLLED_NATIVE_SOURCE_HTTP_TEST'},timing_bundles=bundles,account_arguments=dict(database_path=store.path,account_id=state['account_id'],resolver=market.identity,clock=provider.clock))
   app=FastAPI();app.include_router(prepared['router']);connect=socket.socket.connect
   def offline(sock,address):
    if isinstance(address,tuple) and address[0] in ('127.0.0.1','::1'):return connect(sock,address)
    raise AssertionError('NETWORK_FORBIDDEN')
   with patch('socket.socket.connect',offline),TestClient(app) as client:
    response=client.post('/api/strategy-account/events',json=dict(expected_revision=store.read()['revision'],event=dict(event_id='http-native-cash',kind='CASH_CONFIRM',amount='110',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
    self.assertEqual(response.status_code,200,response.text)
    clockvalues[0]+=timedelta(minutes=1)
    current=client.get('/api/strategy-daily-v3/current');self.assertEqual(current.status_code,200,current.text)
    value=current.json();self.assertEqual(value['daily']['status'],'READY',value)
    before=store.read();news=prepared['news_service'];self.assertEqual(news.context()[0],before)
    old=dict(expected_revision=before['revision'],target_id=target['target_id'],expected_proposal_id=proposal['proposal_id']);news.bound_context(old)
    sale=next(o for o in value['daily']['new_orders'] if o['side']=='SELL');ticker=news.context()[2][sale['security_id']]
    event=dict(event_id='http-native-fill',kind='DIRECT_FILL',ticker=ticker,side='SELL',quantity=1,price='10',fees='0',executed_at=provider.clock().isoformat())
    filled=client.post('/api/strategy-account/events',json=dict(expected_revision=before['revision'],event=event));self.assertEqual(filled.status_code,200,filled.text)
    after=store.read();self.assertEqual(after['shares'][sale['security_id']],before['shares'][sale['security_id']]-1)
    self.assertEqual(len(after['events']),len(before['events'])+1);self.assertEqual(after['total_uninvested_cash'],before['total_uninvested_cash'])
    replay=client.post('/api/strategy-account/events',json=dict(expected_revision=before['revision'],event=event));self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(store.read(),after)
    with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_OR_TARGET'):news.bound_context(old)
    blocked=client.get('/api/strategy-daily-v3/current');self.assertEqual(blocked.status_code,409,blocked.text)
    self.assertEqual(blocked.json()['reason'],'CASH_RECONFIRMATION_REQUIRED')
    confirmed=client.post('/api/strategy-account/events',json=dict(expected_revision=after['revision'],event=dict(event_id='http-native-reconfirm',kind='CASH_CONFIRM',amount='120',cash_basis='AVAILABLE_AFTER_RESERVATIONS')));self.assertEqual(confirmed.status_code,200,confirmed.text)
    clockvalues[0]+=timedelta(minutes=1)
    refreshed=client.get('/api/strategy-daily-v3/current');self.assertEqual(refreshed.status_code,200,refreshed.text)
    value=refreshed.json();self.assertEqual(value['daily']['status'],'READY',value)
    remaining=next(o for o in value['daily']['new_orders'] if o['side']=='SELL' and o['security_id']==sale['security_id']);self.assertEqual(remaining['quantity'],sale['quantity']-1)
    self.assertEqual(value['account']['revision'],store.read()['revision']);self.assertEqual(news.context()[0],store.read());self.assertEqual(view.current()['target_id'],target['target_id'])
   self.assertEqual(start.call_count,1);self.assertEqual(stop.call_count,1)
if __name__=='__main__':unittest.main()
