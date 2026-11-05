"""Isolated target-bound production admission with real protected transports."""
import test_split_three_clock_daily_20261105 as daily_fixture
from test_split_three_clock_daily_20261105 import digest, canonical, ROOT
from copy import deepcopy
from contextlib import closing,nullcontext
from datetime import datetime,timedelta
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import json,gzip,unittest,sqlite3
import test_saved_frontier_isolated_pipeline as pipeline
from docs.candidates import split_production_admission_20261105 as admission
from docs.candidates.split_three_clock_daily_evidence_20261105 import project_split_frontier_daily
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.current_quantity_v2_paper_action_sources import daily_url
from data.strategy_execution_halt_evidence_v1 import HEADER
from data import strategy_halt_gzip_capture_v1 as halt

class Tests(unittest.TestCase):
 case=daily_fixture.Tests.case
 def test_target_bound_split_protected_admission(self):
  for mode in ['cash','zero','recent_null']:
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
    provider=pipeline.offline_provider(c,now)
    from data.current_quantity_v2_pullback_runtime import PullbackCapStore
    legacy=provider.limits.keywords['cap_store']
    PullbackCapStore(legacy.path,clock=legacy.clock,max_history_rows=legacy.max_history_rows,max_history_bytes=legacy.max_history_bytes)
    raw_fetch=provider.market.fetch
    def split_quote(ticker):
     doc=json.loads(raw_fetch(ticker))
     if ticker=='A':
      series=doc['chart']['result'][0];series['meta']['regularMarketPrice']/=8
      for key in ('open','high','low','close'):series['indicators']['quote'][0][key]=[v/8 for v in series['indicators']['quote'][0][key]]
     if ticker=='B' and mode=='recent_null':
      for key in ('open','high','low','close','volume'):doc['chart']['result'][0]['indicators']['quote'][0][key][-1]=None
     return canonical(doc)
    provider.market.fetch=split_quote
    epoch=int(datetime.fromisoformat('2026-10-22T13:30:00+00:00').timestamp())
    def fetch(ticker,start,end):
     events={'splits':{str(epoch):dict(date=epoch,numerator=8,denominator=1,splitRatio='8:1')}} if ticker=='A' else {}
     return dict(status=200,url=daily_url(ticker,start,end),body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events=events)]))))
    provider.actions=StrategyAccountActionCapture(fetch=fetch,clock=lambda:now[0],rss_fetch=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Fri, 23 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
    # Actual pinned identity validator, using temporary reviewed synthetic identity bytes.
    identity_raw=canonical(dict(candidates=[dict(ticker=x,security_id=x,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity-proof']) for x in 'ABDE'],source_hashes={'identity-proof':digest(b'controlled identity proof')}))
    (c['root']/'identities.json').write_bytes(identity_raw);(c['root']/'identity-proof').write_bytes(b'controlled identity proof')
    configuration=dict(identity_manifest='identities.json',identity_sha256=digest(identity_raw))
    runtime=SimpleNamespace(execution_provider=provider.execution,selection=SimpleNamespace(fees='1'))
    monthly=SimpleNamespace(root=c['root'],accounts=accounts,current=lambda:deepcopy(c['target']),snapshot_operation=nullcontext,validate_current_target_pins=lambda:None,_for_target=lambda target:(runtime,configuration))
    def reader(state,target,at,*,proposal):return project_split_frontier_daily(**dict(args,state=state,now=at.isoformat()))
    checks=[]
    service=admission.SplitProductionRollingAdmission(monthly=monthly,monthly_view=SimpleNamespace(require_proposal=lambda **kw:deepcopy(c['proposal'])),reader=reader,clock=lambda:now[0],validate_code=lambda:checks.append(True),policy_execution_enabled=True,policy_id='SPLIT_SAVED_FRONTIER_CONTENT_ONLY_V1')
    halt_body=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode()
    wire=gzip.compress(halt_body)
    real_halt=admission.HaltMarketCaptureV1
    def wrapped(market,**kw):return real_halt(market,fetch=lambda:dict(url=halt.SOURCE_URL,status=200,headers={'Content-Encoding':'gzip'},body=wire),**kw)
    from data import strategy_rss_gzip_capture_v1 as rss_capture,official_rss_gzip_transport_v1 as rss_wire
    rss_body=provider.actions.rss_fetch()['body'].replace(b'<channel>',b'<channel><pubDate>Fri, 23 Oct 2026 13:59:00 GMT</pubDate>');rss_bytes=gzip.compress(rss_body)
    def transport(**kw):return rss_wire.GzipRssTransport(fetch=lambda:dict(url=rss_wire.URL,status=200,headers={'Content-Encoding':'gzip'},body=rss_bytes),**kw)
    failures=[];real_limits=admission.build_timed_limits
    def limits(**kw):
     try:return real_limits(**kw)
     except Exception as error:failures.append(error);raise
    real_composition=admission.SavedFrontierDailyComposition
    def make_composition(**kw):
     import time
     def wait(seconds):
      before=time.monotonic();time.sleep(seconds);now[0]+=timedelta(seconds=time.monotonic()-before)
     return real_composition(sleep=wait,**kw)
    original=accounts.read()
    with patch.object(admission,'SavedFrontierDailyComposition',make_composition),patch.object(admission,'build_timed_limits',limits),patch.object(rss_capture,'GzipRssTransport',transport),patch.object(admission,'HaltMarketCaptureV1',wrapped),patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
     answer=service.preview(expected_revision=original['revision'],target_id=c['target']['target_id'],expected_proposal_id=c['proposal']['proposal_id'])
    self.assertEqual(answer['status'],'READY',answer)
    self.assertEqual(accounts.read(),original);self.assertEqual(len(checks),2)
    self.assertEqual(next(o['quantity'] for o in answer['new_orders'] if o['security_id']=='A'),16)
    self.assertTrue(list(c['root'].rglob('halt_pullback_caps_v2_*.sqlite3')))
    self.assertTrue(list(c['root'].rglob('*.transport.json')))
    with closing(sqlite3.connect(args['risk_path'])) as con:self.assertEqual(con.execute('SELECT payload,digest FROM split_preparation').fetchone(),original_preparation)
    if mode=='recent_null':
     self.assertTrue(any(isinstance(e,admission.retry.RecentClosedMinuteUnavailable) for e in failures),[str(e) for e in failures])
     self.assertTrue(all(o['side']=='SELL' for o in answer['new_orders']))
    if mode=='zero':self.assertTrue(all(o['side']=='SELL' for o in answer['new_orders']))
if __name__=='__main__':unittest.main()
