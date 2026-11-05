"""Protected HTTP composition: real halt/gzip admission, fill and news binding.

The monthly fixture serves a pinned existing target only; selection is not proven.
"""
from contextlib import nullcontext, closing
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json, sqlite3, unittest, gzip
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.saved_frontier_monthly_view_v1 import SavedFrontierProposalStore, SavedFrontierMonthlyView
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.current_quantity_v2_paper_action_sources import daily_url
from data.news_risk_skill_v1 import PINS
from docs.candidates.split_runtime_routes_20261105 import build_routes
from docs.candidates import split_production_admission_20261105 as admission
from data.strategy_execution_halt_evidence_v1 import HEADER
from data import strategy_halt_gzip_capture_v1 as halt
from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider
from docs.candidates.strategy_account_split_market_capture import StrategyAccountMarketCapture
from docs.candidates.strategy_account_split_execution_limits import build_execution_limits
from docs.candidates.split_three_clock_daily_evidence_20261105 import project_split_frontier_daily
import test_split_three_clock_daily_20261105 as fixture
from test_split_three_clock_daily_20261105 import ROOT, digest
import test_saved_frontier_isolated_pipeline as pipeline

class Tests(unittest.TestCase):
 def test_cash_current_and_news_share_fresh_generation(self):
  with TemporaryDirectory(dir=ROOT/'tmp') as folder:
   c,accounts,args=fixture.Tests().case(folder,'AS_TRADED',held_split=True)
   # Keep the real open BUY reservation: cash field is broker available cash.
   now=[datetime.fromisoformat(c['now'])]
   provider=pipeline.offline_provider(c,now)
   from data.current_quantity_v2_pullback_runtime import PullbackCapStore
   legacy=provider.limits.keywords['cap_store']
   PullbackCapStore(legacy.path,clock=legacy.clock,max_history_rows=legacy.max_history_rows,max_history_bytes=legacy.max_history_bytes)
   original_fetch=provider.market.fetch
   def quote(ticker):
    document=json.loads(original_fetch(ticker))
    if ticker=='A':
     series=document['chart']['result'][0];series['meta']['regularMarketPrice']/=8
     for key in ('open','high','low','close'):series['indicators']['quote'][0][key]=[v/8 for v in series['indicators']['quote'][0][key]]
    return canonical(document)
   provider.market.fetch=quote
   epoch=int(datetime.fromisoformat('2026-10-22T13:30:00+00:00').timestamp())
   def actions(ticker,start,end):
    events={'splits':{str(epoch):dict(date=epoch,numerator=8,denominator=1,splitRatio='8:1')}} if ticker=='A' else {}
    return dict(status=200,url=daily_url(ticker,start,end),body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events=events)]))))
   provider.actions=StrategyAccountActionCapture(fetch=actions,clock=lambda:now[0],rss_fetch=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Fri, 23 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
   frozen=deepcopy(c['target'])
   def validate():
    self.assertEqual(c['target'],frozen)
   identity_raw=canonical(dict(candidates=[dict(ticker=x,security_id=x,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity-proof']) for x in 'ABDE'],source_hashes={'identity-proof':digest(b'controlled identity proof')}))
   (c['root']/'identities.json').write_bytes(identity_raw);(c['root']/'identity-proof').write_bytes(b'controlled identity proof')
   configuration=dict(identity_manifest='identities.json',identity_sha256=digest(identity_raw))
   runtime=SimpleNamespace(execution_provider=provider.execution,selection=SimpleNamespace(fees='1'))
   def for_target(target):
    self.assertEqual(target,frozen)
    return runtime,deepcopy(configuration)
   monthly=SimpleNamespace(root=c['root'],accounts=accounts,current=lambda:deepcopy(frozen),snapshot_operation=nullcontext,validate_current_target_pins=validate,_month=lambda:'2026-10',_for_target=for_target)
   proposals=SavedFrontierProposalStore(Path(folder)/'proposals.sqlite3');proposals.bind(frozen)
   view=SavedFrontierMonthlyView(monthly=monthly,proposals=proposals,validate_sources=validate)
   def reader(state,target,at,*,proposal):
    # Controlled new source receipt bound to the actual current revision. This
    # fixture is not a production raw-source authorization mechanism.
    review=json.loads(args['review_bytes']);review['account_revision']=state['revision']
    files=deepcopy(args['files'])
    for event in state['events']:
     identity=event['payload'].get('identity_evidence',{})
     for path,expected in identity.get('source_hashes',{}).items():
      if path not in files:
       files[path]=provider.market.identity._read(path,expected)
       self.assertEqual(digest(files[path]),expected)
    review['source_sha256']={name:digest(raw) for name,raw in files.items()};raw=canonical(review)
    return project_split_frontier_daily(**dict(args,files=files,state=state,now=at.isoformat(),review_bytes=raw,trusted_review_sha256=digest(raw)))
   daily=admission.SplitProductionRollingAdmission(monthly=monthly,monthly_view=view,reader=reader,clock=lambda:now[0],validate_code=validate,policy_execution_enabled=True,policy_id='SPLIT_SAVED_FRONTIER_CONTENT_ONLY_V1')
   halt_body=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode()
   wire=gzip.compress(halt_body);real_halt=admission.HaltMarketCaptureV1
   def wrapped(market,**kw):return real_halt(market,fetch=lambda:dict(url=halt.SOURCE_URL,status=200,headers={'Content-Encoding':'gzip'},body=wire),**kw)
   from data import strategy_rss_gzip_capture_v1 as rss_capture,official_rss_gzip_transport_v1 as rss_wire
   rss_body=provider.actions.rss_fetch()['body'].replace(b'<channel>',b'<channel><pubDate>Fri, 23 Oct 2026 13:59:00 GMT</pubDate>');rss_bytes=gzip.compress(rss_body)
   def transport(**kw):return rss_wire.GzipRssTransport(fetch=lambda:dict(url=rss_wire.URL,status=200,headers={'Content-Encoding':'gzip'},body=rss_bytes),**kw)
   self.enterContext(patch.object(admission,'HaltMarketCaptureV1',wrapped))
   self.enterContext(patch.object(rss_capture,'GzipRssTransport',transport))
   with closing(sqlite3.connect(args['risk_path'])) as connection:
    transition=json.loads(connection.execute('SELECT payload FROM split_preparation').fetchone()[0])['transition']
   for name in PINS:
    destination=Path(folder)/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes((ROOT/name).read_bytes())
   start=self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.start_worker'))
   stop=self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.stop_worker'))
   prepared=build_routes(root=Path(folder),monthly_view=view,daily_service=daily,journal=DailyAdviceJournalV1(Path(folder)/'journal.sqlite3'),clock=lambda:now[0],validate_sources=validate,policy_references={'candidate':'isolated-only'},timing_bundles={'split-A':transition['payload']['timing_bundle']},account_arguments=dict(database_path=accounts.path,account_id=accounts.read()['account_id'],resolver=provider.market.identity,clock=lambda:now[0]))
   self.assertIs(prepared['news_service'].preview.__self__,prepared['observed_daily'])
   self.assertIs(prepared['current_advice'].monthly,view)
   app=FastAPI();app.include_router(prepared['router'])
   # Preserve and execute the actual merged lifespan, stub only worker transport.
   import socket
   real_connect=socket.socket.connect
   def offline_connect(sock,address):
    if isinstance(address,tuple) and address[0] in ('127.0.0.1','::1'):return real_connect(sock,address)
    raise AssertionError('EXTERNAL_NETWORK_FORBIDDEN')
   with patch('socket.socket.connect',offline_connect),TestClient(app) as client:
    before=client.get('/api/strategy-account').json()['account']
    response=client.post('/api/strategy-account/events',json=dict(expected_revision=before['revision'],event=dict(event_id='http-available',kind='CASH_CONFIRM',amount='15000',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
    self.assertEqual(response.status_code,200,response.text)
    state=accounts.read();self.assertEqual(state['available_cash'],'15000')
    self.assertTrue(any(o['status']=='OPEN' and o['side']=='BUY' for o in state['orders'].values()))
    result=client.get('/api/strategy-daily-v3/current')
    self.assertEqual(result.status_code,200,result.text)
    waiting=result.json();self.assertEqual(waiting['daily']['detail_status'],'WAIT_PENDING_RECONCILIATION')
    self.assertEqual(waiting['account']['available_cash'],'15000')
    self.assertEqual(waiting['account']['reserved_cash'],'20')
    self.assertEqual(prepared['news_service'].context()[0],state)
    cancelled=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=dict(event_id='cancel-E-http',kind='CANCEL',order_id='old-open-E')))
    self.assertEqual(cancelled.status_code,200,cancelled.text)
    state=accounts.read()
    confirmed=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=dict(event_id='confirm-after-cancel',kind='CASH_CONFIRM',amount='15020',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
    self.assertEqual(confirmed.status_code,200,confirmed.text);state=accounts.read()
    result=client.get('/api/strategy-daily-v3/current');self.assertEqual(result.status_code,200,result.text)
    body=result.json();self.assertEqual(body['daily']['status'],'READY',{k:v for k,v in body['daily'].items() if k!='verified_snapshot'})
    self.assertEqual(body['account']['revision'],state['revision'])
    self.assertEqual(body['daily']['account_revision'],state['revision'])
    self.assertEqual(next(o['quantity'] for o in body['daily']['new_orders'] if o['security_id']=='A'),16)
    news_account,news_target,names=prepared['news_service'].context()
    self.assertEqual(news_account,state);self.assertEqual(news_target,view.current())
    self.assertEqual(news_target['proposal_id'],body['daily']['proposal_id'])
    self.assertEqual(accounts.read(),state)
    old_binding=dict(expected_revision=state['revision'],target_id=news_target['target_id'],expected_proposal_id=news_target['proposal_id'])
    self.assertEqual(prepared['news_service'].bound_context(old_binding)[0],state)
    fill=dict(event_id='user-sale-A',kind='DIRECT_FILL',ticker='A',side='SELL',quantity=16,price='8.8',fees='0',executed_at=now[0].isoformat())
    sold=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=fill))
    self.assertEqual(sold.status_code,200,sold.text)
    self.assertEqual(accounts.read()['shares'].get('A',0),0)
    with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_OR_TARGET'):
     prepared['news_service'].bound_context(old_binding)
    after=accounts.read()
    retry=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],event=fill))
    self.assertEqual(retry.status_code,200,retry.text);self.assertEqual(accounts.read(),after)
    reconfirm=client.post('/api/strategy-account/events',json=dict(expected_revision=after['revision'],event=dict(event_id='cash-after-sale',kind='CASH_CONFIRM',amount='15160.8',cash_basis='AVAILABLE_AFTER_RESERVATIONS')))
    self.assertEqual(reconfirm.status_code,200,reconfirm.text)
    # A new request uses a genuinely later captured minute after the cash/fill change.
    now[0]+=timedelta(minutes=1)
    refreshed=client.get('/api/strategy-daily-v3/current')
    self.assertEqual(refreshed.status_code,200,refreshed.text)
    fresh=refreshed.json();self.assertEqual(fresh['daily']['status'],'READY',fresh)
    self.assertFalse(any(o['security_id']=='A' for o in fresh['daily']['new_orders']))
    self.assertEqual(fresh['account']['revision'],accounts.read()['revision'])
    self.assertEqual(prepared['news_service'].context()[0],accounts.read())
    self.assertTrue(list(c['root'].rglob('halt_pullback_caps_v2_*.sqlite3')))
    self.assertTrue(list(c['root'].rglob('*.transport.json')))
    stale=client.get('/api/strategy-daily-v3/current',params={'expected_revision':before['revision']})
    self.assertEqual(stale.status_code,409);self.assertEqual(stale.json()['reason'],'STALE_REVISION')
    self.assertEqual(start.call_count,1);self.assertFalse(stop.called)
   self.assertEqual(stop.call_count,1)
   self.assertFalse(prepared['production_activated']);self.assertFalse(prepared['monthly_generation_enabled'])

if __name__=='__main__':unittest.main()
