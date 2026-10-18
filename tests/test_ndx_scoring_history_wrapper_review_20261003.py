from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile,unittest
from scripts import ndx_multidecision_scoring_history_20261003 as m
from test_ndx_multidecision_scoring_history_20261003 import fixture

class Review(unittest.TestCase):
 def test_original_inventory_order_and_foreign_evidence(self):
  docs,refs,_=fixture();before=deepcopy(docs);req=m.prepare(docs,refs)
  cols=docs['panel']['panel']['universe']['columns'];expected=[dict(zip(cols,r))for r in docs['panel']['panel']['universe']['data']]
  self.assertEqual([r['coordinate']for r in req],expected);self.assertEqual(docs,before)
  attacks=[lambda d:d['history_audit'].update(reader_sha256='0'*64),lambda d:d['history_publication']['requirements_reference'].update(path='foreign'),lambda d:d['history']['requirements']['ticker_observations_preserved'][req[0]['coordinate']['ticker']]['raw_reference'].update(sha256='0'*64),lambda d:d['history']['requirements']['reference_calendar']['dates'].remove('2026-03-31'),lambda d:d['panel']['panel'].update(point_in_time_verified=0)]
  for f in attacks:
   bad=deepcopy(docs);f(bad)
   with self.assertRaises(ValueError):m.prepare(bad,refs)
 def test_guard_parent_failure_and_loaded_source_drift(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);r={}
   for role in ('history','panel','bridge'):
    p=root/role;p.mkdir();file=p/'input.json';file.write_bytes(b'{}');r[role]={'path':str(file),'sha256':m.sha(b'{}')}
   sources={v['path']:v['sha256']for v in r.values()};m.guard(sources,r)
   (Path(r['bridge']['path']).parent/'failure.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):m.guard(sources,r)
   with patch.object(m,'LOADED_SHA','0'*64):
    with self.assertRaises(ValueError):m.guard({},r)
 def test_final_previous_channel_drift_leaves_failure_no_retry(self):
  docs,refs,_=fixture();requests=m.prepare(docs,refs)
  fake=SimpleNamespace(materialize_scoring_history_channel=lambda **kw:dict(status='PARTIAL_NUMERIC_SUPPLY_FULL_SCORING_BLOCKED',regular_floor=None,decisions=[]))
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);requests=deepcopy(requests)
   for i,r in enumerate(requests):
    for field in ('raw_reference','receipt_reference'):
     p=root/(str(i)+field);p.write_bytes(b'{}');r[field]=dict(path=str(p),sha256=m.sha(b'{}'))
   original_save=m.save
   def save(p,value,failure=False):
    ref=original_save(p,value,failure)
    if p.name=='publication.json':(p.parent/'channel_000.json').write_bytes(b'corrupt')
    return ref
   with patch.object(m,'OUTPUT',root/'out'),patch.object(m,'load_inputs',return_value=(docs,refs,{},requests,b'TZ',fake)),patch.object(m,'space'),patch.object(m,'guard'),patch.object(m,'validate_channel'),patch.object(m,'save',side_effect=save):
    with self.assertRaisesRegex(ValueError,'Final output drift'):m.run(execute=True)
    self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'publication.json').exists());self.assertEqual(len(list(m.OUTPUT.glob('channel_*.json'))),77)
    with self.assertRaisesRegex(ValueError,'Immutable namespace'):m.run(execute=True)
if __name__=='__main__':unittest.main()
