import copy,importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from scripts import ndx_variable_prefix_source_capture_20261003 as m
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('variable_fixture',ROOT/'tests/test_ndx_variable_prefix_capture_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class Tests(unittest.TestCase):
 def test_pending_before_any_source_or_current_io(self):
  with patch.object(m,'PARENT_BOUND',dict.fromkeys(('reference','publication_reference','readback_reference','reader_reference'))),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'exists',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.run(execute=True)
 def test_private_bytes_core_and_fixed_current_paths(self):
  raw={k:(ROOT/p).read_bytes()for k,(p,h)in m.PINS.items()if k!='tzif'}
  core=m.private_core(raw);self.assertEqual(core.plan_history_capture(**f.fixture())['candidate_sequence'],67)
  self.assertEqual(m.CURRENT,{t:ROOT/'data/cache'/f'{t}.csv'for t in ('QQQ','SPY')})
  raw['core']+=b'\n'
  with self.assertRaisesRegex(ValueError,'SHA'):m.private_core(raw)
 def test_local_capture_failure_preserved_and_no_retry(self):
  for mode in ('ok','clock','drift'):
   args=f.fixture();parent=args['parent'];core=m.private_core({k:(ROOT/p).read_bytes()for k,(p,h)in m.PINS.items()if k!='tzif'})
   with tempfile.TemporaryDirectory()as td:
    root=Path(td);out=root/'capture';live={t:root/f'{t}.csv'for t in ('QQQ','SPY')}
    for t,p in live.items():p.write_bytes(args['source_bytes'][t])
    state=(parent,{}, {},{'tzif':args['tzif_bytes']},args['baseline_bytes'],{},core)
    times=[args['capture_started_at'],args['capture_completed_at']]
    if mode=='clock':times.reverse()
    def guard(s):
     if mode=='drift'and(out/'capture.json').exists():raise ValueError('drift')
    with patch.object(m,'OUTPUT',out),patch.object(m,'CURRENT',live),patch.object(m,'load',return_value=state),patch.object(m,'resource_gate'),patch.object(m,'guard',side_effect=guard),patch.object(m,'now',side_effect=times):
     if mode=='ok':
      result=m.run(execute=True);doc=m.loads(Path(result['capture_reference']['path']).read_bytes());self.assertEqual(doc['plan']['status'],'ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED');self.assertFalse(doc['observation_created']);self.assertEqual((out/'QQQ.csv').read_bytes(),args['source_bytes']['QQQ'])
     else:
      with self.assertRaises(ValueError):m.run(execute=True)
      self.assertTrue((out/'failure.json').exists())
     with self.assertRaisesRegex(ValueError,'Create-only'):m.run(execute=True)
 def test_low_disk_refuses_ordinary_write_failure_still_saves(self):
  with tempfile.TemporaryDirectory()as td,patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
   p=Path(td)/'capture.json'
   with self.assertRaisesRegex(ValueError,'RESOURCE'):m.save(p,{})
   self.assertFalse(p.exists());m.save(Path(td)/'failure.json',{'status':'FAILED_DO_NOT_CONSUME'})
   with self.assertRaises(ValueError):m.resource_gate(True)
if __name__=='__main__':unittest.main()
