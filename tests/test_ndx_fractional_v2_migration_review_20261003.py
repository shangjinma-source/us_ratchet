"""Independent migration proof and synthetic dispatched V2 snapshot regression."""
from pathlib import Path
import hashlib,json,unittest,ast
from scripts import ndx_multidecision_account_execution_20261003 as worker
from backtest import ndx_incumbent_flow_split_control_research as control
from test_ndx_dynamic_fractional_flow_split_research import fixture,split,flow
from test_ndx_incumbent_flow_split_control_research import fixture as control_fixture

ROOT=Path(__file__).resolve().parents[1]
SNAPSHOTS=ROOT/'tests/fixtures/migration_snapshots_20261008/fractional'
class Review(unittest.TestCase):
 def test_all_migration_bytes_and_frozen_v1(self):
  backup=ROOT/'tmp/fractional_v2_binding_migration_20261003_v1';items=json.loads((backup/'manifest.json').read_text())
  self.assertEqual(len(items),12)
  for item in items:
   old=(backup/item['path']).read_bytes();current=(SNAPSHOTS/item['path']).read_bytes()
   self.assertEqual(hashlib.sha256(old).hexdigest(),item['before']);self.assertEqual(hashlib.sha256(current).hexdigest(),item['after'])
   expected=old
   for before,after,count in item['replacements']:
    self.assertEqual(expected.count(before.encode()),count);expected=expected.replace(before.encode(),after.encode())
   if 'extra_step' in item:
    newline=b'\r\n' if b'\r\n' in expected else b'\n'
    helper=b" 'ndx_dynamic_fractional_flow_split_research':'d33937157b7b3e4aa0d031962d1a0b0669eb7aa0ded7c1f8818b5d4348291687',"+newline
    expected=expected.replace(b'CODE={'+newline,b'CODE={'+newline+helper)
   self.assertEqual(current,expected,item['path'])
  self.assertEqual(hashlib.sha256((ROOT/'backtest/ndx_dynamic_fractional_flow_split_research.py').read_bytes()).hexdigest(),'d33937157b7b3e4aa0d031962d1a0b0669eb7aa0ded7c1f8818b5d4348291687')
  # Pending is a property of the historical migration, not of current production.
  import types
  original_path=ROOT/'scripts/ndx_multidecision_account_execution_20261003.py'
  historical=types.ModuleType('historical_worker');historical.__file__=str(original_path)
  exec(compile((SNAPSHOTS/'scripts'/original_path.name).read_bytes(),str(original_path),'exec'),historical.__dict__)
  self.assertTrue(all(h is None for _,h in historical.BOUND.values()))
 def test_private_worker_dispatch_v2_and_v1_helpers_only(self):
  sources={};engines,_,_=worker.private_engines(sources)
  self.assertEqual(worker.ENGINES['CONTINUOUS'][0],'ndx_dynamic_fractional_flow_split_research_v2')
  self.assertEqual(engines['CONTINUOUS'].__globals__['SCHEMA'],'DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2')
  helper=engines['WHOLE_LOT'].__globals__['flow_validation']
  def forbidden(**kwargs):raise AssertionError('Frozen V1 simulation must not dispatch')
  helper.simulate_dynamic_fractional_flow_split_research=forbidden
  a=fixture();a['corporate_actions']=[split()];a['external_flows']=[flow()];a['opens'].iloc[2:,0]=5.;a['closes'].iloc[2:,0]=5.
  out=engines['CONTINUOUS'](**a);self.assertEqual(out['rebalances'][0]['projection']['holdings']['SID']['shares'],10.);self.assertEqual(out['daily'][-1]['holdings']['SID']['shares'],20.)
  whole=control_fixture('WHOLE_LOT');whole.pop('track');engines['WHOLE_LOT'](**whole)
  called={n.attr for n in ast.walk(ast.parse((ROOT/'backtest/ndx_dynamic_frozen_flow_split_research.py').read_text())) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='flow_validation'}
  self.assertEqual(called,{'day','numeric','reference'})
 def test_control_continuous_snapshot_also_uses_v2(self):
  a=control_fixture('CONTINUOUS');a['corporate_actions']=[dict(security_id='A',session='2026-04-02',new_shares=2,old_shares=1,source_url='https://example.com/split',evidence_sha256='b'*64)];a['opens'].loc['2026-04-02':,'A']=5.;a['closes'].loc['2026-04-02':,'A']=5.
  out=control.simulate_incumbent_flow_split_control(**a)
  self.assertEqual(out['rebalances'][0]['projection']['holdings'],out['rebalances'][0]['holdings_after'])
  self.assertAlmostEqual(out['daily'][-1]['holdings']['A']['shares'],out['rebalances'][0]['projection']['holdings']['A']['shares']*2)
  self.assertIn('research_v2',control.fractional.__name__)

if __name__=='__main__':unittest.main()
