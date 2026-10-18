"""Only synthetic envelopes and temporary publication directories."""
import copy,importlib.util,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_prospective_observation_parent_history_20261003 as m
from backtest import ndx_prospective_observation_parent_history_research as core
spec=importlib.util.spec_from_file_location('history_fixtures',ROOT/'tests/test_ndx_prospective_observation_parent_history_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def setup():
 g=f.genesis();o=f.observation(g,late=True);return g,o
class Tests(unittest.TestCase):
 def test_none_before_any_io(self):
  with patch.object(m,'OBSERVATION_BOUND',dict.fromkeys(m.OBSERVATION_BOUND)),patch.object(Path,'read_bytes',side_effect=AssertionError('IO forbidden')),patch.object(Path,'exists',side_effect=AssertionError('IO forbidden')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.run(execute=True)
 def test_compact_first_and_explicit_second_v2_no_v1_expansion(self):
  g,o=setup();original=copy.deepcopy((g,o));h=m.prepare(g,None,o,core);self.assertEqual((g,o),original);self.assertEqual(h['observation_count'],1);self.assertNotIn('payload',h['observations'][0]);self.assertFalse(h['observations'][0]['original_payload_embedded']);self.assertEqual(h['observations'][0]['timing_classification'],'LATE_OBSERVATION')
  p=f.envelope(h,'prior');o2=f.observation(g,p,'2026-10-05');h2=m.prepare(g,p,o2,core);self.assertEqual(h2['observation_count'],2);self.assertFalse(o2['payload']['month_first_actual_observation'])
  o2['audit']['schema']='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1'
  with self.assertRaisesRegex(ValueError,'later observations'):m.prepare(g,p,o2,core)
 def test_no_partial_or_bad_external_audit_and_no_raw_compact_expansion(self):
  for attack in ('audit','rawsource','receipt','zero_count'):
   g,o=setup()
   if attack=='audit':o['audit']['status']='FAILED'
   elif attack=='rawsource':o['payload']['full_original_sources_preserved']['QQQ']['sources']['reference']=f.ref('wrong')
   elif attack=='receipt':o['receipt']['payload_reference']=f.ref('wrong')
   else:o['audit']['counts']['new_observation_count']=True
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.prepare(g,None,o,core)
 def test_namespace_and_post_publication_drift_preserves_failure(self):
  with tempfile.TemporaryDirectory()as tmp:
   out=Path(tmp)/'result';g,o=setup();h=m.prepare(g,None,o,core)
   gb={k:(g[k]['path'],g[k]['sha256'])for k in ('reference','publication_reference','readback_reference','reader_reference')};ob={k:(o[k]['path'],o[k]['sha256'])for k in m.OBSERVATION_BOUND};bb={k:(v['path'],v['sha256'])for k,v in g['baseline_references'].items()};code=Path(m.CORE[0]).read_bytes();raw={o[k]['path']:m.enc(o[v])for k,v in [('payload_reference','payload'),('receipt_reference','receipt'),('audit_reference','audit')]}
   def consume(r,s):
    m.merge(s,r)
    if r['path']==m.CORE[0]:return code
    return raw.get(r['path'],b'csv-or-code')
   calls=[]
   def guard(_):
    calls.append(1)
    if len(calls)==3:raise ValueError('post publication drift')
   with patch.object(m,'OUTPUT',out),patch.object(m,'GENESIS_BOUND',gb),patch.object(m,'BASELINE_BOUND',bb),patch.object(m,'OBSERVATION_BOUND',ob),patch.object(m,'load_envelope',return_value=g),patch.object(m,'consume',side_effect=consume),patch.object(m,'observation_namespace'),patch.object(m,'guard',side_effect=guard),patch.object(m,'prepare',return_value=h):
    with self.assertRaisesRegex(ValueError,'post publication drift'):m.run(execute=True)
    self.assertEqual({p.name for p in out.iterdir()},{'started.json','history.json','publication.json','failure.json'})
    with self.assertRaisesRegex(ValueError,'Create-only'):m.run(execute=True)
   obs=Path(tmp)/'obs';obs.mkdir();rs={k:f.ref(str(obs/n))for k,n in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]}
   for n in ('started.json','observation_payload.json','receipt.json','independent_readback.json'):(obs/n).write_bytes(b'{}')
   m.observation_namespace(rs);(obs/'failure.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):m.observation_namespace(rs)
if __name__=='__main__':unittest.main()
