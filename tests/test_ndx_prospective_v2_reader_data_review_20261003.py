"""Independent V2 observation reader attacks; synthetic envelopes only."""
import copy,importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_prospective_observation_independent_readback_v2_20261003 as m
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reader_fixture',ROOT/'tests/test_ndx_prospective_observation_independent_readback_v2_20261003.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class Review(unittest.TestCase):
 def test_complete_second_prefix_failed_first_and_source_associations(self):
  a=f.fixture(True,True);h=a['docs']['parent']['document'];h['known_typed_rows'][65]['seal_status']='FAILED'
  a['docs']['capture']['document']['plan']['known_typed_rows_preserved']=copy.deepcopy(h['known_typed_rows']);a['payload']['known_typed_rows_preserved']=copy.deepcopy(h['known_typed_rows'])
  self.assertFalse(m.inspect(**a)['month_first_actual_observation']);self.assertEqual(a['payload']['first_actual_observed_session_of_month'],'2026-10-02')
  for mode in ('parentreader','capturecore','snapshot','extra_live','count','attempt','prefix'):
   b=copy.deepcopy(a);p=b['docs']['parent'];c=b['docs']['capture']
   if mode=='parentreader':p['readback']['reader_sha256']='f'*64
   elif mode=='capturecore':
    key=m.CAPTURE_CORE[0]
    for o in (c['document'],c['publication'],c['readback']):o['source_hashes'].pop(key,None)
   elif mode=='snapshot':c['readback']['source_hashes'].pop(c['document']['captured_artifacts']['QQQ']['path'])
   elif mode=='extra_live':
    for o in (p['document'],p['publication'],p['readback']):o['source_hashes'][str(ROOT/'data/cache/SPY.csv')]='a'*64
   elif mode=='count':c['readback']['counts']['parent_typed_row_count']=67.0
   elif mode=='attempt':p['document']['parent_attempt_inventory'].pop()
   else:p['document']['known_typed_rows'].pop(65)
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect(**b)
 def test_outside_rows_never_dropped_capture_interval_and_receipt_role(self):
  a=f.fixture();self.assertEqual(len(a['payload']['full_original_sources_preserved']['QQQ']['sources']['outside_required_scope_diagnostics']),1)
  for mode in ('oldrow','base64','partial','beforeclose','completion','receiptrole','bool'):
   b=copy.deepcopy(a);p=b['payload'];c=b['docs']['capture']['document']
   if mode=='oldrow':p['full_original_sources_preserved']['QQQ']['sources']['rows'].pop(0)
   elif mode=='base64':p['full_original_sources_preserved']['QQQ']['baseline_sources']['original_csv_bytes_base64']=''
   elif mode=='partial':b['blobs'][c['captured_artifacts']['SPY']['path']]=b'partial'
   elif mode=='beforeclose':
    c['capture_started_at']=c['plan']['capture_started_at']=p['capture_started_at_utc']='2026-10-05T19:59:00+00:00'
   elif mode=='completion':p['writer_completed_at_utc']='2026-10-05T22:00:00+00:00'
   elif mode=='receiptrole':b['receipt']['publication_time_role']='DURABLE_RECEIPT_COMPLETED_AT'
   else:b['receipt']['month_first_actual_observation']=0
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect(**b)
 def test_independently_built_closure_and_failed_namespace(self):
  a=f.fixture();sources=copy.deepcopy(a['payload']['source_hashes'])
  with tempfile.TemporaryDirectory()as td,patch.object(m,'BASE',Path(td)),patch.object(m,'load_inputs',return_value=(a['docs'],a['refs'],a['blobs'],sources)):
   p=copy.deepcopy(a['payload']);r=copy.deepcopy(a['receipt']);started=copy.deepcopy(a['started'])
   for o in (p,r,started):o['source_hashes']={}
   pr=m.save(m.BASE/'observation_payload.json',p);r['payload_reference']=pr;rr=m.save(m.BASE/'receipt.json',r);m.save(m.BASE/'started.json',started)
   with patch.object(m,'PAYLOAD_SHA',pr['sha256']),patch.object(m,'RECEIPT_SHA',rr['sha256']),patch.object(m,'inspect',side_effect=AssertionError('must reject first')):
    with self.assertRaisesRegex(ValueError,'producer source closure'):m.readback(execute=True)
   self.assertTrue((m.BASE/'failure.json').exists());self.assertFalse((m.BASE/'independent_readback.json').exists())
   with self.assertRaises(ValueError):m.readback(execute=True)
  with tempfile.TemporaryDirectory()as td:
   p=Path(td)/'oldsource';p.write_bytes(b'old');r=dict(path=str(p),sha256=m.sha(b'old'));m.consume(r,{})
   (Path(td)/'failure.json').write_text('{}')
   with self.assertRaisesRegex(ValueError,'Failed'):m.consume(r,{})
if __name__=='__main__':unittest.main()
