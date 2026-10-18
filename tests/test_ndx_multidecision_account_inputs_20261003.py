from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_account_inputs_20261003 as w
from backtest import ndx_multidecision_account_inputs_research as core
from test_ndx_multidecision_account_inputs_research import fixture


def staged(root):
    args=fixture();source=root/'source';source.write_bytes(b'fixed')
    return dict(args=args,core=core,sources={str(source):w.sha(b'fixed')},input_references={},outer_started_reference=w.reference(source,w.sha(b'fixed')),outer_started_externally_anchored=False,coordinator_file_inventory=[])

def physical_sources(root):
    a=fixture();outer=root/'outer';(outer/'coordinates').mkdir(parents=True)
    def put(p,obj,raw=False):
      p.parent.mkdir(parents=True,exist_ok=True);b=obj if raw else w.enc(obj);p.write_bytes(b);return w.reference(p,w.sha(b))
    reader=put(root/'outer_reader.py',b'# never executed',True);coord=put(root/'coordinator.py',b'# never executed',True)
    receipt=put(root/'receipt.json',dict(schema='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1',reader_reference=reader))
    outerflags=dict.fromkeys(w.OUTER_FLAGS,False);rows=[];initial=[]
    for i,r in enumerate(a['outer_rows']):
      c=r['coordinate'];item=dict(cutoff=c[0],fx_mode=c[1],lane=c[2]);initial.append(item)
      row=dict(coordinate_index=i,coordinate=c,outcome='SOURCE_BLOCKED' if r['evidence'] is None else 'AUDITED_DIRECT_SUCCESS')
      if r['evidence'] is None:
        row['blocked_state_reference']=put(outer/f'coordinates/{i:02d}.json',dict(schema='OUTER_LANE_COORDINATE_NOT_DISPATCHED_V1',coordinate_index=i,prepared_row=item,**outerflags))
      else:
        e=deepcopy(r['evidence']);home=root/'evidence'/str(i);refs={'reader':reader}
        refs['request']=put(home/'request.json',e['request']);refs['raw_result']=put(home/'raw_result.json',e['raw_result'])
        e['postcheck'].update(request_reference=refs['request'],raw_result_reference=refs['raw_result']);refs['postcheck']=put(home/'postcheck.json',e['postcheck'])
        e['readback'].update(reader_sha256=reader['sha256'],source_hashes={v['path']:v['sha256'] for v in refs.values()})
        for role in ('request','raw_result','postcheck'):e['readback'][role+'_reference']=refs[role]
        refs['readback']=put(home/'readback.json',e['readback'])
        row.update(evidence_references=refs,postcheck_reference=refs['postcheck'],readback_reference=refs['readback'])
        row['dispatch_started_reference']=put(outer/f'coordinates/{i:02d}-dispatch.json',dict(schema='OUTER_LANE_COORDINATE_DISPATCH_STARTED_V1',coordinate_index=i,request=e['request'],**outerflags))
        put(outer/f'coordinates/{i:02d}-accepted.json',row)
      rows.append(row)
    prep=put(outer/'prepared48.json',dict(schema='OUTER_LANE_FULL48_INITIAL_PREPARATION_V1',prepared={'rows':initial},**outerflags))
    put(outer/'started.json',dict(schema='OUTER_LANE_FULL48_COORDINATOR_STARTED_V1',coordinate_count=48,receipt_contract_reference=receipt,source_hashes={coord['path']:coord['sha256']},**outerflags))
    result=put(outer/'result.json',dict(schema='OUTER_LANE_FULL48_COORDINATOR_RESULT_V1',status='COMPLETED_REGISTERED_COORDINATES',failure=None,rows=rows,prepared_reference=prep,**outerflags))
    # Authenticate synthetic underlying raw/receipt bytes, not only parent projections.
    for i,r in enumerate(a['price_evidence']['document']['rows']):
      ch=r['channel'];raw=put(root/f'prices/raw{i}',b'raw',True);rr=put(root/f'prices/receipt{i}',b'receipt',True)
      ch.update(raw_reference=raw,receipt_reference=rr);ch['receipt_preserved'].update(raw_path=raw['path'],raw_sha256=raw['sha256'])
      a['price_evidence']['readback']['per_channel'][i].update(raw_reference=raw,receipt_reference=rr)
    price=put(root/'prices.json',a['price_evidence']['document']);pub=put(root/'pricepub.json',{});pr=put(root/'price_reader.py',b'# no execution',True)
    au=a['price_evidence']['readback'];au.update(channels_sha256=price['sha256'],publication_sha256=pub['sha256'],reader_sha256=pr['sha256']);audit=put(root/'priceaudit.json',au)
    ex=deepcopy(a['execution_contract']);ex.pop('reference')
    benchmarks={k:put(root/(k+'.json'),{'reference_only':True}) for k in a['benchmark_references']}
    contract=put(root/'contract.json',dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_SOURCE_CONTRACT_V1',execution_contract=ex,benchmark_references=benchmarks,flows_by_lane=a['flows_by_lane'],**w.FLAGS))
    for e in (core.FRACTIONAL_ENGINE,core.WHOLE_ENGINE):put(root/e['path'],(w.ROOT/e['path']).read_bytes(),True)
    roles=dict(channels=price,price_publication=pub,price_reader=pr,price_readback=audit,outer_result=result,outer_coordinator=coord,account_contract=contract)
    return outer,reader,{k:(r['path'],r['sha256']) for k,r in roles.items()}

class Tests(unittest.TestCase):
 def test_pending_before_source_io_and_final_core_pin(self):
    self.assertEqual(w.sha(w.CORE.read_bytes()),w.CORE_SHA)
    pending=deepcopy(w.BOUND);pending['outer_result']=(pending['outer_result'][0],None)
    with patch.object(w,'BOUND',pending),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
      with self.assertRaisesRegex(ValueError,'binding pending'):w.read_inputs()
 def test_project_exact_source_contract_and_no_flow_reinterpretation(self):
    a=fixture();r={k:{'path':'/synthetic/'+k,'sha256':'a'*64} for k in ('channels','price_publication','price_readback','price_reader','account_contract')}
    execution=deepcopy(a['execution_contract']);execution.pop('reference')
    d={'channels':a['price_evidence']['document'],'price_readback':a['price_evidence']['readback'],'account_contract':dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_SOURCE_CONTRACT_V1',execution_contract=execution,benchmark_references=a['benchmark_references'],flows_by_lane=a['flows_by_lane'],**w.FLAGS)}
    before=w.enc(d);out=w.project_inputs(d,r,a['outer_rows']);self.assertEqual(out['execution_contract']['reference'],r['account_contract']);out['flows_by_lane'].clear();self.assertEqual(w.enc(d),before)
    d['account_contract']['account_simulation_performed']=0
    with self.assertRaises(ValueError):w.project_inputs(d,r,a['outer_rows'])
 def test_same_bytes_loading_and_hash_conflict(self):
    with tempfile.TemporaryDirectory() as td:
      p=Path(td)/'source.json';p.write_bytes(b'{"x":1}');r=w.reference(p,w.sha(p.read_bytes()))
      with patch.object(Path,'read_bytes',side_effect=[b'{"x":1}',b'{"x":2}']) as read:self.assertEqual(w.load(r,{}),{'x':1});self.assertEqual(read.call_count,1)
      with self.assertRaises(ValueError):w.load(r,{str(p):'f'*64})
      p.with_name('failure.json').write_text('{}')
      with self.assertRaises(ValueError):w.load(r,{})
 def test_synthetic_createonly_and_postwrite_source_drift(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td);c=staged(root);out=root/'published'
      with patch.object(w,'OUTPUT',out),patch.object(w,'read_inputs',return_value=c),patch.object(w,'resource'),patch.object(w,'coordinator_inventory'):
        result=w.run(execute=True);doc=w.decode(Path(result['path']).read_bytes());self.assertEqual(doc['inputs']['track_count'],16);self.assertFalse(doc['account_simulation_performed'])
        with self.assertRaisesRegex(ValueError,'Create only'):w.run(execute=True)
      c=staged(root);out=root/'drift';save=w.save
      def damaged(name,value,emergency=False):
        result=save(name,value,emergency=emergency)
        if name=='publication.json':Path(next(iter(c['sources']))).write_bytes(b'changed')
        return result
      with patch.object(w,'OUTPUT',out),patch.object(w,'read_inputs',return_value=c),patch.object(w,'resource'),patch.object(w,'coordinator_inventory'),patch.object(w,'save',side_effect=damaged):
        with self.assertRaisesRegex(ValueError,'Source drift'):w.run(execute=True)
      self.assertTrue((out/'inputs.json').exists());self.assertTrue((out/'failure.json').exists())
 def test_unmocked_complete_48_source_loader_project_private_core_and_inventory(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td);outer,reader,bound=physical_sources(root)
      with patch.object(w,'ROOT',root),patch.object(w,'OUTER_ROOT',outer),patch.object(w,'OUTER_READER',Path(reader['path'])),patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',root/'output'),patch.object(w,'resource'):
        c=w.read_inputs();self.assertEqual(len(c['args']['outer_rows']),48)
        result=w.run(execute=True);doc=w.decode(Path(result['path']).read_bytes());self.assertEqual(doc['inputs']['track_count'],16)
        (outer/'unexpected').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError,'inventory drift'):w.coordinator_inventory(c['coordinator_file_inventory'])
 def test_full_origin_envelope_loaded_without_account_or_reader_execution(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td);refs={};reader=root/'reader.py';reader.write_bytes(b'raise AssertionError("do not execute")');refs['reader']=w.reference(reader,w.sha(reader.read_bytes()))
      for role in ('request','raw_result','postcheck','readback'):
        p=root/(role+'.json');p.write_bytes(w.enc({'role':role,'source_hashes':{}}));refs[role]=w.reference(p,w.sha(p.read_bytes()))
      with patch.object(w,'OUTER_READER',reader):
        got=w.load_envelope({'references':refs,'numerical_reuse_references':deepcopy(refs)},{},{})
      self.assertEqual(got['numerical_reuse_evidence']['references'],refs);self.assertEqual(got['raw_result'],{'role':'raw_result','source_hashes':{}})

if __name__=='__main__':unittest.main()
