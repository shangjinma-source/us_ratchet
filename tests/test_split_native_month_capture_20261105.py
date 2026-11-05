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
 def test_capture_exact_receipts_native_risk_and_midcapture_cash_rejection(self):
  with TemporaryDirectory(dir=fixture.ROOT/'tmp') as folder:
   monthly,store,target,proposal,args=fixture.Tests().case(folder)
   view=SavedFrontierMonthlyView(monthly=monthly,proposals=SavedFrontierProposalStore(Path(folder)/'proposals.sqlite3'),validate_sources=monthly.selection._pins)
   base=json.loads(args['review_bytes']);files=args['files'];calendar=json.loads(files[base['documents']['calendar']]);identities=json.loads(files[base['documents']['identities']])['securities']
   context=dict(calendar=calendar,identities=identities);clockvalues=[datetime.fromisoformat(args['now'])]
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
    result=deepcopy(files);review=deepcopy(base);inputs=json.loads(result[review['documents']['normalized_inputs']]);inputs['observed_at']=now.isoformat();result[review['documents']['normalized_inputs']]=canonical(inputs)
    received={}
    for sid,path in capture['documents']['action_receipts'].items():
     receipt=json.loads(capture['files'][path]);received[sid]=receipt['received_at'];receipts.append(receipt)
     unitpath=review['documents']['unit_reviews'][sid];unit=json.loads(result[unitpath]);unit['reviewed_at']=now.isoformat();unit['raw_normalization'].update(captured_at=receipt['received_at'],basis_asof=receipt['received_at']);result[unitpath]=canonical(unit)
    review.update(source_received_by_security=received,source_received_at=max(received.values(),key=datetime.fromisoformat),reviewed_at=now.isoformat())
    for path,raw in capture['files'].items():result['capture/'+path]=raw
    review['source_sha256']={n:fixture.digest(r) for n,r in result.items()}
    return dict(review_bytes=canonical(review),trusted_review_sha256=fixture.digest(canonical(review)),files=result)
   reader=NativeMonthCaptureReader(monthly_view=view,risk_store=MonthlyPeakExitStore(args['risk_path']),research_root=args['research_root'],capture_root=Path(folder)/'captures',context_sha256=fixture.digest(canonical(context)),review_capture=reviewer,clock=clock,validate_sources=monthly.selection._pins,fetch_daily=daily_fetch,**context)
   before=store.read()
   with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('data.strategy_monthly_supplement_gzip_v1.GzipRssTransport',side_effect=lambda **kw:GzipRssTransport(fetch=rss_fetch,**kw)):
    result=reader(before,target,clock(),proposal=proposal)
   self.assertEqual(result['status'],'DAILY_SIGNAL_READY');self.assertFalse(result['automatic_source_approval']);self.assertEqual(store.read(),before)
   self.assertEqual(len({r['received_at'] for r in receipts}),len(identities))
   prior=reader.risk.read(before['account_id']);clockvalues[0]+=timedelta(minutes=16);mutation[0]=True
   with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('data.strategy_monthly_supplement_gzip_v1.GzipRssTransport',side_effect=lambda **kw:GzipRssTransport(fetch=rss_fetch,**kw)):
    with self.assertRaisesRegex(ValueError,'NATIVE_CAPTURE_ACCOUNT_OR_TARGET_CHANGED'):reader(before,target,clock(),proposal=proposal)
   self.assertEqual(reader.risk.read(before['account_id']),prior)
if __name__=='__main__':unittest.main()
