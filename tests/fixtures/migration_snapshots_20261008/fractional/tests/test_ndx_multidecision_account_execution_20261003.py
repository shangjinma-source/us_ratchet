from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_account_execution_20261003 as w
from backtest import ndx_multidecision_account_inputs_research as prepare
from test_ndx_multidecision_account_inputs_research import fixture


def physical(root):
    parent=root/'parent';parent.mkdir()
    def put(path,body,raw=False):
      path.parent.mkdir(parents=True,exist_ok=True);b=body if raw else w.enc(body);path.write_bytes(b);return w.ref(path,w.sha(b))
    args=fixture();args['execution_contract']['cash_flow_role']='EXPLICIT_NEW_CASH_RESEARCH'
    args['flows_by_lane'][prepare.MODES[1]+'|RETURN']=[dict(session='2026-04-02',amount_usd=1000,currency='USD',timing='BEFORE_OPEN',source_reference={'path':'/synthetic/flow','sha256':'a'*64})]
    inputs=prepare.prepare_multidecision_account_inputs(**args)
    flags=dict.fromkeys(w.PARENT_FLAGS,False)
    started=put(parent/'started.json',dict(source_hashes={}))
    ir=put(parent/'inputs.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1',inputs=inputs,input_references={},source_hashes={},**flags))
    pr=put(parent/'publication.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1',status='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS',inputs_reference=ir,started_reference=started,input_references={},source_hashes={},**flags))
    reader=put(root/'reader.py',b'raise AssertionError("never execute input reader")',True)
    audit=put(root/'audit.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',scope='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION',inputs_reference=ir,publication_reference=pr,reader_sha256=reader['sha256'],source_hashes={r['path']:r['sha256'] for r in (ir,pr,reader,started)},inspection=dict(coordinate_count=48,lane_count=8,track_count=16,security_count=77,issuer_count=76,provenance_count=101,sidecar_count=7),**dict.fromkeys(('producer_called','account_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'),False)))
    for name in w.CODE:put(root/'backtest'/f'{name}.py',(w.ROOT/'backtest'/f'{name}.py').read_bytes(),True)
    refs=dict(inputs=ir,publication=pr,readback=audit,reader=reader)
    return parent,{k:(r['path'],r['sha256']) for k,r in refs.items()}


class Tests(unittest.TestCase):
 def test_pending_refuses_before_io(self):
    with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
      with self.assertRaisesRegex(ValueError,'pending'):w.load_inputs()
 def test_complete_physical_inputs_private_engines_16_slots_and_isolated_cash(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td);parent,bound=physical(root);output=root/'out'
      with patch.object(w,'ROOT',root),patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',output),patch.object(w,'resource'):
        resultref=w.run(execute=True)
        with self.assertRaisesRegex(ValueError,'Exclusive'):w.run(execute=True)
      result=w.decode(Path(resultref['path']).read_bytes())
      self.assertEqual(result['account_call_count'],8);self.assertEqual(result['returned_call_count'],8);self.assertEqual(len(result['rows']),16)
      self.assertEqual(result['counts'],{'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT':8,'ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK':8})
      self.assertTrue(all(r['raw_reference'] is None for r in result['rows'][:8]))
      first=w.decode(Path(result['rows'][8]['raw_reference']['path']).read_bytes())['result'];other=w.decode(Path(result['rows'][10]['raw_reference']['path']).read_bytes())['result']
      self.assertEqual(sum(r['cash_injection_usd'] for r in first['daily']),1000);self.assertEqual(sum(r['cash_injection_usd'] for r in other['daily']),0)
      self.assertEqual(len(first['daily']),len(other['daily']));self.assertEqual(first['daily'][0]['normalized_twr'],1.)
      self.assertFalse(result['fit_performed']);self.assertFalse(result['actual_orders_executed'])
 def test_real_loader_rejects_wrong_audit_input_and_strict_bool_count(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td);parent,bound=physical(root)
      for mutate in (lambda a:a['inputs_reference'].update(sha256='f'*64),lambda a:a['inspection'].update(track_count=True)):
        audit=w.decode(Path(bound['readback'][0]).read_bytes());original=deepcopy(audit);mutate(audit);Path(bound['readback'][0]).write_bytes(w.enc(audit));bad=deepcopy(bound);bad['readback']=(bound['readback'][0],w.sha(w.enc(audit)))
        with patch.object(w,'ROOT',root),patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bad):
          with self.assertRaises(ValueError):w.load_inputs()
        Path(bound['readback'][0]).write_bytes(w.enc(original))
 def test_return_none_and_exception_raw_first_stop_without_fake_accounts(self):
    for returns_none in (True,False):
      with self.subTest(returns_none=returns_none),tempfile.TemporaryDirectory() as td:
        root=Path(td);parent,bound=physical(root);output=root/'out';real=w.private_engines
        def fake(s):
          engines,pd,runtime=real(s)
          def result(**kwargs):
            if returns_none:return None
            raise ArithmeticError('synthetic numerical failure')
          engines['CONTINUOUS']=result;return engines,pd,runtime
        with patch.object(w,'ROOT',root),patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',output),patch.object(w,'resource'),patch.object(w,'private_engines',side_effect=fake):
          with self.assertRaisesRegex(ValueError,'technical failure'):w.run(execute=True)
        raw=w.decode((output/'tracks/08/raw_result.json').read_bytes());result=w.decode((output/'result.json').read_bytes())
        self.assertEqual(raw['returned'],returns_none);self.assertEqual(raw['returned_call_count'],int(returns_none));self.assertIsNone(raw['result'])
        self.assertEqual(result['rows'][8]['outcome'],'VALIDATION_FAILURE' if returns_none else 'NUMERICAL_EXCEPTION');self.assertEqual(result['counts']['UNDISPATCHED'],7)
        self.assertTrue((output/'failure.json').exists());self.assertFalse((output/'publication.json').exists())
 def test_raw_return_survives_postcall_resource_gate(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td);parent,bound=physical(root);output=root/'out';real=w.private_engines;done=[False]
      def engines(s):
        es,pd,runtime=real(s);old=es['CONTINUOUS']
        def call(**kwargs):
          result=old(**kwargs);done[0]=True;return result
        es['CONTINUOUS']=call;return es,pd,runtime
      def resource(size=0):
        if done[0]:raise ValueError('synthetic postcall low space')
      with patch.object(w,'ROOT',root),patch.object(w,'PARENT',parent),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',output),patch.object(w,'resource',side_effect=resource),patch.object(w,'private_engines',side_effect=engines):
        with self.assertRaises(ValueError):w.run(execute=True)
      raw=w.decode((output/'tracks/08/raw_result.json').read_bytes());self.assertTrue(raw['returned']);self.assertEqual(raw['result']['schema'],'DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2');self.assertTrue((output/'failure.json').exists())

if __name__=='__main__':unittest.main()
