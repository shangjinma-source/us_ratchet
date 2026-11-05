"""Real split profiled adoption/router to protected native daily admission.

Only the signal reader and external HTTP bytes are controlled test inputs.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import gzip,json,unittest
import test_split_profiled_monthly_20261105 as fixture
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView,SavedFrontierProposalStore
from data.current_quantity_v2_pullback_runtime import PullbackCapStore
from data.strategy_execution_halt_evidence_v1 import HEADER
from data import strategy_halt_gzip_capture_v1 as halt
from data import strategy_rss_gzip_capture_v1 as rss_capture,official_rss_gzip_transport_v1 as rss_wire
from docs.candidates import split_native_rolling_admission_20261105 as admission

class Tests(unittest.TestCase):
 def test_actual_profiled_activation_router_to_protected_native_daily(self):
  f=fixture.Tests();f.setUp();self.addCleanup(f.doCleanups)
  def gate():
   for name,expected in f.pins.items():
    self.assertEqual(fixture.digest((f.root/name).read_bytes()),expected)
    self.assertEqual(fixture.digest((fixture.ROOT/name).read_bytes()),expected)
  with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
   ready=f.prepare(f.f.entry,'real-profiled-daily')
   adopted=f.activation.adopt(receipt_path=ready['path'],receipt_sha256=ready['sha256'],expected_release_revision=0)
   router=fixture.module.SplitProfiledRouter(root=f.root,snapshot_provider=f.activation.snapshot,initial_snapshot=f.activation.snapshot(),approvals=f.approvals,clock=lambda:f.now,market_factory=f.market,action_factory=f.actions)
   view=SavedFrontierMonthlyView(monthly=router,proposals=SavedFrontierProposalStore(f.root/'data/strategy_account/proposal.sqlite3'),validate_sources=gate)
   target=view.generate(event_id='actual-profiled-native',reason='INITIAL',expected_revision=f.store.read()['revision'],previous_target_id=None)
   native=router.current();runtime,configuration=router._for_target(native)
   provider=runtime.execution_provider.__self__
   legacy=provider.limits.keywords['cap_store']
   PullbackCapStore(legacy.path,clock=legacy.clock,max_history_rows=legacy.max_history_rows,max_history_bytes=legacy.max_history_bytes)
   def reader(state,target,at,*,proposal):
    quantities=deepcopy(proposal['payload']['proposed_target_quantities'])
    for sid in state['shares']:quantities.setdefault(sid,0)
    signal=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target['target_id'],proposal_id=proposal['proposal_id'],policy_id='CONTROLLED_PROFILED_NATIVE_TEST',evidence_id='controlled',evidence_archive={'controlled':True},effective_target_quantities=quantities,observed_at=at.isoformat(),available_at=at.isoformat(),valid_from=at.isoformat(),valid_until=(at+timedelta(seconds=60)).isoformat())
    return dict(status='DAILY_SIGNAL_READY',signal=signal,evidence_archive=signal['evidence_archive'])
   service=admission.NativeSplitRollingAdmission(monthly=router,monthly_view=view,reader=reader,clock=lambda:f.now,validate_code=gate,timing_bundles={'split-A':f.timing},policy_execution_enabled=True,policy_id='CONTROLLED_PROFILED_NATIVE_TEST')
   body=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode();wire=gzip.compress(body)
   real_halt=admission.HaltMarketCaptureV1
   def wrapped(market,**kw):return real_halt(market,fetch=lambda:dict(url=halt.SOURCE_URL,status=200,headers={'Content-Encoding':'gzip'},body=wire),**kw)
   rss=provider.actions.rss_fetch()['body'].replace(b'<channel>',b'<channel><pubDate>'+f.now.strftime('%a, %d %b %Y %H:%M:%S GMT').encode()+b'</pubDate>')
   def transport(**kw):return rss_wire.GzipRssTransport(fetch=lambda:dict(url=rss_wire.URL,status=200,headers={'Content-Encoding':'gzip'},body=gzip.compress(rss)),**kw)
   before=f.store.read();snapshot=f.activation.snapshot()
   request=dict(expected_revision=before['revision'],target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
   with patch.object(admission,'HaltMarketCaptureV1',wrapped),patch.object(rss_capture,'GzipRssTransport',transport):
    result=service.preview(**request)
   self.assertEqual(result['status'],'READY',result);self.assertTrue(result['new_orders'])
   self.assertTrue(result['execution_binding'])
   self.assertEqual(result['account_revision'],before['revision'])
   self.assertEqual(f.store.read(),before);self.assertEqual(view.current(),target)
   self.assertEqual(f.activation.snapshot(),snapshot);self.assertEqual(snapshot['revision'],adopted['revision'])
   self.assertTrue(list(f.root.rglob('*.transport.json')))
   self.assertTrue(list(f.root.rglob('halt_pullback_caps_v2_*.sqlite3')))
   # Resolve once more through the real router, not a test _for_target replacement.
   again,again_config=router._for_target(native)
   self.assertEqual(again_config,configuration)
   self.assertIs(type(again.execution_provider.__self__),type(provider))
   with patch.object(type(provider),'_assemble',side_effect=AssertionError('PROFILED_FACTORY_REVIEW_REQUIRED')) as checked:
    with self.assertRaisesRegex(AssertionError,'PROFILED_FACTORY_REVIEW_REQUIRED'):service.preview(**request)
    self.assertEqual(checked.call_count,1)
   self.assertEqual(f.store.read(),before)

if __name__=='__main__':unittest.main()
