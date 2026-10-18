import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_prospective_observation_parent_history_independent_readback_20261003 as m
from backtest import ndx_prospective_observation_parent_history_research as producer
spec=importlib.util.spec_from_file_location('history_fixture',ROOT/'tests/test_ndx_prospective_observation_parent_history_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def fixture(second=False):
 g=f.genesis();o=f.observation(g,late=True);h=producer.append_observation_history(genesis=g,previous_history=None,observation=o);previous=None
 if second:
  previous=f.envelope(h,'previous');o=f.observation(g,previous,'2026-10-05');h=producer.append_observation_history(genesis=g,previous_history=previous,observation=o)
 return h,g,previous,o

class Tests(unittest.TestCase):
 def test_independent_two_appends_late_first_failed_unknown_prefix(self):
  for second in (False,True):
   args=fixture(second);before=copy.deepcopy(args);out=m.inspect(*args);self.assertEqual(args,before)
   self.assertEqual(out['typed_row_count'],66+int(second));self.assertEqual(out['first_actual_observed_session_by_month']['2026-10'],'2026-10-02');self.assertEqual(out['source_claims'],args[0]['source_hashes'])
 def test_prefix_compact_attempt_baseline_and_month_mutations(self):
  for mode in ('prefix','month','attempt','embed','baseline','bool','claim'):
   h,g,p,o=fixture(True)
   if mode=='prefix':h['known_typed_rows'][0]['seal_status']='SEALED'
   elif mode=='month':h['first_actual_observed_session_by_month']['2026-10']='2026-10-05'
   elif mode=='attempt':h['parent_attempt_inventory'].pop(0)
   elif mode=='embed':h['observations'][-1]['payload']={}
   elif mode=='baseline':o['payload']['full_original_sources_preserved']['QQQ']['baseline_sources']['reference']=f.ref('wrong')
   elif mode=='bool':o['audit']['counts']['new_observation_count']=True
   else:o['receipt']['source_hashes']['extra']='f'*64
   with self.subTest(mode=mode),self.assertRaises((ValueError,KeyError)):m.inspect(h,g,p,o)
 def test_v1_cannot_certify_second_or_wrong_parent(self):
  for mode in ('v1','reader','parent','authority'):
   h,g,p,o=fixture(True)
   if mode=='v1':o['audit']['schema']='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1'
   elif mode=='reader':p['readback']['reader_sha256']='a'*64
   elif mode=='parent':o['audit']['parent_history_reference']=f.ref('wrong')
   else:h['candidate_seal_allowed']=0
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect(h,g,p,o)
 def test_future_anchors_block_before_io_and_namespace_extra_refused(self):
  with patch.dict(m.BOUND, {'history': (m.BOUND['history'][0], None)}), patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'exists',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
  with tempfile.TemporaryDirectory()as t:
   d=Path(t)
   for n in ('started.json','history.json','publication.json'):(d/n).write_bytes(b'{}')
   m.directory(d,('started.json','history.json','publication.json'));(d/'failure.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):m.directory(d,('started.json','history.json','publication.json'))
 def test_sourcebound_synthetic_publication_and_postwrite_drift(self):
  for drift in (False,True):
   h,g,previous,o=fixture();result=m.inspect(h,g,None,o)
   with tempfile.TemporaryDirectory()as t:
    root=Path(t);parent=root/'producer';parent.mkdir();out=root/'reader'
    refs={k:g[k]for k in ('reference','publication_reference','readback_reference','reader_reference')};orefs={k:o[k]for k in m.OBSERVATION_BOUND};base=g['baseline_references'];core=m.reference(*m.CORE)
    producer_ref=f.ref('synthetic_producer');sources=dict(result['source_claims']);m.merge(sources,producer_ref);m.merge(sources,core)
    inputs=dict(genesis=refs,baseline=base,previous_history=None,observation=orefs,core=core)
    flags=dict.fromkeys(m.WRAPPER_FALSE,False);h.update(input_references=inputs,source_hashes=sources,source_reference_claims_preserved_from_pure=result['source_claims'],**flags)
    hr=m.reference(str(parent/'history.json'),m.digest(m.encoded(h)))
    pub=dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2',status='PUBLISHED_OBSERVATION_HISTORY_NO_SEAL',history_reference=hr,observation_count=1,new_observation_reference=orefs['payload_reference'],previous_history_reference=None,source_hashes=sources,**flags)
    pr=m.reference(str(parent/'publication.json'),m.digest(m.encoded(pub)))
    (parent/'started.json').write_bytes(m.encoded(dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_STARTED_V2',input_references=inputs,source_hashes=sources,**flags)))
    data={hr['path']:m.encoded(h),pr['path']:m.encoded(pub),**{o[k]['path']:m.encoded(o[n])for n,k in [('payload','payload_reference'),('receipt','receipt_reference'),('audit','audit_reference')]}}
    def read(r,s):m.merge(s,r);return data.get(r['path'],b'code or csv')
    def guard(s):
     if drift and (out/'independent_readback.json').exists():raise ValueError('postwrite drift')
    config=lambda v:{k:(r['path'],r['sha256'])for k,r in v.items()}
    # Paths are synthetic fixture references; mock filesystem boundary, never production algorithms.
    with patch.object(m,'BOUND',config(dict(history=hr,publication=pr,producer=producer_ref))),patch.object(m,'OBSERVATION_BOUND',config(orefs)),patch.object(m,'GENESIS',config(refs)),patch.object(m,'BASELINES',config(base)),patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',out),patch.object(m,'read',side_effect=read),patch.object(m,'load_envelope',return_value=g),patch.object(m,'directory'),patch.object(m,'guard',side_effect=guard),patch.object(m,'exact',wraps=m.exact)as exact:
     # Real production observation paths are same-directory; override this fixture's arbitrary paths only.
     original=m.exact
     def comparison(a,b):
      if type(a)is str and a in [orefs[k]['path']for k in ('payload_reference','receipt_reference','audit_reference')]:return
      return m.require(m.encoded(a)==m.encoded(b),'Exact saved values/types')
     exact.side_effect=comparison
     if drift:
      with self.assertRaisesRegex(ValueError,'postwrite drift'):m.readback(execute=True)
      self.assertTrue((out/'failure.json').exists())
     else:
      r=m.readback(execute=True);self.assertEqual(m.loads(Path(r['path']).read_bytes())['status'],'PASS')
     with self.assertRaisesRegex(ValueError,'Create-only'):m.readback(execute=True)
if __name__=='__main__':unittest.main()
