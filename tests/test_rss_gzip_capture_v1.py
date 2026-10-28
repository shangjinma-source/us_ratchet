"""Gzip transport proof and isolated production-wiring regression tests.
Default loads installed modules; NEWS_RSS_GZIP_CANDIDATE_ROOT may select a stage root.
No network, financial account writes, or live previews.
"""
import os, importlib, importlib.util, sys, gzip, json, unittest
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace as NS
from contextlib import nullcontext, ExitStack
from functools import partial

def load(name):
    candidate = os.environ.get('NEWS_RSS_GZIP_CANDIDATE_ROOT')
    if not candidate:
        return importlib.import_module('data.' + name)
    path = Path(candidate) / 'data' / (name + '.py')
    spec = importlib.util.spec_from_file_location('data.' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

transport=load('official_rss_gzip_transport_v1')
capture=load('strategy_rss_gzip_capture_v1')
supplement=load('strategy_monthly_supplement_gzip_v1')
reader_module=load('saved_frontier_live_reader_v1')
rolling=load('saved_frontier_rolling_admission_v1')
prep=load('strategy_unified_server_preparation_v27')
m=transport
class StopAfterCapture(Exception): pass

class CaptureFixture:
 def setUp(self):
  self.now=datetime(2026,10,28,18,tzinfo=timezone.utc);self.binding=dict(account_id='test',account_revision='r',target_id='t',session='2026-10-28')
  self.request=dict(account_id='test',state_revision='r',window_start='2026-10-01T13:30:00+00:00',observed_floor=self.now.isoformat(),securities={'A':{'ticker':'TEST'}},current_target_quantities={'A':1})
  self.body=b'<rss><channel><pubDate>Wed, 28 Oct 2026 17:59:00 GMT</pubDate><item><title>TEST</title><pubDate>Wed, 28 Oct 2026 17:59:00 GMT</pubDate></item></channel></rss>';self.wire=gzip.compress(self.body);self.calls=0
 def fetch(self):
  self.calls+=1;return dict(status=200,url=transport.URL,body=self.wire,headers={'Content-Encoding':'gzip','Content-Length':str(len(self.wire))})
 def factory(self,**kwargs):return transport.GzipRssTransport(fetch=self.fetch,**kwargs)
 def daily(self,*args):return dict(status=200,body=b'{"events":{}}')

class GzipProofTests(unittest.TestCase):
 def test_identity_and_gzip(self):
  body=b'<rss>fixture</rss>'
  self.assertEqual(m.decode_wire(body,{}),body)
  wire=gzip.compress(body);self.assertEqual(m.decode_wire(wire,{'Content-Encoding':'gzip','Content-Length':str(len(wire))}),body)
 def test_corrupt_truncated_trailing_multiple_and_bomb_rejected(self):
  wire=gzip.compress(b'xml');bad=bytearray(wire);bad[-8]^=1
  for raw in [bytes(bad),wire[:-1],wire+b'tail',wire+wire,gzip.compress(b'x'*(m.MAX_BYTES+1))]:
   with self.subTest(length=len(raw)),self.assertRaises(ValueError):m.decode_wire(raw,{'Content-Encoding':'gzip'})
  for headers in [{'Content-Encoding':'br'},{'Content-Encoding':'gzip, identity'},{'Content-Encoding':'gzip','Content-Length':'1'}]:
   with self.assertRaises(ValueError):m.decode_wire(wire,headers)
 def test_proof_independent_binding_and_real200_required(self):
  wire=gzip.compress(b'<rss/>');records=[]
  def fetch():return dict(status=200,url=m.URL,body=wire,headers={'Content-Encoding':'gzip','Content-Length':str(len(wire))})
  now=datetime(2026,10,28,18,30,tzinfo=timezone.utc)
  response=m.GzipRssTransport(fetch=fetch,clock=lambda:now,sink=lambda *args:records.append(args))()
  proof,actual,entity=records[0];self.assertEqual(response['status'],200);self.assertEqual(actual,wire);self.assertEqual(response['body'],b'<rss/>');self.assertTrue(m.validate_proof(proof,actual,entity))
  for key,value in [('http_status',304),('url',m.URL+'x'),('decoded_sha256','bad'),('request_headers',{})]:
   bad=deepcopy(proof);bad[key]=value
   with self.assertRaises(ValueError):m.validate_proof(bad,actual,entity)
  with self.assertRaises(ValueError):m.GzipRssTransport(fetch=lambda:dict(fetch(),status=304),clock=lambda:now,sink=lambda *args:None)()
class CaptureProofTests(CaptureFixture, unittest.TestCase):
 def test_real_supplement_persists_reuses_and_tamper_rejects(self):
  with TemporaryDirectory() as directory,patch.object(supplement,'GzipRssTransport',self.factory):
   def run():return supplement.capture_supplement(directory=directory,request=self.request,binding=self.binding,read_binding=lambda:self.binding.copy(),execute=True,fetch_daily=self.daily,clock=lambda:self.now)
   result=run();capture.validate_capture(result);again=run();self.assertTrue(again['reused']);self.assertEqual(self.calls,1);self.assertEqual(result['files'],again['files'])
   proof=json.loads(result['files'][result['rss_encoding_proof_path']]);folder=Path(directory)/result['capture_id'];wirepath=folder/(result['source_hashes'][proof['wire_path']]+'.bin');self.assertEqual(wirepath.read_bytes(),self.wire)
   self.assertEqual((folder/'transport-002.bin').read_bytes(),self.wire)
   wirepath.write_bytes(b'bad')
   with self.assertRaises(ValueError):run()
 def test_real_v6_action_chain_retains_wire_and_current_xml(self):
  with TemporaryDirectory() as directory,patch.object(capture,'GzipRssTransport',self.factory):
   result=capture.GzipActionCapture(fetch=self.daily,clock=lambda:self.now).capture(self.request,Path(directory)/'capture')
   self.assertTrue(capture.validate_capture(result));self.assertEqual(result['files'][result['documents']['rss_raw']],self.body)
   self.assertTrue((Path(directory)/'capture/complete-gzip.json').exists());self.assertEqual(self.calls,1)

class WiringTests(CaptureFixture, unittest.TestCase):
 def test_reader_reaches_real_gzip_supplement(self):
  with TemporaryDirectory() as directory, ExitStack() as stack:
   root=Path(directory);state={'account_id':'test','revision':'r'}
   target={'target_id':'t','payload':{'target_month':'2026-10','decision':{'payload':{'input_binding':{}}}}}
   proposal={'proposal_id':'p'};risk={'target_month':'2026-10','decision_date':'2026-10-27'}
   monthly=NS(accounts=NS(read=lambda:state),current=lambda:target)
   view=NS(monthly=monthly,require_proposal=lambda **kw:proposal)
   release=dict(authorized=True,policy_id=reader_module.POLICY_ID,monthly_cap='1/2',exit_ratio='4/5',sma20_overlay=False,authorized_at='2026-10-01T00:00:00Z')
   calendar={'schema':'FIXED_EXCHANGE_SESSIONS_V1','exchange':'NASDAQ','sessions':[{'date':day,'open':day+'T13:30:00Z','close':day+'T20:00:00Z'} for day in ['2026-10-27','2026-10-28']]}
   stack.enter_context(patch.object(reader_module,'pinned',return_value=json.dumps(calendar).encode()))
   stack.enter_context(patch.object(reader_module,'locate_unit_baseline_sources',return_value=[]))
   stack.enter_context(patch.object(reader_module,'prepare_frontier_supplement_request',return_value={'request':self.request,'binding':self.binding}))
   stack.enter_context(patch.object(supplement,'GzipRssTransport',self.factory))
   captured=[]
   def review(**kwargs):
    captured.append(kwargs['capture']);capture.validate_capture(kwargs['capture']);raise StopAfterCapture()
   stack.enter_context(patch.object(reader_module,'read_frontier_capture',side_effect=review))
   reader=reader_module.SavedFrontierLiveReader(root=root,monthly_view=view,risk_store=NS(read=lambda _:risk),source_configuration={'calendar':{},'identity':{},'target_evidence_root':'x'},source_pins={p:'0'*64 for p in reader_module.SOURCES},capture_root=root/'captures',archive_root=root/'archive',release_bytes=json.dumps(release).encode(),clock=lambda:self.now,validate_sources=lambda:None,fetch_daily=self.daily,fetch_official=None)
   with self.assertRaises(StopAfterCapture):reader(state,target,self.now,proposal=proposal)
   self.assertEqual(self.calls,1);self.assertEqual(len(captured),1)
   self.assertEqual(len(list((root/'captures').rglob('complete.json'))),1)

 def test_rolling_replaces_actions_and_executes_gzip_capture(self):
  with TemporaryDirectory() as directory, ExitStack() as stack:
   root=Path(directory);legacy=root/'legacy.db';legacy.write_bytes(b'fixture')
   provider=object.__new__(rolling.StrategyAccountEvidenceProvider)
   provider.market=NS(identity=None,fetch=None,clock=lambda:self.now,workers=1,max_mark_age=60)
   provider.actions=NS(fetch=self.daily,rss_fetch=lambda: (_ for _ in ()).throw(AssertionError('legacy RSS used')),clock=lambda:self.now,workers=4)
   provider.limits=partial(lambda:None,cap_store=NS(path=legacy,clock=lambda:self.now,max_history_rows=100,max_history_bytes=1000))
   runtime=NS(execution_provider=provider.execution,selection=NS(fees=0))
   monthly=NS(snapshot_operation=nullcontext,current=lambda:{'target_id':'t'},accounts=NS(read=lambda:{'revision':'r'}),_for_target=lambda target:(runtime,{}),root=root)
   stack.enter_context(patch.object(rolling,'validate_account_identity_coverage'))
   stack.enter_context(patch.object(rolling,'PullbackCapStore',return_value=NS()))
   stack.enter_context(patch.object(capture,'GzipRssTransport',self.factory))
   captured=[]
   def composition(**kwargs):
    actual=kwargs['execution_provider'].__self__
    self.assertIsInstance(actual.actions,capture.GzipActionCapture)
    def preview(**kw):
     result=actual.actions.capture(self.request,root/'capture');capture.validate_capture(result);captured.append(result);return {'status':'SMOKE_ONLY'}
    return NS(preview=preview)
   stack.enter_context(patch.object(rolling,'SavedFrontierDailyComposition',side_effect=composition))
   service=rolling.SavedFrontierRollingAdmissionV1(monthly=monthly,monthly_view=NS(require_proposal=lambda **kw:{'id':'p'}),reader=None,clock=lambda:self.now,validate_code=lambda:None)
   self.assertEqual(service.preview(expected_revision='r',target_id='t',expected_proposal_id='p')['status'],'SMOKE_ONLY')
   self.assertEqual(self.calls,1);self.assertEqual(len(captured),1)

 def test_preparation_enforces_new_pins_and_owns_official_transport(self):
  with TemporaryDirectory() as directory, ExitStack() as stack:
   root=Path(directory);release=dict(authorized=True,policy_id=prep.POLICY_ID,monthly_cap='1/2',exit_ratio='4/5',sma20_overlay=False,authorized_at='2026-10-01T00:00:00Z')
   config={'schema':'SAVED_FRONTIER_UNIFIED_PREPARATION_V27','base_v26':{'path':'base','sha256':'x'},'release':{'path':'release','sha256':'x'},'source_pins':{p:'0'*64 for p in prep.SOURCES},**{name:'data/strategy_account/'+name for name in ['proposal_database','capture_root','archive_root','display_root']}}
   def read(root,ref):return (b'config',config) if ref['path']=='config' else ((b'release',release) if ref['path']=='release' else (b'source',{}))
   stack.enter_context(patch.object(prep,'_read',side_effect=read));stack.enter_context(patch.object(prep,'_read_digest',return_value='0'*64))
   packet=NS(reference={'path':'source'},fetch_daily=self.daily,fetch_official=lambda:None)
   oldreader=NS(source_reader=NS(packet_reader=packet),risk_store=NS(path=root/'risk.db'))
   monthly=NS(accounts=NS(path=root/'account.db'),targets=NS(path=root/'target.db'))
   old=NS(service=NS(service=NS(reader=oldreader)),clock=lambda:self.now)
   stack.enter_context(patch.object(prep,'build_unified_server_preparation_v26',return_value={'monthly':monthly,'observed_daily':old,'validate_code':lambda:None}))
   stack.enter_context(patch.object(prep,'SavedFrontierProposalStore',side_effect=lambda p:NS(path=p)))
   stack.enter_context(patch.object(prep,'SavedFrontierMonthlyView',return_value=NS()))
   reached=[]
   def construct(**kwargs):
    reached.append(kwargs);self.assertIsNone(kwargs['fetch_official']);raise StopAfterCapture()
   stack.enter_context(patch.object(reader_module,'SavedFrontierLiveReader',side_effect=construct))
   with self.assertRaises(StopAfterCapture):prep.build_unified_server_preparation_v27(root=root,configuration_path='config',configuration_sha256='x',clock=lambda:self.now)
   self.assertEqual(len(reached),1)
   for name in ['official_rss_gzip_transport_v1','strategy_rss_gzip_capture_v1','strategy_monthly_supplement_gzip_v1']:
    self.assertIn('data/'+name+'.py',reached[0]['source_pins'])
   del config['source_pins']['data/official_rss_gzip_transport_v1.py']
   with self.assertRaisesRegex(ValueError,'V27_SOURCE_SCOPE'):prep.build_unified_server_preparation_v27(root=root,configuration_path='config',configuration_sha256='x',clock=lambda:self.now)


class ClockTests(CaptureFixture, unittest.TestCase):
 def test_rebound_old_proof_and_legacy_timing_fail_closed(self):
  with TemporaryDirectory() as directory,patch.object(capture,'GzipRssTransport',self.factory):
   result=capture.GzipActionCapture(fetch=self.daily,clock=lambda:self.now).capture(self.request,Path(directory)/'capture')
  path=result['rss_encoding_proof_path'];proof=json.loads(result['files'][path])
  self.assertIsNotNone(proof['legacy_timing_path'])
  def update(data,name,value):
   data['files'][name]=json.dumps(value).encode();data['source_hashes'][name]=sha256(data['files'][name]).hexdigest()
  old=deepcopy(result);changed=deepcopy(proof)
  for key in ['started_at','network_received_at','decoded_at']:changed[key]='2026-10-27T18:00:00+00:00'
  update(old,path,changed)
  with self.assertRaisesRegex(ValueError,'RECEIPT_CLOCK'):capture.validate_capture(old)
  reversed_time=deepcopy(result);changed=deepcopy(proof);changed['network_received_at']='2026-10-28T18:00:01+00:00';update(reversed_time,path,changed)
  with self.assertRaisesRegex(ValueError,'CLOCK'):capture.validate_capture(reversed_time)
  tampered=deepcopy(result);timing_path=proof['legacy_timing_path'];tampered['files'][timing_path]+=b' '
  with self.assertRaisesRegex(ValueError,'TIMING_HASH'):capture.validate_capture(tampered)
  reordered=deepcopy(result);timing=json.loads(reordered['files'][timing_path]);timing['transport_received_at']='2026-10-28T17:59:59+00:00';update(reordered,timing_path,timing)
  changed=deepcopy(proof);changed['legacy_timing_sha256']=reordered['source_hashes'][timing_path];update(reordered,path,changed)
  with self.assertRaisesRegex(ValueError,'TIMING_CLOCK'):capture.validate_capture(reordered)
  naive=deepcopy(result);changed=deepcopy(proof);changed['started_at']='2026-10-28T18:00:00';update(naive,path,changed)
  with self.assertRaisesRegex(ValueError,'AWARE_CLOCK'):capture.validate_capture(naive)


if __name__ == '__main__': unittest.main()
