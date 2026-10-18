"""Variable-prefix writer author tests; synthetic history/CSV and temporary output only."""
import copy,importlib.util,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_prospective_observation_writer_v2_20261003 as m
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v2writer_fixture',ROOT/'tests/test_ndx_variable_prefix_capture_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def ref(path):return dict(path=path,sha256='a'*64)
def fixture(second=False):
 a=f.fixture(second);parent=a['parent'];plan=f.m.plan_history_capture(**a);pr={k:parent[k]for k in m.PARENT_BOUND};cr={k:ref('capture_'+k)for k in m.PARENT_BOUND}
 sources={m.CAPTURE_PRODUCER[0]:m.CAPTURE_PRODUCER[1]}
 for o in (parent['document'],parent['publication'],parent['readback']):sources.update(o['source_hashes'])
 for r in pr.values():sources[r['path']]=r['sha256']
 sources.update(plan['source_reference_claims']);sources[m.CAPTURE_CORE[0]]=m.CAPTURE_CORE[1]
 cap=dict(schema='SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1',plan=plan,parent_references=pr,input_references={'core':dict(path=m.CAPTURE_CORE[0],sha256=m.CAPTURE_CORE[1])},captured_artifacts={**a['source_references'],'tzif':a['tzif_reference']},current_cache_references={t:dict(path=str(ROOT/'data/cache'/f'{t}.csv'),sha256=a['source_references'][t]['sha256'])for t in ('QQQ','SPY')},current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',source_hashes=sources,capture_started_at=a['capture_started_at'],capture_completed_at=a['capture_completed_at'],clock_captured_by_runner=True,external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',**m.FLAGS)
 pub=dict(schema='VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=cr['reference'],source_hashes=copy.deepcopy(sources),**m.FLAGS)
 audit_sources=copy.deepcopy(sources)
 for k in ('reference','publication_reference','reader_reference'):audit_sources[cr[k]['path']]=cr[k]['sha256']
 n=len(parent['document']['known_typed_rows']);counts=dict(status=plan['status'],candidate_session=plan['candidate_session'],parent_typed_row_count=n,parent_observed_count=n-5,parent_gap_count=5,diagnostic_count=0,snapshot_counts={t:plan['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')})
 audit=dict(schema='VARIABLE_PREFIX_CAPTURE_INDEPENDENT_READBACK_V1',status='PASS',capture_reference=cr['reference'],publication_reference=cr['publication_reference'],reader_sha256=cr['reader_reference']['sha256'],parent_references=pr,counts=counts,source_hashes=audit_sources,snapshot_bytes_verified=True,current_live_cache_read_or_reverified=False,external_clock_attestation_verified=False,**m.FLAGS)
 env=dict(cr,document=cap,publication=pub,readback=audit)
 capture=dict(reference=cr['reference'],started_at_utc=a['capture_started_at'],completed_at_utc=a['capture_completed_at'],sources={t:dict(bytes=a['source_bytes'][t],reference=a['source_references'][t])for t in ('QQQ','SPY')},baseline_sources={t:dict(bytes=a['baseline_bytes'][t],reference=parent['document']['baseline_references'][t])for t in ('QQQ','SPY')},tzif=dict(bytes=a['tzif_bytes'],reference=a['tzif_reference']))
 args=dict(parent_reference=pr['reference'],parent_readback_reference=pr['readback_reference'],known_typed_rows=copy.deepcopy(parent['document']['known_typed_rows']),parent_attempt_inventory=copy.deepcopy(parent['document']['parent_attempt_inventory']),capture=capture,session=plan['candidate_session'])
 core=types.ModuleType('_synthetic_payload_core');raw=m.CORE.read_bytes();assert m.sha(raw)==m.CORE_SHA;exec(compile(raw,str(m.CORE),'exec'),core.__dict__)
 s=copy.deepcopy(audit_sources)
 for r in cr.values():s[r['path']]=r['sha256']
 # Payload adds original typed-row and attempt pointers, already sealed claims in real history.
 preview=core.prepare_observation_payload(**args,writer_started_at_utc=plan['candidate_session']+'T21:01:00+00:00',writer_completed_at_utc=plan['candidate_session']+'T21:01:01+00:00');s.update(preview['source_hash_claims'])
 return parent,env,args,dict(parent=pr,capture=cr),s,core
class Tests(unittest.TestCase):
 def test_pending_before_any_io_and_fixed_payload(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'exists',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'pending'):m.run(execute=True)
  self.assertEqual(m.sha(m.CORE.read_bytes()),m.CORE_SHA)
 def test_variable_history_and_metadata_reject(self):
  for second in (False,True):
   p,c,args,refs,s,core=fixture(second);before=copy.deepcopy((p,c));self.assertEqual(m.validate_documents(p,c),args['session']);self.assertEqual((p,c),before)
  for mode in ('rows','count','baseline','none','audit','live','role','time'):
   p,c,*_=fixture();h=p['document'];plan=c['document']['plan']
   if mode=='rows':h['known_typed_rows'].pop(0)
   elif mode=='count':c['readback']['counts']['diagnostic_count']=False
   elif mode=='baseline':plan['source_evidence']['QQQ']['baseline_reference']=ref('other')
   elif mode=='none':plan['status']='NO_NEW_SESSION'
   elif mode=='audit':c['readback']['source_hashes']={}
   elif mode=='live':p['document']['source_hashes'][str(ROOT/'data/cache/QQQ.csv')]='a'*64
   elif mode=='role':plan['timing_role']='TIMELY_CERTIFIED'
   else:plan['capture_completed_at']='2000-01-01T00:00:00+00:00'
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_documents(p,c)
 def test_late_payload_persists_month_first_and_receipt_check_time(self):
  for second in (False,True):
   p,c,args,refs,s,core=fixture(second);day=args['session'];times=[day+'T21:01:00+00:00',day+'T21:01:01+00:00','2026-10-09T15:00:00+00:00']
   with tempfile.TemporaryDirectory()as td,patch.object(m,'OUTPUT',Path(td)/'attempt'),patch.object(m,'resource_gate'),patch.object(m,'load_inputs',return_value=(args,refs,s,core)),patch.object(m,'guard'),patch.object(m,'now',side_effect=times):
    r=m.run(execute=True);receipt=m.load_json(Path(r['path']).read_bytes());payload=m.load_json((m.OUTPUT/'observation_payload.json').read_bytes())
    self.assertEqual(receipt['timing_classification'],'LATE_OBSERVATION');self.assertEqual(payload['first_actual_observed_session_of_month'],'2026-10-02');self.assertFalse(receipt['month_first_actual_observation']);self.assertEqual(payload['sequence'],67+int(second));self.assertEqual(payload['known_typed_rows_preserved'],args['known_typed_rows']);self.assertEqual(payload['parent_attempt_inventory_preserved'],args['parent_attempt_inventory']);self.assertTrue(all(receipt[k]is False for k in m.FLAGS))
    self.assertEqual(receipt['publication_time_role'],'AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE')
    with self.assertRaisesRegex(ValueError,'no retry'):m.run(execute=True)
 def test_unresolved_attempt_and_publication_failures_preserve_payload(self):
  for mode in ('unresolved','receipt','clock','drift'):
   p,c,args,refs,s,core=fixture();day=args['session'];times=[day+'T21:01:00+00:00',day+'T21:01:01+00:00',day+('T21:00:00+00:00'if mode=='clock'else 'T21:01:02+00:00'),day+'T21:02:00+00:00']
   if mode=='unresolved':args['parent_attempt_inventory'][0]['status']='PAYLOAD_ONLY'
   original=m.save
   def save(path,v):
    if mode=='receipt'and path.name=='receipt.json':raise OSError('fsync failed')
    return original(path,v)
   def guard(s):
    if mode=='drift'and(m.OUTPUT/'observation_payload.json').exists():raise ValueError('source drift')
   with tempfile.TemporaryDirectory()as td,patch.object(m,'OUTPUT',Path(td)/'attempt'),patch.object(m,'resource_gate'),patch.object(m,'load_inputs',return_value=(args,refs,s,core)),patch.object(m,'guard',side_effect=guard),patch.object(m,'save',side_effect=save),patch.object(m,'now',side_effect=times):
    with self.assertRaises((ValueError,OSError)):m.run(execute=True)
    self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertEqual((m.OUTPUT/'observation_payload.json').exists(),mode!='unresolved')
    with self.assertRaisesRegex(ValueError,'no retry'):m.run(execute=True)
 def test_resources_and_no_live_permanent_closure(self):
  with tempfile.TemporaryDirectory()as td,patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=0)):
   p=Path(td)/'receipt.json'
   with self.assertRaisesRegex(ValueError,'RESOURCE'):m.save(p,{})
   self.assertFalse(p.exists());m.save(Path(td)/'failure.json',{})
  with self.assertRaisesRegex(ValueError,'LIVE_CACHE'):m.no_live({str(ROOT/'data/cache/SPY.csv'):'a'*64})
if __name__=='__main__':unittest.main()
