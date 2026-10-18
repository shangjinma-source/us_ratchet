import unittest,tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from scripts import ndx_multidecision_account_inputs_independent_readback_20261003 as r
from backtest import ndx_multidecision_account_inputs_research as producer_fixture_only
from test_ndx_multidecision_account_inputs_research import fixture


def inputs():
 a=fixture();saved=producer_fixture_only.prepare_multidecision_account_inputs(**a)
 contract=dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_SOURCE_CONTRACT_V1',**dict.fromkeys(r.PFLAGS,False),execution_contract={k:v for k,v in a['execution_contract'].items() if k!='reference'},flows_by_lane=a['flows_by_lane'],benchmark_references=a['benchmark_references'])
 return dict(saved=saved,outer_rows=a['outer_rows'],channels=a['price_evidence']['document'],price_audit=a['price_evidence']['readback'],price_refs=a['price_evidence']['references'],contract=contract,contract_ref=a['execution_contract']['reference'])

def resign(x):x['saved']['content_sha256']=r.sha(r.enc({k:v for k,v in x['saved'].items() if k!='content_sha256'}))

class Tests(unittest.TestCase):
 def test_full_saved_projection_and_source_immutability(self):
  x=inputs();b=r.enc(x);out=r.inspect_projection(**x);self.assertEqual((out['coordinate_count'],out['lane_count'],out['track_count']),(48,8,16));self.assertEqual(r.enc(x),b)
 def test_re_signed_numeric_alias_action_and_missing_mutations(self):
  for mode in ('value','alias','flow','missing','engine','flags'):
   x=inputs();lane=next(l for l in x['saved']['rows'] if l['original_targets_schedule']);t=lane['tracks'][0]
   if mode=='value':t['stateful_input']['opens']['data'][0][0]+=1
   elif mode=='alias':t['stateful_input']['schedule'][0]['targets'][next(iter(t['stateful_input']['schedule'][0]['targets']))]['ticker']='OTHER'
   elif mode=='flow':t['stateful_input']['external_flows']=[{'amount_usd':1000}]
   elif mode=='missing':t['blocking_reasons'].append({'reason':'invented'})
   elif mode=='engine':t['engine_binding']['keyword_arguments']['initial_cash_usd']=1
   else:t['point_in_time_verified']=0
   resign(x)
   with self.assertRaises(ValueError):r.inspect_projection(**x)
 def test_pre_io_missing_pins_and_same_bytes(self):
  with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(r,'INPUTS_SHA',None):
   with self.assertRaisesRegex(ValueError,'pending'):r.load_inputs()
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'a.json';p.write_bytes(b'{"v":1}');ref=r.ref(p,r.sha(p.read_bytes()))
   with patch.object(Path,'read_bytes',side_effect=[b'{"v":1}',b'{"v":2}']) as read:self.assertEqual(r.load(ref,{}),{'v':1});self.assertEqual(read.call_count,1)
 def test_real_temporary_full_source_closure(self):
  from test_ndx_multidecision_account_inputs_20261003 import physical_sources,w
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);outer,reader,bound=physical_sources(base);parent=base/'parent'
   with patch.object(w,'ROOT',base),patch.object(w,'OUTER_ROOT',outer),patch.object(w,'OUTER_READER',Path(reader['path'])),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',parent),patch.object(w,'resource'):
    source=w.run(execute=True)
   with patch.object(r,'ROOT',base),patch.object(r,'OUTER_ROOT',outer),patch.object(r,'OUTER_READER',Path(reader['path'])),patch.object(r,'BOUND',bound),patch.object(r,'PARENT',parent),patch.object(r,'OUTPUT',base/'reader'),patch.object(r,'INPUTS_SHA',source['sha256']),patch.object(r,'PUBLICATION_SHA',r.hashfile(parent/'publication.json')):
    report=r.readback(execute=True);self.assertEqual(r.decode(Path(report['path']).read_bytes())['inspection']['coordinate_count'],48)
 def test_output_source_drift_preserves_failure(self):
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);src=base/'source';src.write_bytes(b'x');c=dict(args=inputs(),sources={str(src):r.sha(b'x')},inputs_reference=r.ref(src,r.sha(b'x')),publication_reference=r.ref(src,r.sha(b'x')),outer_inventory=[]);original=r.save
   def saving(name,value,emergency=False):
    v=original(name,value,emergency)
    if name=='independent_readback.json':src.write_bytes(b'drift')
    return v
   with patch.object(r,'OUTPUT',base/'out'),patch.object(r,'load_inputs',return_value=c),patch.object(r,'inventory'),patch.object(r,'save',side_effect=saving):
    with self.assertRaisesRegex(ValueError,'drift'):r.readback(execute=True)
    self.assertTrue((r.OUTPUT/'failure.json').exists())
    with self.assertRaisesRegex(ValueError,'no retry'):r.readback(execute=True)

if __name__=='__main__':unittest.main()
