"""Configured actual profiled capture admission mounted into fresh HTTP routes.

Synthetic pinned source authorization is explicit; no browser/model authenticity
claim and no production activation. Reuses the configuration fixture once.
"""
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import socket,unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_split_native_capture_configuration_20261105 as fixture
from data.news_risk_skill_v1 import PINS
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from docs.candidates.split_configured_runtime_routes_20261105 import build_configured_routes as build_routes

class Tests(unittest.TestCase):
 def test_configured_capture_cash_fill_http_lifecycle(self):
  builder=fixture.Tests();self.addCleanup(builder.doCleanups)
  case=builder.case();service=case['service'];f=case['f'];view=case['view'];provider=case['provider'];store=f.store
  target=view.current();fixed_id=target['target_id'];clock=lambda:f.now
  for name in PINS:
   path=f.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((fixture.fixture.ROOT/name).read_bytes())
  started=self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.start_worker'));stopped=self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.stop_worker'))
  prepared=build_routes(root=f.root,monthly_view=view,daily_service=service,journal=DailyAdviceJournalV1(f.root/'http-journal.sqlite3'),clock=clock,validate_sources=service.validate_code,policy_references={'scope':'CONFIGURED_NATIVE_CAPTURE_HTTP_FIXTURE'},timing_bundles=case['timing'],account_arguments=dict(database_path=store.path,account_id=store.read()['account_id'],resolver=provider.market.identity,clock=clock))
  self.assertTrue(prepared['calendar_enabled']);self.assertTrue(prepared['native_hold_enabled']);self.assertTrue(prepared['monthly_generation_enabled'])
  self.assertIs(prepared['event_pipeline'].service,prepared['news_service'])
  self.assertTrue(callable(prepared['news_service'].risk_plan_provider))
  calendar=prepared['event_pipeline'].calendar_window(clock().isoformat())
  self.assertEqual(calendar['target_id'],fixed_id);self.assertEqual(calendar['proposal_id'],target['proposal_id'])
  app=FastAPI();app.include_router(prepared['router']);connect=socket.socket.connect
  def offline(sock,address):
   if isinstance(address,tuple) and address[0] in ('127.0.0.1','::1'):return connect(sock,address)
   raise AssertionError('NETWORK_FORBIDDEN')
  with patch('socket.socket.connect',offline),TestClient(app) as client:
   initial=store.read();cash=client.post('/api/strategy-account/events',json=dict(expected_revision=initial['revision'],event=dict(event_id='configured-http-cash',kind='CASH_CONFIRM',amount='110',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
   self.assertEqual(cash.status_code,200,cash.text);state=store.read()
   current=client.get('/api/strategy-daily-v3/current');self.assertEqual(current.status_code,200,current.text)
   value=current.json();self.assertEqual(value['daily']['status'],'READY',value);self.assertEqual(value['account']['revision'],state['revision'])
   self.assertTrue(list(Path(service.capture_root).rglob('complete.json')))
   news=prepared['news_service'];old=dict(expected_revision=state['revision'],target_id=fixed_id,expected_proposal_id=target['proposal_id']);news.bound_context(old)
   sale=next(o for o in value['daily']['new_orders'] if o['side']=='SELL');ticker=news.context()[2][sale['security_id']]
   event=dict(event_id='configured-http-sell',kind='DIRECT_FILL',ticker=ticker,side='SELL',quantity=1,price='10',fees='0',executed_at=clock().isoformat())
   filled=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=event));self.assertEqual(filled.status_code,200,filled.text)
   after=store.read();self.assertEqual(after['shares'][sale['security_id']],state['shares'][sale['security_id']]-1);self.assertEqual(len(after['events']),len(state['events'])+1)
   self.assertEqual(after['total_uninvested_cash'],state['total_uninvested_cash']);self.assertFalse(after['cash_confirmation_valid'])
   repeated=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=event));self.assertEqual(repeated.status_code,200,repeated.text);self.assertEqual(store.read(),after)
   with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_OR_TARGET'):news.bound_context(old)
   blocked=client.get('/api/strategy-daily-v3/current');self.assertEqual(blocked.status_code,409,blocked.text);self.assertEqual(blocked.json()['reason'],'CASH_RECONFIRMATION_REQUIRED')
   confirmed=client.post('/api/strategy-account/events',json=dict(expected_revision=after['revision'],event=dict(event_id='configured-http-reconfirm',kind='CASH_CONFIRM',amount='120',cash_basis='AVAILABLE_AFTER_RESERVATIONS')));self.assertEqual(confirmed.status_code,200,confirmed.text)
   f.now+=timedelta(minutes=1)
   refreshed=client.get('/api/strategy-daily-v3/current');self.assertEqual(refreshed.status_code,200,refreshed.text)
   value=refreshed.json();self.assertEqual(value['daily']['status'],'READY',value)
   remaining=next(o for o in value['daily']['new_orders'] if o['side']=='SELL' and o['security_id']==sale['security_id']);self.assertEqual(remaining['quantity'],sale['quantity']-1)
   self.assertEqual(news.context()[0],store.read());self.assertEqual(view.current()['target_id'],fixed_id)
   self.assertEqual(client.get('/api/strategy-account/target').json()['target_id'],fixed_id)
  self.assertEqual(started.call_count,1);self.assertEqual(stopped.call_count,1)

if __name__=='__main__':unittest.main()
