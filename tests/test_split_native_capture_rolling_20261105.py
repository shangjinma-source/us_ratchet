"""Real durable daily/RSS gzip capture into native monthly raw review and risk."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import gzip,json,unittest
import test_split_native_month_daily_20261105 as fixture
from core.strategy_account_ledger import canonical
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView,SavedFrontierProposalStore
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.official_rss_gzip_transport_v1 import GzipRssTransport,URL
from data.current_quantity_v2_paper_action_sources import daily_url
from docs.candidates.split_native_month_capture_20261105 import NativeMonthCaptureReader

class Tests(unittest.TestCase):
 def test_actual_capture_through_protected_rolling_admission(self):
  with TemporaryDirectory(dir=fixture.ROOT/'tmp') as folder:
   monthly,store,target,proposal,args=fixture.Tests().case(folder)
   view=SavedFrontierMonthlyView(monthly=monthly,proposals=SavedFrontierProposalStore(Path(folder)/'proposals.sqlite3'),validate_sources=monthly.selection._pins)
   base=json.loads(args['review_bytes']);files=args['files'];calendar=json.loads(files[base['documents']['calendar']]);identities=json.loads(files[base['documents']['identities']])['securities']
   context=dict(calendar=calendar,identities=identities);clockvalues=[datetime.fromisoformat(args['now'])-timedelta(seconds=1)]
   def clock():
    clockvalues[0]+=timedelta(milliseconds=1);return clockvalues[0]
   ticker_sid={v['ticker']:s for s,v in identities.items()};mutation=[False];receipts=[]
   def daily_fetch(ticker,begin,end):
    clockvalues[0]+=timedelta(seconds=1)
    if mutation[0]:
     store.append(dict(event_id='mid-capture',kind='CASH_CONFIRM',amount='90',cash_basis='TOTAL_UNINVESTED'),expected_revision=store.read()['revision']);mutation[0]=False
    return dict(status=200,url=daily_url(ticker,begin,end),body=files[base['documents']['raw_by_security'][ticker_sid[ticker]]])
   def rss_fetch():return dict(status=200,url=URL,headers={'Content-Encoding':'gzip'},body=gzip.compress(b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 13:00:00 GMT</pubDate><item><title>Unrelated</title><pubDate>Tue, 03 Nov 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
   def reviewer(*,capture,prepared,state,target,proposal,risk_state,now):
    # Explicit synthetic server authority; not a production vendor-basis certification.
    result=deepcopy(files);review=deepcopy(base);review['risk_state_sha256']=fixture.digest(canonical(risk_state));inputs=json.loads(result[review['documents']['normalized_inputs']]);inputs['observed_at']=now.isoformat();result[review['documents']['normalized_inputs']]=canonical(inputs)
    received={}
    for sid,path in capture['documents']['action_receipts'].items():
     receipt=json.loads(capture['files'][path]);received[sid]=receipt['received_at'];receipts.append(receipt)
     unitpath=review['documents']['unit_reviews'][sid];unit=json.loads(result[unitpath]);unit['reviewed_at']=now.isoformat();unit['raw_normalization'].update(captured_at=receipt['received_at'],basis_asof=receipt['received_at']);result[unitpath]=canonical(unit)
    review.update(source_received_by_security=received,source_received_at=max(received.values(),key=datetime.fromisoformat),reviewed_at=now.isoformat())
    for path,raw in capture['files'].items():result['capture/'+path]=raw
    review['source_sha256']={n:fixture.digest(r) for n,r in result.items()}
    return dict(review_bytes=canonical(review),trusted_review_sha256=fixture.digest(canonical(review)),files=result)
   reader=NativeMonthCaptureReader(monthly_view=view,risk_store=MonthlyPeakExitStore(args['risk_path']),research_root=args['research_root'],capture_root=Path(folder)/'captures',context_sha256=fixture.digest(canonical(context)),review_capture=reviewer,clock=clock,validate_sources=monthly.selection._pins,fetch_daily=daily_fetch,**context)
   # Unwrap only fixture instrumentation, preserving the actual factory Provider.
   from types import SimpleNamespace
   from docs.candidates import split_native_rolling_admission_20261105 as admission
   from data.strategy_execution_halt_evidence_v1 import HEADER
   from data import strategy_halt_gzip_capture_v1 as halt
   from data.current_quantity_v2_pullback_runtime import PullbackCapStore
   provider=monthly.execution_provider.__self__
   market=next(c.cell_contents for c in provider.market.capture.__closure__ if hasattr(c.cell_contents,'fetch'))
   provider.market=market;provider.clock=clock;market.clock=clock;provider.actions.clock=clock
   original_fetch=market.fetch;attempts={};mode={'bad_halt':False}
   def minute_fetch(ticker):
    attempts[ticker]=attempts.get(ticker,0)+1
    raw=json.loads(original_fetch(ticker));row=raw['chart']['result'][0]
    at=clock();last=int(at.timestamp());opened=int(at.replace(hour=14,minute=30,second=0,microsecond=0).timestamp())
    row['meta']['regularMarketTime']=last;row['meta']['currentTradingPeriod']['regular'].update(start=opened,end=opened+23400)
    timestamps=list(range(opened,last-last%60,60))
    # First buy quote is incomplete; original retry must obtain a full second response.
    row['timestamp']=timestamps;row['indicators']['quote'][0]={k:[v]*len(timestamps) for k,v in dict(open=10,high=11,low=9,close=10,volume=10).items()}
    if ticker=='BBB' and attempts[ticker]==1:
     for field in ('open','high','low','close','volume'):row['indicators']['quote'][0][field][-1]=None
    return canonical(raw)
   market.fetch=minute_fetch
   legacy=provider.limits.keywords['cap_store'];legacy.clock=lambda:clock().isoformat();PullbackCapStore(legacy.path,clock=legacy.clock,max_history_rows=legacy.max_history_rows,max_history_bytes=legacy.max_history_bytes)
   identity=canonical(dict(candidates=[dict(ticker=t,security_id=s,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['integration-identity']) for t,s in ticker_sid.items()],source_hashes={'integration-identity':fixture.digest(b'controlled proof')}))
   (provider.root/'integration-identities.json').write_bytes(identity);(provider.root/'integration-identity').write_bytes(b'controlled proof')
   configuration=dict(identity_manifest='integration-identities.json',identity_sha256=fixture.digest(identity))
   def for_target(value):
    self.assertEqual(value,monthly.current());monthly.validate_current_target_pins();return monthly,deepcopy(configuration)
   routed=SimpleNamespace(accounts=monthly.accounts,root=provider.root,current=monthly.current,snapshot_operation=monthly.snapshot_operation,validate_current_target_pins=monthly.validate_current_target_pins,_for_target=for_target)
   service=admission.NativeSplitRollingAdmission(monthly=routed,monthly_view=view,reader=reader,clock=clock,validate_code=monthly.selection._pins,timing_bundles=base['timing_bundles'],policy_execution_enabled=True,policy_id='SPLIT_NATIVE_MONTH_CONTENT_ONLY_V1')
   body=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode();wire=gzip.compress(body);real_halt=admission.HaltMarketCaptureV1
   def wrapped(market,**kw):return real_halt(market,fetch=lambda:dict(url=halt.SOURCE_URL,status=200,headers={'Content-Encoding':'gzip'},body=b'bad' if mode['bad_halt'] else wire),**kw)
   from data import strategy_rss_gzip_capture_v1 as rss_capture
   self.enterContext(patch.object(admission,'HaltMarketCaptureV1',wrapped));self.enterContext(patch.object(rss_capture,'GzipRssTransport',side_effect=lambda **kw:GzipRssTransport(fetch=rss_fetch,**kw)))
   import time
   real_sleep=time.sleep
   def wait(seconds):
    real_sleep(seconds);clockvalues[0]+=timedelta(seconds=seconds)
   self.enterContext(patch('data.saved_frontier_daily_composition_v1.time.sleep',side_effect=wait))
   before=store.read()
   request=dict(expected_revision=before['revision'],target_id=target['target_id'],expected_proposal_id=proposal['proposal_id'])
   with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('data.strategy_monthly_supplement_gzip_v1.GzipRssTransport',side_effect=lambda **kw:GzipRssTransport(fetch=rss_fetch,**kw)):
    result=service.preview(**request)
   self.assertEqual(result['status'],'READY',result);self.assertTrue(result['new_orders']);self.assertEqual(store.read(),before)
   self.assertGreaterEqual(attempts['BBB'],2)
   self.assertEqual(len({r['received_at'] for r in receipts}),len(identities))
   self.assertTrue(list(provider.root.rglob('halt_pullback_caps_v2_*.sqlite3')))
   self.assertTrue(list((Path(folder)/'captures').rglob('complete.json')))
   # A later malformed gzip halt response remains a hard refusal, not stale advice.
   mode['bad_halt']=True;clockvalues[0]+=timedelta(minutes=1)
   with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('data.strategy_monthly_supplement_gzip_v1.GzipRssTransport',side_effect=lambda **kw:GzipRssTransport(fetch=rss_fetch,**kw)):
    blocked=service.preview(**request)
   self.assertTrue(all(o['side']=='SELL' for o in blocked.get('new_orders',[])),blocked)
   self.assertTrue(blocked.get('buy_data_failure') or blocked['status']=='WAIT',blocked)
   failures=[json.loads(p.read_bytes()).get('reason') for p in provider.root.rglob('receipt.json')]
   self.assertIn('RSS_GZIP_INTEGRITY_FAILED',failures)
   print('NATIVE_CAPTURE_ROLLING_DIAGNOSTIC',attempts,blocked.get('buy_data_failure'))
   self.assertEqual(store.read(),before)
if __name__=='__main__':unittest.main()


