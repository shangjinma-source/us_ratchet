"""Versioned reader integration: real capture/source/boundary/account/risk stores.
Only external HTTP and the established proposal-policy fixture seam are replaced.
No production account, network, fake authority flag or order submission.
"""
from contextlib import ExitStack
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import gzip,json,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from data.monthly_peak_exit_reentry_store_v1 import MonthlyPeakExitReentryStore
from data import saved_frontier_reentry_live_reader_v1 as reader_module
from data import strategy_monthly_supplement_gzip_v1 as supplement
from data.official_rss_gzip_transport_v1 import GzipRssTransport,URL
import test_strategy_daily_first_window_v3 as original_fixture
ROOT=original_fixture.ROOT

class ReentryReaderTests(unittest.TestCase):
 def setup_case(self,folder,stack,advancing_clock=False,earlier_exit=False):
  root=Path(folder);case,config,captured=original_fixture.FirstWindowTests().case(folder)
  captured['official.response.bin']=captured['official.response.bin'].replace(b'<channel>',b'<channel><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate>')
  daily=json.loads(captured['daily.response.bin']);series=daily['chart']['result'][0];series['indicators']['quote'][0]['close'][-1]=79;series['indicators']['adjclose'][0]['adjclose'][-1]=79;captured['daily.response.bin']=canonical(daily)
  if earlier_exit:
   case.clock[0]+=timedelta(days=1)
   captured['official.response.bin']=captured['official.response.bin'].replace(b'Tue, 03 Nov 2026 14:00:00 GMT',b'Wed, 04 Nov 2026 14:00:00 GMT')
   daily=json.loads(captured['daily.response.bin']);series=daily['chart']['result'][0];series['timestamp'].append(int((case.clock[0]-timedelta(days=1,minutes=30)).timestamp()));series['indicators']['quote'][0]['close'].append(70);series['indicators']['adjclose'][0]['adjclose'].append(70);captured['daily.response.bin']=canonical(daily)
   cp=root/config['calendar']['path'];cal=json.loads(cp.read_bytes());cal['sessions'].append(dict(date='2026-11-04',open='2026-11-04T14:30:00+00:00',close='2026-11-04T21:00:00+00:00'));cp.write_bytes(canonical(cal));config['calendar']['sha256']=sha256(cp.read_bytes()).hexdigest()
  clock=[case.clock[0]-timedelta(seconds=30)]
  accounts=StrategyAccountStore(root/'reader-account.sqlite',clock=lambda:clock[0]);state=accounts.initialize(case.state['account_id'],operation_id='reader-init')
  for row in case.state['events']:
   if row['payload'].get('order_id')=='a-pending':continue
   state,_=accounts.append(row['payload'],expected_revision=state['revision'])
  target=deepcopy(case.target);target['payload']['target_quantities']={'B':0};selected=target['payload']['decision']['payload'];selected['target_quantities']={'B':0};target['payload']['decision']['decision_id']=sha256(canonical(selected)).hexdigest();target['target_id']=sha256(canonical(target['payload'])).hexdigest()
  proposal=dict(proposal_id='validated-policy-seam',payload=dict(proposed_target_quantities={'B':7}))
  for name in ['saved_frontier_supplement_request_v1','saved_frontier_first_window_v1','saved_frontier_reentry_exit_packet_v1']:
   stack.enter_context(patch('data.'+name+'.build_frontier_proposal',side_effect=lambda **kw:deepcopy(proposal)))
  pins=[]
  for name in reader_module.SOURCES:
   raw=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);pins.append(dict(path=name,sha256=sha256(raw).hexdigest()))
  risk=MonthlyPeakExitReentryStore(root/'reader-risk.sqlite');risk.activate_reference(account_id=state['account_id'],activation_id='a'*64,activation_at='2026-10-30T21:00:00Z',activation_session='2026-10-30',account_revision=state['revision'],source_configuration_sha256='b'*64)
  clock[0]=case.clock[0]
  def now():
   if advancing_clock:clock[0]+=timedelta(milliseconds=1)
   return clock[0]
  view=SimpleNamespace(monthly=SimpleNamespace(accounts=accounts,current=lambda:deepcopy(target)),require_proposal=lambda **kw:deepcopy(proposal))
  release=canonical(dict(authorized=True,authorized_at=(clock[0]-timedelta(minutes=1)).isoformat(),policy_id=reader_module.POLICY_ID,monthly_cap='1/2',exit_ratio='4/5',sma20_overlay=False))
  wire=gzip.compress(captured['official.response.bin'])
  def factory(**kw):return GzipRssTransport(fetch=lambda:dict(status=200,url=URL,body=wire,headers={'Content-Encoding':'gzip','Content-Length':str(len(wire))}),**kw)
  stack.enter_context(patch.object(supplement,'GzipRssTransport',factory))
  reader=reader_module.SavedFrontierReentryLiveReader(root=root,monthly_view=view,risk_store=risk,source_configuration=dict(identity=config['identity'],calendar=config['calendar'],target_evidence_root='capture'),source_pins=pins,capture_root=root/'live-capture',archive_root=root/'live-archive',boundary_root=root/'boundaries',release_bytes=release,clock=now,validate_sources=lambda:None,fetch_daily=lambda *args:dict(status=200,body=captured['daily.response.bin']))
  return dict(root=root,reader=reader,state=state,target=target,proposal=proposal,risk=risk,accounts=accounts,clock=clock)
 def test_real_precommit_snapshot_atomic_exit_repeat_and_unchanged_account(self):
  with TemporaryDirectory() as folder,ExitStack() as stack:
   c=self.setup_case(folder,stack,True);before=c['accounts'].path.read_bytes()
   def run():return c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal'])
   result=run();self.assertEqual(result['status'],'DAILY_SIGNAL_READY',result);self.assertEqual(result['risk_projection']['state'],c['risk'].read(c['state']['account_id']));self.assertIn('B',result['reference_state']['locks']);self.assertEqual(result['reference_state']['locks']['B']['held_quantity_at_exit'],14);self.assertFalse(result['reentry_execution_applied']);self.assertEqual(c['accounts'].path.read_bytes(),before)
   reference=deepcopy(result['reference_state']);repeat=run();self.assertEqual(repeat['reference_state'],reference);self.assertEqual(c['accounts'].path.read_bytes(),before)
 def test_atomic_failure_retry_keeps_original_boundary_and_account(self):
  with TemporaryDirectory() as folder,ExitStack() as stack:
   c=self.setup_case(folder,stack,True);before=c['accounts'].path.read_bytes();reference=c['risk'].read_reference(c['state']['account_id'])
   def fail(connection):raise RuntimeError('injected atomic fail')
   c['risk'].before_commit=fail
   with self.assertRaisesRegex(RuntimeError,'atomic fail'):c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal'])
   self.assertIsNone(c['risk'].read(c['state']['account_id']));self.assertEqual(c['risk'].read_reference(c['state']['account_id']),reference)
   indexes=list((c['root']/'boundaries/references').glob('*.json'));self.assertEqual(len(indexes),1);saved=indexes[0].read_bytes();c['risk'].before_commit=None
   result=c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal']);self.assertEqual(result['status'],'DAILY_SIGNAL_READY');self.assertEqual(indexes[0].read_bytes(),saved);self.assertEqual(c['accounts'].path.read_bytes(),before)
 def test_late_fill_before_old_boundary_waits_without_risk_write(self):
  with TemporaryDirectory() as folder,ExitStack() as stack:
   c=self.setup_case(folder,stack,True);first=c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal']);risk_before=c['risk'].read(c['state']['account_id']);reference=deepcopy(first['reference_state'])
   c['clock'][0]+=timedelta(seconds=1)
   c['state'],_=c['accounts'].append(dict(event_id='late-real-fill',kind='DIRECT_FILL',security_id='B',side='SELL',quantity=1,price='79',fees='0',executed_at='2026-11-03T14:59:50Z'),expected_revision=c['state']['revision'])
   before=c['accounts'].path.read_bytes();result=c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal']);self.assertEqual(result['reason'],'WAIT_LATE_RECORDED_FILL_RECONCILIATION');self.assertEqual(c['risk'].read(c['state']['account_id']),risk_before);self.assertEqual(c['risk'].read_reference(c['state']['account_id']),reference);self.assertEqual(c['accounts'].path.read_bytes(),before)
 def test_same_epoch_target_change_keeps_original_intent(self):
  with TemporaryDirectory() as folder,ExitStack() as stack:
   c=self.setup_case(folder,stack,True);first=c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal']);saved=[p.read_bytes() for p in (c['root']/'boundaries/references').glob('*.json')]
   c['clock'][0]+=timedelta(seconds=1)
   c['state'],_=c['accounts'].append(dict(event_id='new-cash',kind='CASH_CONFIRM',amount='500',cash_basis='TOTAL_UNINVESTED'),expected_revision=c['state']['revision'])
   c['target']['payload']['cash_update_fixture']='new';c['target']['target_id']=sha256(canonical(c['target']['payload'])).hexdigest();c['proposal']['proposal_id']='new-current-proposal'
   result=c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal']);self.assertEqual(result['status'],'DAILY_SIGNAL_READY');self.assertEqual(result['reference_state'],first['reference_state']);self.assertEqual([p.read_bytes() for p in (c['root']/'boundaries/references').glob('*.json')],saved)
 def test_missing_historical_intent_does_not_backfill_exit_holdings(self):
  with TemporaryDirectory() as folder,ExitStack() as stack:
   c=self.setup_case(folder,stack,True,True);before=c['risk'].read_reference(c['state']['account_id']);account_before=c['accounts'].path.read_bytes()
   result=c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal']);self.assertEqual(result['reason'],'WAIT_ORIGINAL_DECISION_BOUNDARY_MISSING');self.assertIsNone(c['risk'].read(c['state']['account_id']));self.assertEqual(c['risk'].read_reference(c['state']['account_id']),before);self.assertEqual(c['accounts'].path.read_bytes(),account_before)
   refs=[json.loads(p.read_bytes()) for p in (c['root']/'boundaries/references').glob('*.json')];self.assertEqual([r['session_date'] for r in refs],['2026-11-03'])
 def test_postcommit_archive_failure_retries_without_duplicate_reference(self):
  with TemporaryDirectory() as folder,ExitStack() as stack:
   c=self.setup_case(folder,stack,True);account_before=c['accounts'].path.read_bytes()
   with patch.object(reader_module,'archive_rebound_evidence',side_effect=RuntimeError('final archive failure')):
    with self.assertRaisesRegex(RuntimeError,'final archive failure'):
     c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal'])
   risk=c['risk'].read(c['state']['account_id']);reference=c['risk'].read_reference(c['state']['account_id'])
   self.assertIsNotNone(risk);self.assertIn('B',reference['locks'])
   saved={p.name:p.read_bytes() for p in (c['root']/'boundaries/references').glob('*.json')}
   self.assertTrue(saved)
   result=c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal'])
   self.assertEqual(result['status'],'DAILY_SIGNAL_READY');self.assertEqual(c['risk'].read(c['state']['account_id']),risk)
   self.assertEqual(result['reference_state'],reference);self.assertEqual(c['risk'].read_reference(c['state']['account_id']),reference)
   self.assertEqual({p.name:p.read_bytes() for p in (c['root']/'boundaries/references').glob('*.json')},saved)
   self.assertEqual(c['accounts'].path.read_bytes(),account_before)
 def test_missing_activation_waits_before_capture(self):
  with TemporaryDirectory() as folder,ExitStack() as stack:
   c=self.setup_case(folder,stack);c['reader'].risk=MonthlyPeakExitReentryStore(c['root']/'unactivated.sqlite')
   result=c['reader'](c['state'],c['target'],c['clock'][0],proposal=c['proposal']);self.assertEqual(result['reason'],'WAIT_EXPLICIT_REFERENCE_ACTIVATION');self.assertFalse((c['root']/'live-capture').exists())
if __name__=='__main__':unittest.main()
