"""Offline CBOE gzip closure and rolling wiring; no network or real accounts."""
import os,sys,importlib,importlib.util,json,gzip,unittest
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import patch
from contextlib import ExitStack,nullcontext
from functools import partial

def load(name):
 root=os.environ.get('HALT_GZIP_CANDIDATE_ROOT')
 if not root:return importlib.import_module('data.'+name)
 spec=importlib.util.spec_from_file_location('data.'+name,Path(root)/'data'/(name+'.py'))
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module
m=load('strategy_halt_gzip_capture_v1');rolling=load('saved_frontier_rolling_admission_v1');prep=load('strategy_unified_server_preparation_v27')
class HaltGzipTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,29,2,tzinfo=timezone.utc);self.body=b'<html><table>current halt evidence</table></html>';self.wire=gzip.compress(self.body)
 def response(self,wire=None,encoding='gzip'):
  return dict(status=200,url=m.SOURCE_URL,headers={'Content-Encoding':encoding},body=self.wire if wire is None else wire)
 def run_capture(self,root,response,clock=None):
  calls=[]
  def market(**kwargs):calls.append(kwargs);return {'files':{},'source_hashes':{},'existing_sell_quote':'preserved'}
  result=m.HaltGzipMarketCaptureV1(NS(capture=market),fetch=lambda:response,clock=clock or (lambda:self.now)).capture(output_directory=Path(root)/'market')
  self.assertEqual(len(calls),1);self.assertEqual(result['existing_sell_quote'],'preserved');return result
 def test_identity_gzip_and_decoded_receipt(self):
  for response in (self.response(),self.response(self.body,'identity')):
   with self.subTest(encoding=response['headers']),TemporaryDirectory() as root:
    result=self.run_capture(root,response);self.assertTrue(m.validate_halt_encoding(result));self.assertEqual(result['files'][result['halt_evidence']['raw_path']],self.body)
    self.assertEqual((Path(root)/'market-halts/wire.bin').read_bytes(),response['body'])
 def test_corruption_size_and_failure_keep_market_without_halt_authority(self):
  bad=bytearray(self.wire);bad[-8]^=1
  for wire in [bytes(bad),self.wire[:-1],self.wire+self.wire,self.wire+b'tail',b'x'*(m.MAX_BYTES+1),gzip.compress(b'x'*(m.MAX_BYTES+1))]:
   with self.subTest(length=len(wire)),TemporaryDirectory() as root:
    result=self.run_capture(root,self.response(wire));self.assertIn('halt_capture_failure',result);self.assertNotIn('halt_evidence',result);self.assertNotIn('halt_encoding_proof_path',result)
 def test_http_and_clock_failure_are_not_no_halt(self):
  for response in [dict(self.response(),status=304),dict(self.response(),url=m.SOURCE_URL+'x')]:
   with TemporaryDirectory() as root:self.assertIn('halt_capture_failure',self.run_capture(root,response))
  times=iter([self.now,self.now.replace(hour=1),self.now,self.now])
  with TemporaryDirectory() as root:self.assertIn('halt_capture_failure',self.run_capture(root,self.response(),lambda:next(times)))
 def test_all_closure_parts_and_rehashed_clock_tamper_rejected(self):
  with TemporaryDirectory() as root:result=self.run_capture(root,self.response())
  proof=json.loads(result['files'][result['halt_encoding_proof_path']])
  for key in ['wire_path','decoded_path','receipt_path']:
   bad=deepcopy(result);bad['files'][proof[key]]+=b'x'
   with self.assertRaises(ValueError):m.validate_halt_encoding(bad)
  bad=deepcopy(result);proof['network_received_at']='2026-10-29T01:00:00+00:00';path=bad['halt_encoding_proof_path'];bad['files'][path]=json.dumps(proof).encode();bad['source_hashes'][path]=sha256(bad['files'][path]).hexdigest()
  with self.assertRaisesRegex(ValueError,'CLOCK_ORDER'):m.validate_halt_encoding(bad)
 def test_slow_decode_and_persistence_never_refresh_network_receipt(self):
  times=iter([self.now,self.now+timedelta(seconds=1),self.now+timedelta(seconds=40)])
  original_decode=m.decode_wire
  with TemporaryDirectory() as root,patch.object(m,'decode_wire',side_effect=original_decode):
   result=self.run_capture(root,self.response(),lambda:next(times))
  proof=json.loads(result['files'][result['halt_encoding_proof_path']])
  receipt=json.loads(result['files'][result['halt_evidence']['receipt_path']])
  self.assertEqual(receipt['received_at'],(self.now+timedelta(seconds=1)).isoformat())
  self.assertEqual(proof['decoded_at'],(self.now+timedelta(seconds=40)).isoformat())
  self.assertEqual(proof['network_received_at'],receipt['received_at'])
  # A fresh-looking replacement receipt is rejected even if its hashes are recomputed.
  bad=deepcopy(result);receipt['received_at']=proof['decoded_at'];path=bad['halt_evidence']['receipt_path']
  bad['files'][path]=json.dumps(receipt).encode();bad['source_hashes'][path]=sha256(bad['files'][path]).hexdigest()
  proof['receipt_sha256']=bad['source_hashes'][path];proof_path=bad['halt_encoding_proof_path']
  bad['files'][proof_path]=json.dumps(proof).encode();bad['source_hashes'][proof_path]=sha256(bad['files'][proof_path]).hexdigest()
  with self.assertRaisesRegex(ValueError,'CLOCK_ORDER'):m.validate_halt_encoding(bad)
 def test_actual_rolling_replacement_and_source_pin(self):
  self.assertIn('data/strategy_halt_gzip_capture_v1.py',prep.SOURCES)
  with TemporaryDirectory() as root,ExitStack() as stack:
   root=Path(root);legacy=root/'legacy.db';legacy.write_bytes(b'fixture')
   provider=object.__new__(rolling.StrategyAccountEvidenceProvider)
   provider.market=NS(identity=None,fetch=None,clock=lambda:self.now,workers=4,max_mark_age=60)
   provider.actions=NS(fetch=None,rss_fetch=None,clock=lambda:self.now,workers=4)
   provider.limits=partial(lambda:None,cap_store=NS(path=legacy,clock=lambda:self.now,max_history_rows=100,max_history_bytes=1000))
   runtime=NS(execution_provider=provider.execution,selection=NS(fees=0))
   monthly=NS(snapshot_operation=nullcontext,current=lambda:{'target_id':'t'},accounts=NS(read=lambda:{'revision':'r'}),_for_target=lambda target:(runtime,{}),root=root)
   stack.enter_context(patch.object(rolling,'validate_account_identity_coverage'))
   stack.enter_context(patch.object(rolling,'PullbackCapStore',return_value=NS()))
   stack.enter_context(patch.object(rolling,'DailyMarketCaptureV3',return_value=NS(capture=lambda **kw:{'files':{},'source_hashes':{}})))
   captured=[]
   def composition(**kwargs):
    actual=kwargs['execution_provider'].__self__;self.assertIsInstance(actual.market,m.HaltGzipMarketCaptureV1)
    actual.market.fetch=lambda:self.response()
    def preview(**kw):
     result=actual.market.capture(output_directory=root/'market');m.validate_halt_encoding(result);captured.append(result);return {'status':'SMOKE_ONLY'}
    return NS(preview=preview)
   stack.enter_context(patch.object(rolling,'SavedFrontierDailyComposition',side_effect=composition))
   service=rolling.SavedFrontierRollingAdmissionV1(monthly=monthly,monthly_view=NS(require_proposal=lambda **kw:{'id':'p'}),reader=None,clock=lambda:self.now,validate_code=lambda:None)
   self.assertEqual(service.preview(expected_revision='r',target_id='t',expected_proposal_id='p')['status'],'SMOKE_ONLY');self.assertEqual(len(captured),1)
if __name__=='__main__':unittest.main()
