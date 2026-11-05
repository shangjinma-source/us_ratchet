"""Synthetic server authority; real capture codec/archive/normalizer/risk execution."""
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
from docs.candidates.split_native_capture_review_20261105 import NativeCaptureReview,digest

class Tests(unittest.TestCase):
 def test_real_capture_builds_review_and_rejects_new_dividend_and_changed_baseline(self):
  with TemporaryDirectory(dir=fixture.ROOT/'tmp') as folder:
   monthly,store,target,proposal,args=fixture.Tests().case(folder)
   base=json.loads(args['review_bytes']);original=args['files'];documents=base['documents']
   calendar=json.loads(original[documents['calendar']]);identities=json.loads(original[documents['identities']])['securities']
   evidence={k:v for k,v in original.items() if k not in set(documents['raw_by_security'].values())|set(documents['unit_reviews'].values())|{documents['normalized_inputs']}}
   permissions={};inputs=json.loads(original[documents['normalized_inputs']])
   for sid,path in documents['unit_reviews'].items():
    unit=json.loads(original[path]);nr=unit['raw_normalization'];baseline='baseline/'+sid
    evidence[baseline]=canonical(dict(security_id=sid,unit_id=nr['current_unit_id'],closes={r['date']:r['close'] for r in inputs['histories'][sid]['closes']}))
    permissions[sid]={k:nr[k] for k in ['price_basis','basis_asof','current_unit_id','split_schedule','reviewed_dividends']};permissions[sid]['baseline']=baseline;permissions[sid]['reviewed_dividends']=[dict(date='2026-11-02',provider_amount='0.25')]
   grant=dict(schema='NATIVE_CAPTURE_SOURCE_AUTHORIZATION_V1',pending_rights=[],unresolved_units=[],target_id=target['target_id'],proposal_id=proposal['proposal_id'],reviewed_at='2026-11-03T14:00:00+00:00',valid_until='2026-11-03T20:00:00+00:00',calendar=documents['calendar'],identities=documents['identities'],timing_bundles=base['timing_bundles'],securities=permissions,source_sha256={k:digest(v) for k,v in evidence.items()})
   reviewer=NativeCaptureReview(research_root=args['research_root'],authorization_bytes=canonical(grant),authorization_sha256=digest(canonical(grant)),files=evidence)
   view=SavedFrontierMonthlyView(monthly=monthly,proposals=SavedFrontierProposalStore(Path(folder)/'proposals.sqlite3'),validate_sources=monthly.selection._pins)
   now=[datetime.fromisoformat(args['now'])];mode=['normal'];saved=[];calls=[]
   def clock():now[0]+=timedelta(milliseconds=1);return now[0]
   def fetch(ticker,begin,end):
    now[0]+=timedelta(seconds=1);sid=next(s for s,i in identities.items() if i['ticker']==ticker)
    raw=json.loads(original[documents['raw_by_security'][sid]]);series=raw['chart']['result'][0]
    series['events']={'dividends':{'known':{'date':series['timestamp'][-1],'amount':.25}}}
    series['indicators']['adjclose'][0]['adjclose']=[1]*len(series['timestamp']) # never infer split basis from adjclose
    if mode[0]=='dividend':series['events']={'dividends':{'unknown':{'date':series['timestamp'][-1],'amount':.50}}}
    if mode[0]=='price':series['indicators']['quote'][0]['close'][0]*=2
    return dict(status=200,url=daily_url(ticker,begin,end),body=canonical(raw))
   def rss():return dict(status=200,url=URL,headers={'Content-Encoding':'gzip'},body=gzip.compress(b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 13:00:00 GMT</pubDate><item><title>Unrelated</title><pubDate>Tue, 03 Nov 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
   def capture_review(**kw):
    calls.append(kw);value=reviewer(**kw);saved.append(value);return value
   context=dict(calendar=calendar,identities=identities)
   reader=NativeMonthCaptureReader(monthly_view=view,risk_store=MonthlyPeakExitStore(args['risk_path']),research_root=args['research_root'],capture_root=Path(folder)/'captures',context_sha256=digest(canonical(context)),review_capture=capture_review,clock=clock,validate_sources=monthly.selection._pins,fetch_daily=fetch,**context)
   before=store.read()
   with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('data.strategy_monthly_supplement_gzip_v1.GzipRssTransport',side_effect=lambda **kw:GzipRssTransport(fetch=rss,**kw)):
    result=reader(before,target,clock(),proposal=proposal)
    self.assertEqual(result['status'],'DAILY_SIGNAL_READY');self.assertFalse(result['automatic_source_approval'])
    self.assertEqual(store.read(),before);prior=reader.risk.read(before['account_id'])
    self.assertIn('authorization.json',saved[0]['files'])
    for kind,error in [('dividend','RAW_DIVIDEND_REVIEW_MISMATCH'),('price','CAPTURE_BASELINE_CONTINUITY')]:
     mode[0]=kind;now[0]+=timedelta(minutes=16)
     with self.assertRaisesRegex(ValueError,error):reader(before,target,clock(),proposal=proposal)
     self.assertEqual(reader.risk.read(before['account_id']),prior)
   from copy import deepcopy
   for change,error in [('basis','CAPTURE_BASIS_FUTURE_AUTHORIZATION'),('baseline','CAPTURE_BASELINE_TIME_OR_PRICE'),('target','CAPTURE_AUTH_TARGET')]:
    altered=deepcopy(grant);changed_files=dict(evidence)
    if change=='basis':altered['securities'][next(iter(permissions))]['basis_asof']='2026-11-03T14:59:00+00:00'
    elif change=='target':altered['target_id']='0'*64
    else:
     path=permissions[next(iter(permissions))]['baseline'];doc=json.loads(changed_files[path]);doc['closes']['2026-11-03']='10';changed_files[path]=canonical(doc);altered['source_sha256'][path]=digest(changed_files[path])
    changed=NativeCaptureReview(research_root=args['research_root'],authorization_bytes=canonical(altered),authorization_sha256=digest(canonical(altered)),files=changed_files)
    with self.assertRaisesRegex(ValueError,error):changed(**calls[0])
    self.assertEqual(reader.risk.read(before['account_id']),prior)
   altered=deepcopy(grant);altered['pending_rights']=[dict(security_id=next(iter(permissions)),kind='UNRESOLVED_DIVIDEND')]
   changed=NativeCaptureReview(research_root=args['research_root'],authorization_bytes=canonical(altered),authorization_sha256=digest(canonical(altered)),files=evidence)
   kwargs=deepcopy(calls[0]);kwargs['risk_state']=prior
   admitted=changed(**kwargs)
   self.assertEqual(json.loads(admitted['review_bytes'])['pending_rights'],altered['pending_rights'])
   from docs.candidates.split_native_month_daily_20261105 import project_native_month_daily
   with self.assertRaisesRegex(ValueError,'FRONTIER_REVIEW_SCOPE'):
    project_native_month_daily(research_root=args['research_root'],risk_path=args['risk_path'],target_id=target['target_id'],state=before,now=kwargs['now'].isoformat(),enabled=True,**admitted)
   self.assertEqual(reader.risk.read(before['account_id']),prior)
   with self.assertRaisesRegex(ValueError,'CAPTURE_AUTH_HASH'):NativeCaptureReview(research_root=args['research_root'],authorization_bytes=canonical(grant),authorization_sha256='0'*64,files=evidence)
if __name__=='__main__':unittest.main()
