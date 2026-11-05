"""Native generated target HTTP lifecycle; signal reader remains controlled.

Real proposal storage, split accounting, execution transport, routes and news
binding execute. This does not certify the forthcoming native evidence reader.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json, socket, unittest, gzip
from types import SimpleNamespace
from docs.candidates import split_native_rolling_admission_20261105 as admission
from data.strategy_execution_halt_evidence_v1 import HEADER
from data import strategy_halt_gzip_capture_v1 as halt
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_split_monthly_factory_20261105 as fixture
from core.strategy_account_ledger import canonical
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView, SavedFrontierProposalStore
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.news_risk_skill_v1 import PINS
from docs.candidates.split_native_daily_composition_20261105 import build_composition
from docs.candidates.split_native_daily_execution_bridge_20261105 import DailyMixedExecutionBridge,DailyBuyDataWaitExecutionBridge
from docs.candidates.split_runtime_routes_20261105 import build_routes
from docs.candidates.split_native_monthly_routes_20261105 import attach_monthly_routes

class Tests(unittest.TestCase):
 def test_native_target_http_cash_fill_retry_and_news_staleness(self):
  with TemporaryDirectory() as folder:
   monthly,store,_=fixture.Tests().case(folder)
   provider=monthly.execution_provider.__self__
   market=next(c.cell_contents for c in provider.market.capture.__closure__ if hasattr(c.cell_contents,'fetch'))
   original_fetch=market.fetch
   def fetch(ticker):
    raw=json.loads(original_fetch(ticker));row=raw['chart']['result'][0]
    row['timestamp']=list(range(row['meta']['currentTradingPeriod']['regular']['start'],row['meta']['regularMarketTime'],60))
    row['indicators']['quote'][0]={k:[v]*len(row['timestamp']) for k,v in dict(open=10,high=11,low=9,close=10,volume=10).items()}
    return canonical(raw)
   market.fetch=fetch
   view=SavedFrontierMonthlyView(monthly=monthly,proposals=SavedFrontierProposalStore(Path(folder)/'proposal.sqlite'),validate_sources=monthly.selection._pins)
   state=store.read()
   target=view.generate(event_id='native-http',reason='INITIAL',expected_revision=state['revision'],previous_target_id=None)
   fixed_target=deepcopy(target)
   # Unwrap only the fixture's no-op market.capture instrumentation; production
   # factory already exposes the actual market transport object.
   provider.market=market
   def reader(state,target,at,*,proposal):
    quantities=dict(proposal['payload']['proposed_target_quantities'])
    for sid in state['shares']:quantities.setdefault(sid,0)
    signal=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target['target_id'],proposal_id=proposal['proposal_id'],policy_id='CONTROLLED_NATIVE_TEST',evidence_id='controlled',evidence_archive={'fixture':True},effective_target_quantities=quantities,observed_at=at.isoformat(),available_at=at.isoformat(),valid_from=at.isoformat(),valid_until=(at+timedelta(seconds=60)).isoformat())
    return dict(status='DAILY_SIGNAL_READY',signal=signal,evidence_archive=signal['evidence_archive'])
   bundles=next(c.cell_contents for c in type(provider)._assemble.__closure__ if isinstance(c.cell_contents,dict) and 'split-B' in c.cell_contents)
   from data.current_quantity_v2_pullback_runtime import PullbackCapStore
   legacy=provider.limits.keywords['cap_store'];PullbackCapStore(legacy.path,clock=legacy.clock,max_history_rows=legacy.max_history_rows,max_history_bytes=legacy.max_history_bytes)
   identity=canonical(dict(candidates=[dict(ticker=ticker,security_id=sid,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['native-admission-identity-proof']) for sid,ticker in [('A','AAA'),('B','BBB')]],source_hashes={'native-admission-identity-proof':fixture.digest(b'controlled proof')}))
   (provider.root/'native-admission-identities.json').write_bytes(identity);(provider.root/'native-admission-identity-proof').write_bytes(b'controlled proof')
   configuration=dict(identity_manifest='native-admission-identities.json',identity_sha256=fixture.digest(identity))
   def for_target(value):
    self.assertEqual(value,monthly.current());monthly.validate_current_target_pins()
    return monthly,deepcopy(configuration)
   routed=SimpleNamespace(accounts=monthly.accounts,root=provider.root,current=monthly.current,snapshot_operation=monthly.snapshot_operation,validate_current_target_pins=monthly.validate_current_target_pins,_for_target=for_target)
   service=admission.NativeSplitRollingAdmission(monthly=routed,monthly_view=view,reader=reader,clock=provider.clock,validate_code=monthly.selection._pins,timing_bundles=bundles,policy_execution_enabled=True,policy_id='CONTROLLED_NATIVE_TEST')
   body=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode()
   wire=gzip.compress(body);real_halt=admission.HaltMarketCaptureV1
   transport_mode={'halt_ok':True}
   def wrapped(market,**kw):return real_halt(market,fetch=lambda:dict(url=halt.SOURCE_URL,status=200,headers={'Content-Encoding':'gzip'},body=wire if transport_mode['halt_ok'] else b'not gzip'),**kw)
   from data import strategy_rss_gzip_capture_v1 as rss_capture,official_rss_gzip_transport_v1 as rss_wire
   rss=provider.actions.rss_fetch()['body'].replace(b'<channel>',b'<channel><pubDate>Mon, 02 Nov 2026 15:00:00 GMT</pubDate>')
   def rss_transport(**kw):return rss_wire.GzipRssTransport(fetch=lambda:dict(url=rss_wire.URL,status=200,headers={'Content-Encoding':'gzip'},body=gzip.compress(rss)),**kw)
   self.enterContext(patch.object(admission,'HaltMarketCaptureV1',wrapped));self.enterContext(patch.object(rss_capture,'GzipRssTransport',rss_transport))
   original_assemble=type(provider)._assemble;calls=[]
   def traced(self,*args,**kwargs):calls.append(True);return original_assemble(self,*args,**kwargs)
   self.enterContext(patch.object(type(provider),'_assemble',traced))
   for name in PINS:
    path=Path(folder)/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((fixture.ROOT/name).read_bytes())
   start=self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.start_worker'))
   stop=self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.stop_worker'))
   prepared=build_routes(root=Path(folder),monthly_view=view,daily_service=service,journal=DailyAdviceJournalV1(Path(folder)/'journal.sqlite'),clock=provider.clock,validate_sources=monthly.selection._pins,policy_references={'scope':'CONTROLLED_NATIVE_HTTP_TEST'},timing_bundles=bundles,account_arguments=dict(database_path=store.path,account_id=state['account_id'],resolver=market.identity,clock=provider.clock))
   prepared=attach_monthly_routes(prepared=prepared,validate_sources=monthly.selection._pins)
   app=FastAPI();app.include_router(prepared['router'])
   connect=socket.socket.connect
   def offline(sock,address):
    if isinstance(address,tuple) and address[0] in ('127.0.0.1','::1'):return connect(sock,address)
    raise AssertionError('NETWORK_FORBIDDEN')
   with patch('socket.socket.connect',offline),TestClient(app) as client:
    response=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=dict(event_id='native-cash',kind='CASH_CONFIRM',amount='110',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
    self.assertEqual(response.status_code,200,response.text);state=store.read()
    current=client.get('/api/strategy-daily-v3/current');self.assertEqual(current.status_code,200,current.text)
    value=current.json();self.assertEqual(value['daily']['status'],'READY',value)
    self.assertEqual(value['daily']['account_revision'],state['revision']);self.assertEqual(value['account']['revision'],state['revision'])
    news=prepared['news_service'];self.assertEqual(news.context()[0],state)
    old=dict(expected_revision=state['revision'],target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
    news.bound_context(old)
    sale=next(order for order in value['daily']['new_orders'] if order['side']=='SELL')
    ticker=news.context()[2][sale['security_id']]
    event=dict(event_id='native-sale',kind='DIRECT_FILL',ticker=ticker,side='SELL',quantity=1,price='10',fees='0',executed_at=provider.clock().isoformat())
    filled=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=event));self.assertEqual(filled.status_code,200,filled.text)
    after=store.read();self.assertFalse(after['cash_confirmation_valid'])
    self.assertEqual(after['shares'][sale['security_id']],state['shares'][sale['security_id']]-1)
    # A fill records its cash effect but does not infer broker buying power.
    self.assertEqual(after['total_uninvested_cash'],state['total_uninvested_cash'])
    self.assertEqual(len(after['events']),len(state['events'])+1)
    with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_OR_TARGET'):news.bound_context(old)
    replay=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=event));self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(store.read(),after)
    unconfirmed=client.get('/api/strategy-daily-v3/current')
    self.assertEqual(unconfirmed.status_code,409,unconfirmed.text)
    self.assertEqual(unconfirmed.json()['reason'],'CASH_RECONFIRMATION_REQUIRED')
    confirmed=client.post('/api/strategy-account/events',json=dict(expected_revision=after['revision'],event=dict(event_id='native-confirm',kind='CASH_CONFIRM',amount='120',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
    self.assertEqual(confirmed.status_code,200,confirmed.text)
    clock_values=next(cell.cell_contents for cell in provider.clock.__closure__ if isinstance(cell.cell_contents,list))
    clock_values[0]+=timedelta(minutes=1)
    refreshed=client.get('/api/strategy-daily-v3/current');self.assertEqual(refreshed.status_code,200,refreshed.text)
    value=refreshed.json();self.assertEqual(value['daily']['status'],'READY',value)
    remaining=next(order for order in value['daily']['new_orders'] if order['side']=='SELL' and order['security_id']==sale['security_id'])
    self.assertEqual(remaining['quantity'],sale['quantity']-1)
    self.assertEqual(value['account']['revision'],store.read()['revision']);self.assertEqual(news.context()[0],store.read())
    self.assertEqual(news.context()[1],view.current());self.assertEqual(view.current(),fixed_target)
    target_response=client.get('/api/strategy-account/target')
    self.assertEqual(target_response.status_code,200,target_response.text)
    self.assertEqual(target_response.json()['proposal_id'],target['proposal_id'])
    old_binding=dict(expected_revision=store.read()['revision'],target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
    regeneration=dict(event_id='http-reconfigure',reason='EXPLICIT_RECONFIGURE',expected_revision=store.read()['revision'],previous_target_id=target['target_id'])
    regenerated=client.post('/api/strategy-account/target/generate',json=regeneration)
    self.assertEqual(regenerated.status_code,200,regenerated.text)
    self.assertNotEqual(regenerated.json()['target_id'],target['target_id'])
    repeated=client.post('/api/strategy-account/target/generate',json=regeneration)
    self.assertEqual(repeated.status_code,200,repeated.text)
    self.assertEqual(repeated.json(),regenerated.json())
    with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_OR_TARGET'):news.bound_context(old_binding)
    self.assertEqual(start.call_count,1);self.assertFalse(stop.called)
   self.assertEqual(stop.call_count,1)
   self.assertGreaterEqual(len(calls),3)
   self.assertTrue(list(provider.root.rglob('*.transport.json')))
   self.assertTrue(list(provider.root.rglob('halt_pullback_caps_v2_*.sqlite3')))
   target=view.current();current=store.read();request=dict(expected_revision=current['revision'],target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
   with patch.object(type(provider),'_assemble',side_effect=AssertionError('NATIVE_REQUIRED_REVIEW')) as guard:
    with self.assertRaisesRegex(AssertionError,'NATIVE_REQUIRED_REVIEW'):service.preview(**request)
    self.assertEqual(guard.call_count,1)
   transport_mode['halt_ok']=False
   blocked=service.preview(**request)
   self.assertTrue(all(order['side']=='SELL' for order in blocked.get('new_orders',[])),blocked)
   self.assertTrue(blocked.get('buy_data_failure') or blocked['status']=='WAIT',blocked)
   self.assertEqual(store.read(),current)

if __name__=='__main__':unittest.main()




