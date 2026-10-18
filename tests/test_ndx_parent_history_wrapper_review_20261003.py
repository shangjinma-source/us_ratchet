import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from test_ndx_prospective_observation_parent_history_20261003 import setup,f
from scripts import ndx_prospective_observation_parent_history_20261003 as m
from backtest import ndx_prospective_observation_parent_history_research as core

class Review(unittest.TestCase):
 def test_explicit_future_roles_before_any_io_and_consumed_claim_conflict(self):
  with patch.object(m,'OBSERVATION_BOUND',dict.fromkeys(m.OBSERVATION_BOUND)),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'exists',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.run(execute=True)
  sources={'x':'a'*64}
  with self.assertRaisesRegex(ValueError,'conflict'):m.add_claims({'source_hashes':{'x':'b'*64}},sources)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'bad';p.write_bytes(b'actual')
   with self.assertRaisesRegex(ValueError,'changed'):m.consume({'path':str(p),'sha256':'a'*64},{})
 def test_late_month_first_and_full_parent_preserved_compact_second(self):
  g,o=setup();h=m.prepare(g,None,o,core);parent=f.envelope(h,'history1');o2=f.observation(g,parent,'2026-10-05');before=copy.deepcopy((g,parent,o2));out=m.prepare(g,parent,o2,core)
  self.assertEqual((g,parent,o2),before);self.assertEqual(out['known_typed_rows'][:-1],h['known_typed_rows']);self.assertEqual(out['observations'][0],h['observations'][0]);self.assertEqual(out['first_actual_observed_session_by_month']['2026-10'],'2026-10-02');self.assertFalse(out['observations'][1]['month_first_actual_observation']);self.assertTrue(all(out[k] is False for k in core.FLAGS));self.assertEqual(out['baseline_references'],core.captured_baselines(o2['payload']))
  for key in ('payload','receipt','audit'):self.assertNotIn(key,out['observations'][0])
  o2['audit']['schema']='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1'
  with self.assertRaises(ValueError):m.prepare(g,parent,o2,core)
 def test_partial_namespace_or_wrong_receipt_location_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);r={k:f.ref(str(root/n)) for k,n in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]}
   for name in ('started.json','observation_payload.json','receipt.json','independent_readback.json'):(root/name).write_bytes(b'{}')
   m.observation_namespace(r);bad=copy.deepcopy(r);bad['receipt_reference']['path']=str(root/'elsewhere'/'receipt.json')
   with self.assertRaises(ValueError):m.observation_namespace(bad)
   (root/'receipt.json').unlink()
   with self.assertRaises(ValueError):m.observation_namespace(r)
   (root/'receipt.json').write_bytes(b'{}');(root/'failure.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):m.observation_namespace(r)
 def test_receipt_write_failure_preserves_history_and_no_retry(self):
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/'history';g,o=setup();h=m.prepare(g,None,o,core);gb={k:(g[k]['path'],g[k]['sha256']) for k in ('reference','publication_reference','readback_reference','reader_reference')};ob={k:(o[k]['path'],o[k]['sha256']) for k in m.OBSERVATION_BOUND};bb={k:(r['path'],r['sha256']) for k,r in g['baseline_references'].items()};code=Path(m.CORE[0]).read_bytes();raw={o[k]['path']:m.enc(o[v]) for k,v in [('payload_reference','payload'),('receipt_reference','receipt'),('audit_reference','audit')]};save=m.save
   def consume(r,s):m.merge(s,r);return code if r['path']==m.CORE[0] else raw.get(r['path'],b'synthetic')
   def failing(p,v):
    if p.name=='publication.json':raise OSError('synthetic receipt write failure')
    return save(p,v)
   with patch.object(m,'OUTPUT',out),patch.object(m,'GENESIS_BOUND',gb),patch.object(m,'OBSERVATION_BOUND',ob),patch.object(m,'BASELINE_BOUND',bb),patch.object(m,'load_envelope',return_value=g),patch.object(m,'consume',side_effect=consume),patch.object(m,'observation_namespace'),patch.object(m,'guard'),patch.object(m,'prepare',return_value=h),patch.object(m,'save',side_effect=failing):
    with self.assertRaisesRegex(OSError,'receipt write'):m.run(execute=True)
    self.assertEqual({p.name for p in out.iterdir()},{'started.json','history.json','failure.json'});failure=json.loads((out/'failure.json').read_bytes());self.assertIs(failure['retry_allowed'],False)
    with self.assertRaisesRegex(ValueError,'Create-only'):m.run(execute=True)
if __name__=='__main__':unittest.main()
