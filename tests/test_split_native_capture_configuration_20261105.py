"""Synthetic authorizations; real profiled router + configured capture/rolling path."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory
import gzip,json,unittest
import test_split_profiled_monthly_20261105 as fixture
from core.strategy_account_ledger import canonical
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView,SavedFrontierProposalStore
from data.saved_frontier_policy_archive import archive_saved_frontier_policy
from data.current_quantity_v2_pullback_runtime import PullbackCapStore
from data.current_quantity_v2_paper_action_sources import daily_url
from data.official_rss_gzip_transport_v1 import GzipRssTransport,URL
from data.strategy_execution_halt_evidence_v1 import HEADER
from data import strategy_halt_gzip_capture_v1 as halt, strategy_rss_gzip_capture_v1 as rss_capture
from docs.candidates import split_native_rolling_admission_20261105 as admission
from docs.candidates.split_native_capture_configuration_20261105 import ConfiguredNativeAdmission,SOURCE_PATHS,digest

class Tests(unittest.TestCase):
 def case(self):
  f=fixture.Tests();f.setUp();self.addCleanup(f.doCleanups)
  def gate():
   for name,expected in f.pins.items():
    self.assertEqual(digest((f.root/name).read_bytes()),expected);self.assertEqual(digest((fixture.ROOT/name).read_bytes()),expected)
  with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
   sessions=[];day=datetime(2025,1,1)
   while day.date()<=f.now.date():
    if day.weekday()<5 or day.date().isoformat()=='2026-11-01':
     d=day.date().isoformat();sessions.append(dict(date=d,open=d+'T14:30:00+00:00',close=d+'T21:00:00+00:00'))
    day+=timedelta(days=1)
   sessions[next(i for i,r in enumerate(sessions) if r['date']=='2026-11-01')]=deepcopy(f.timing['calendar']['sessions'][0])
   calendar=dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=sessions)
   f.timing['calendar']=dict(calendar,sessions=[r for r in sessions if r['date']<='2026-11-01']);f.timing['calendar_sha256']=digest(canonical(f.timing['calendar']))
   ready=f.prepare(f.f.entry,'configured-native');f.activation.adopt(receipt_path=ready['path'],receipt_sha256=ready['sha256'],expected_release_revision=0)
   router=fixture.module.SplitProfiledRouter(root=f.root,snapshot_provider=f.activation.snapshot,initial_snapshot=f.activation.snapshot(),approvals=f.approvals,clock=lambda:f.now,market_factory=f.market,action_factory=f.actions)
   view=SavedFrontierMonthlyView(monthly=router,proposals=SavedFrontierProposalStore(f.root/'data/strategy_account/proposal.sqlite3'),validate_sources=gate)
   target=view.generate(event_id='configured-native',reason='INITIAL',expected_revision=f.store.read()['revision'],previous_target_id=None)
   native=router.current();proposal=view.require_proposal(target_id=target['target_id'],expected_proposal_id=target['proposal_id']);state=f.store.read()
   runtime,_=router._for_target(native);provider=runtime.execution_provider.__self__
   legacy=provider.limits.keywords['cap_store'];PullbackCapStore(legacy.path,clock=legacy.clock,max_history_rows=legacy.max_history_rows,max_history_bytes=legacy.max_history_bytes)
   binding=native['payload']['decision']['payload']['input_binding'];allpins=dict(binding['source_hashes']);allpins.update(native['payload']['runtime_pins'])
   byhash={digest(p.read_bytes()):p.read_bytes() for p in f.root.rglob('*') if p.is_file()}
   sourcefiles={name:byhash[h] for name,h in allpins.items()}
   temporary=TemporaryDirectory(dir=fixture.ROOT/'tmp');self.addCleanup(temporary.cleanup);research=Path(temporary.name);archive_saved_frontier_policy(research_root=research,target=native,proposal=proposal,source_files=sourcefiles,enabled=True)
   domain={s for s,q in proposal['payload']['proposed_target_quantities'].items() if q}|{s for s,q in state['shares'].items() if q}
   files={'calendar':canonical(calendar),'identity-proof':b'explicit synthetic identity authority'};identities={};permissions={};raws={}
   for event in state['events']:
    for name,h in event['payload'].get('identity_evidence',{}).get('source_hashes',{}).items():files[name]=byhash[h]
   for sid in sorted(domain):
    ticker=binding['marks'][sid]['ticker'];unit='new' if sid=='A' else 'unit-'+sid
    issuer=binding['search_arguments']['metadata'].get(sid,{}).get('issuer_id','IA')
    identities[sid]=dict(security_id=sid,ticker=ticker,issuer_id=issuer,currency='USD',exchange='NMS',identity_reviewed=True,source_hashes={'identity-proof':digest(files['identity-proof'])})
    baseline='baseline/'+sid;files[baseline]=canonical(dict(security_id=sid,unit_id=unit,closes={'2026-11-30':'10'}))
    permissions[sid]=dict(price_basis='AS_TRADED',basis_asof='2026-12-01T14:00:00+00:00',current_unit_id=unit,split_schedule=[],reviewed_dividends=[],baseline=baseline)
    raws[ticker]=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',exchangeName='NMS',instrumentType='EQUITY'),timestamp=[int(datetime.fromisoformat('2026-11-30T14:30:00+00:00').timestamp())],events={},indicators=dict(quote=[dict(close=[10])],adjclose=[dict(adjclose=[9])]))])))
   files['identities']=canonical(dict(schema='SAVED_FRONTIER_REVIEWED_IDENTITIES_V1',securities=identities))
   grant=dict(schema='NATIVE_CAPTURE_SOURCE_AUTHORIZATION_V1',target_id=native['target_id'],proposal_id=proposal['proposal_id'],reviewed_at='2026-12-01T14:00:00+00:00',valid_until='2026-12-01T21:00:00+00:00',calendar='calendar',identities='identities',timing_bundles={'split-A':f.timing},securities=permissions,pending_rights=[],unresolved_units=[],source_sha256={k:digest(v) for k,v in files.items()})
   refs={}
   for name,raw in files.items():
    path=f.root/'authority'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);refs[name]=path.relative_to(f.root).as_posix()
   (f.root/'authority/grant.json').write_bytes(canonical(grant));pins={}
   for name in SOURCE_PATHS:
    raw=(fixture.ROOT/name).read_bytes();path=f.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);pins[name]=digest(raw)
   config=dict(schema='NATIVE_CAPTURE_RUNTIME_CANDIDATE_V1',production_activated=False,policy_execution_enabled=True,policy_id='SPLIT_NATIVE_MONTH_CONTENT_ONLY_V1',source_pins=pins,authorizations={native['target_id']:dict(path='authority/grant.json',sha256=digest(canonical(grant)),files=refs)})
   configraw=canonical(config);(f.root/'native-config.json').write_bytes(configraw)
   def daily(ticker,begin,end):return dict(status=200,url=daily_url(ticker,begin,end),body=raws[ticker])
   import sqlite3
   from contextlib import closing
   with closing(sqlite3.connect(research/'risk.sqlite3')) as connection:connection.execute('PRAGMA user_version=0')
   arguments=dict(root=f.root,configuration_path='native-config.json',configuration_sha256=digest(configraw),monthly=router,monthly_view=view,research_root=research,risk_path=research/'risk.sqlite3',capture_root=research/'captures',clock=lambda:f.now,validate_runtime=gate,fetch_daily=daily)
   service=ConfiguredNativeAdmission(**arguments)
   rss=b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 01 Dec 2026 14:00:00 GMT</pubDate><item><title>Unrelated</title><pubDate>Tue, 01 Dec 2026 14:00:00 GMT</pubDate></item></channel></rss>'
   def transport(**kw):return GzipRssTransport(fetch=lambda:dict(url=URL,status=200,headers={'Content-Encoding':'gzip'},body=gzip.compress(rss)),**kw)
   body=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode();real_halt=admission.HaltMarketCaptureV1
   def wrapped(market,**kw):return real_halt(market,fetch=lambda:dict(url=halt.SOURCE_URL,status=200,headers={'Content-Encoding':'gzip'},body=gzip.compress(body)),**kw)
   request=dict(expected_revision=state['revision'],target_id=native['target_id'],expected_proposal_id=proposal['proposal_id'])
   self.enterContext(patch.object(admission,'HaltMarketCaptureV1',wrapped));self.enterContext(patch.object(rss_capture,'GzipRssTransport',transport));self.enterContext(patch('data.strategy_monthly_supplement_gzip_v1.GzipRssTransport',transport))
   return dict(service=service,f=f,router=router,view=view,provider=provider,timing={'split-A':f.timing},request=request,state=state,configraw=configraw,arguments=arguments)

 def test_configured_actual_router_capture_risk_quotes_and_mutation_rejection(self):
  context=self.case();service=context['service'];f=context['f'];request=context['request'];state=context['state'];configraw=context['configraw']
  with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
   result=service.preview(**request)
   self.assertEqual(result['status'],'READY',result);self.assertTrue(result['new_orders']);self.assertEqual(f.store.read(),state)
   previous=service.risk.read(state['account_id'])
   with self.assertRaisesRegex(ValueError,'NATIVE_CONFIG_RISK_ISOLATION'):
    ConfiguredNativeAdmission(**dict(context['arguments'],risk_path=service.risk.path.with_name('missing.sqlite3')))
   self.assertFalse(service.risk.path.with_name('missing.sqlite3').exists())
   with self.assertRaisesRegex(ValueError,'NATIVE_CONFIG_NEW_TARGET_AUTHORIZATION_REQUIRED'):service.preview(**dict(request,target_id='0'*64))
   (f.root/'native-config.json').write_bytes(configraw+b' ')
   with self.assertRaisesRegex(ValueError,'NATIVE_CONFIG_CHANGED'):service.preview(**request)
   (f.root/'native-config.json').write_bytes(configraw)
   name='docs/candidates/split_native_capture_review_20261105.py';raw=(f.root/name).read_bytes();(f.root/name).write_bytes(raw+b'\n')
   with self.assertRaisesRegex(ValueError,'NATIVE_CONFIG_SOURCE_CHANGED'):service.preview(**request)
   (f.root/name).write_bytes(raw)
   self.assertEqual(service.risk.read(state['account_id']),previous);self.assertEqual(f.store.read(),state)
if __name__=='__main__':unittest.main()
