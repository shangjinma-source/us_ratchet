from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
import tempfile
from contextlib import ExitStack
from unittest.mock import patch
from test_ndx_outer_lane_refit_evidence_research import fixture,evidence
from test_ndx_multidecision_selected_refit_inputs_research import fixture as source_fixture
from backtest import ndx_outer_lane_refit_evidence_research as prep
from backtest import ndx_multidecision_selected_refit_inputs_research as original_prepare

spec=importlib.util.spec_from_file_location('outer_reader',Path(__file__).resolve().parents[1]/'scripts/ndx_outer_lane_refit_independent_readback_20261003.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.prepared,cls.contract=fixture();cls.out=prep.resolve_adjacent_refit_priors(prepared=cls.prepared,prior_evidence=[],receipt_contract=cls.contract)
  cls.request=cls.out['rows'][4]['outer_request'];cls.e=evidence(cls.request,cls.prepared['fitter_contract_preserved'],cls.contract)
  cls.arithmetic=staticmethod(m.private_inspector({}))

 def source_args(self):
  src=source_fixture()
  return dict(selection=src['selection']['document'],history=src['history']['document'],channels={b['coordinate']['security_id']:b for b in src['channel_bindings']},fitter=self.prepared['fitter_contract_preserved'],refs=dict(selection=src['selection']['reference'],history=src['history']['reference'],fitter=self.prepared['fitter_contract_preserved']['reference']))

 def test_source_matrix_and_source_slots_independently_rebuilt(self):
  args=self.source_args();out=m.inspect_request(self.request,**args)
  self.assertEqual(out['coordinate_index'],4);self.assertEqual(out['original_source_slots_verified'],504)
  for key in ('matrix','source','identity'):
   r=deepcopy(self.request)
   if key=='matrix':r['fit_matrix']['returns'][0][0]+=.001
   elif key=='source':r['source_slot_evidence'][0]['return_index_start']+=1
   else:r['location_identity']['lane']='FOREIGN'
   r['content_sha256']=m.sha(m.enc({k:v for k,v in r.items() if k!='content_sha256'}))
   with self.subTest(key=key),self.assertRaises(ValueError):m.inspect_request(r,**args)

 def test_actual_independent_arithmetic_no_producer_or_fit(self):
  e=deepcopy(self.e);args=dict(request=e['request'],raw=e['raw_result'],post=e['postcheck'],refs=e['references'],fitter=self.prepared['fitter_contract_preserved'],arithmetic=self.arithmetic)
  result=m.inspect_envelope(**args);self.assertTrue(result['declared_risks_passed']);self.assertFalse(result['fit_performed'])
  e['raw_result']['result']['fit_data_sha256']='0'*64
  with self.assertRaises(ValueError):m.inspect_envelope(**args)

 def test_invocation_and_authority_types(self):
  for field,value in (('current_location_call_invoked',1),('current_location_returned_call_count',True),('promotion_allowed',0)):
   e=deepcopy(self.e);e['postcheck'][field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):m.inspect_envelope(request=e['request'],raw=e['raw_result'],post=e['postcheck'],refs=e['references'],fitter=self.prepared['fitter_contract_preserved'],arithmetic=self.arithmetic)

 def test_module_has_no_producer_invocation(self):
  text=m.SOURCE.read_text(encoding='utf8')
  self.assertNotIn('inspect_return(',text);self.assertNotIn('refit_dynamic_cutoff_weights(',text)

 def physical(self,root):
  parent=root/'worker';output=root/'reader';e=deepcopy(self.e);q=e['request'];location=parent/'locations'/q['location_id'];numeric=parent/'numerical'/q['numerical_task_id'];location.mkdir(parents=True);numeric.mkdir(parents=True)
  requestref=m.save(location/'request.json',q);e['references']['request']=requestref
  args=self.source_args();inputrefs=args['refs'];inventory=[{k:r[k] for k in ('status','numerical_task_id','location_id')}|dict(coordinate_index=i,coordinate=[r['cutoff'],r['fx_mode'],r['lane']]) for i,r in enumerate(self.out['rows'])]
  declared={requestref['path']:requestref['sha256']}
  raw=e['raw_result'];raw.update(request_reference=requestref,source_hashes=declared,input_references=inputrefs,prior_evidence_references=[],coordinate_inventory=inventory)
  started=dict(schema='OUTER_LANE_CUTOFF_REFIT_STARTED_V1',request_reference=requestref,numerical_task_id=q['numerical_task_id'],location_id=q['location_id'],source_hashes=declared,input_references=inputrefs,prior_evidence_references=[],coordinate_inventory=inventory,runtime_versions=raw['runtime_versions'],worker_environment=raw['worker_environment'],**m.FLAGS)
  m.save(numeric/'started.json',started);rawref=m.save(numeric/'raw_result.json',raw)
  post=e['postcheck'];post.update(request_reference=requestref,raw_result_reference=rawref,source_hashes=declared|{rawref['path']:rawref['sha256']},input_references=inputrefs,prior_evidence_references=[],coordinate_inventory=inventory,saved_result_inspection=self.arithmetic(request=q,result=raw['result'],fitter_contract=args['fitter']))
  postref=m.save(location/'postcheck.json',post)
  context=({'selection':{'result':args['selection']},'history':args['history']},args['channels'],args['fitter'],{})
  return parent,output,postref,context,numeric

 def test_physical_success_no_retry_and_report_roles(self):
  with tempfile.TemporaryDirectory() as td:
   parent,out,ref,ctx,numeric=self.physical(Path(td))
   with patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',out),patch.object(m,'PRODUCER_SHA','f'*64),patch.object(m,'load_inputs',return_value=ctx):
    result=m.readback(ref,execute=True);report=m.loads(Path(result['path']).read_bytes())
    self.assertEqual(report['status'],'PASS');self.assertTrue(report['prior_eligible']);self.assertEqual(report['reader_reference'],m.reference(m.SOURCE,m.LOADED))
    with self.assertRaisesRegex(ValueError,'retry'):m.readback(ref,execute=True)

 def test_final_source_drift_failure_and_extra_numeric_file(self):
  with tempfile.TemporaryDirectory() as td:
   parent,out,ref,ctx,numeric=self.physical(Path(td));real=m.save
   def drift(path,value):
    result=real(path,value)
    if path.name=='independent_readback.json':(numeric/'started.json').write_bytes(b'changed')
    return result
   with patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',out),patch.object(m,'PRODUCER_SHA','f'*64),patch.object(m,'load_inputs',return_value=ctx),patch.object(m,'save',side_effect=drift):
    with self.assertRaisesRegex(ValueError,'Source drift'):m.readback(ref,execute=True)
   self.assertTrue((out/Path(ref['path']).parent.name/'failure.json').exists())
  with tempfile.TemporaryDirectory() as td:
   parent,out,ref,ctx,numeric=self.physical(Path(td));(numeric/'unserializable_return.bin').write_bytes(b'not declared')
   with patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',out),patch.object(m,'PRODUCER_SHA','f'*64),patch.object(m,'load_inputs',return_value=ctx):
    with self.assertRaisesRegex(ValueError,'inventory'):m.readback(ref,execute=True)

 def test_future_producer_and_missing_external_anchor_before_io(self):
  with patch.object(m,'take',side_effect=AssertionError('IO must not occur')):
   with self.assertRaises(ValueError):m.readback(None,execute=True)
   with patch.object(m,'PRODUCER_SHA',None),self.assertRaises(ValueError):m.readback(m.reference(m.PARENT/'locations'/('a'*64)/'postcheck.json','b'*64),execute=True)

 def test_next_prior_precision_is_not_risk_failure(self):
  e=deepcopy(self.e);body=e['raw_result']['result'];sid=next(iter(body['targets']));body['targets'][sid]['target_weight']+=5e-11
  e['postcheck'].update(outcome='VALIDATION_FAILURE',error={'type':'ValueError','message':'prior simplex'})
  result=m.inspect_envelope(request=e['request'],raw=e['raw_result'],post=e['postcheck'],refs=e['references'],fitter=self.prepared['fitter_contract_preserved'],arithmetic=self.arithmetic)
  self.assertTrue(result['declared_risks_passed']);self.assertFalse(result['next_prior_simplex_eligible'])
  e['postcheck']['outcome']='REFIT_RISK_FAILED'
  with self.assertRaises(ValueError):m.inspect_envelope(request=e['request'],raw=e['raw_result'],post=e['postcheck'],refs=e['references'],fitter=self.prepared['fitter_contract_preserved'],arithmetic=self.arithmetic)

 def test_full_unmocked_loader_and_readback_closed_synthetic_sources(self):
  with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
   root=Path(td);roles={k:k+'.json' for k in m.ROLE_PATHS};producer=root/'worker.py';producer.write_bytes(b'# synthetic worker source\n')
   def put(name,value):return m.save(root/name,value)
   def code(name):
    path=root/name;path.write_bytes(b'# synthetic declared reader\n');return m.reference(path,m.filehash(path))
   refs={};args=source_fixture();fitter=deepcopy(self.prepared['fitter_contract_preserved']);sourcehash={}
   for name,h in original_prepare.FITTER_CODES.items():sourcehash[str(m.ROOT/'backtest'/name)]=h
   for i in range(22):r=code('fitter_'+str(i)+'.py');sourcehash[r['path']]=r['sha256']
   fitter['source_hashes']=sourcehash;fitter['fitter_source_fingerprint']=m.sha(m.enc(sourcehash));fitter['entrypoint_reference']=m.reference(m.ROOT/'backtest/ndx_dynamic_cutoff_refit_v2_research.py',original_prepare.FITTER_CODES['ndx_dynamic_cutoff_refit_v2_research.py']);fitter.pop('reference')
   refs['fitter']=put(roles['fitter'],fitter);fitter['reference']=refs['fitter'];args['fitter_contract']=fitter
   for role in ('selection_reader','history_reader'):refs[role]=code(roles[role])
   bindings={b['coordinate']['security_id']:b for b in args['channel_bindings']};hi=args['history']['document'];ha=args['history']['readback'];hs={}
   for i,(r,a) in enumerate(zip(hi['rows'],ha['rows'])):
    sid=r['coordinate']['security_id'];body=bindings[sid]['channel'] if sid in bindings else {'ticker':r['coordinate']['ticker'],'unused_synthetic':True}
    cr=put('channel_'+str(i)+'.json',body);r['channel_reference']=cr;a['channel_reference']=cr;hs[cr['path']]=cr['sha256']
    if sid in bindings:bindings[sid]['reference']=cr
   hi['source_hashes']=deepcopy(hs);refs['history']=put(roles['history'],hi)
   hs.update({refs[k]['path']:refs[k]['sha256'] for k in ('history','history_reader')});ha.update(index_reference=refs['history'],reader_sha256=refs['history_reader']['sha256'],source_hashes=hs)
   refs['history_audit']=put(roles['history_audit'],ha)
   args['history'].update(reference=refs['history'],readback_reference=refs['history_audit'],reader_reference=refs['history_reader'])
   refs['selection']=put(roles['selection'],dict(schema='REGISTERED_SCORING_SELECTION_RAW_V1',result=args['selection']['document']))
   si=dict(schema='REGISTERED_SCORING_SELECTION_INDEX_V1',selection_reference=refs['selection'],source_hashes={})
   refs['selection_index']=put(roles['selection_index'],si)
   sp=dict(schema='REGISTERED_SCORING_SELECTION_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_SELECTION_ONLY',index_reference=refs['selection_index'],raw_selection_reference=refs['selection'],source_hashes={})
   refs['selection_publication']=put(roles['selection_publication'],sp)
   sa=args['selection']['readback'];sa.update(index_reference=refs['selection_index'],publication_reference=refs['selection_publication'],raw_selection_reference=refs['selection'],reader_sha256=refs['selection_reader']['sha256'],source_hashes={refs[k]['path']:refs[k]['sha256'] for k in ('selection','selection_reader')})
   refs['selection_audit']=put(roles['selection_audit'],sa);args['selection'].update(reference=refs['selection'],readback_reference=refs['selection_audit'],reader_reference=refs['selection_reader'])
   contract=dict(schema='OUTER_LANE_RECEIPT_INTERFACE_CONTRACT_V1',reader_reference=m.reference(m.SOURCE,m.LOADED),source_bytes_authenticated=False)
   refs['receipt_contract']=put('receipt.json',contract);refs['outer_reader']=contract['reader_reference']
   codes={k:(str(m.ROOT/v[0]),v[1]) for k,v in m.CODES.items()}
   parent=root/'attempts';output=root/'audits'
   for key,value in dict(ROOT=root,ROLE_PATHS=roles,FIXED={},PRODUCER=producer,PRODUCER_SHA=m.filehash(producer),CODES=codes,PARENT=parent,OUTPUT=output).items():stack.enter_context(patch.object(m,key,value))
   docs,channels,loaded_fitter,common=m.load_inputs(refs)
   self.assertEqual(len(channels),77);self.assertEqual(len(loaded_fitter['source_hashes']),25)
   p=original_prepare.prepare_selected_cutoff_refit_inputs(**args);out=prep.resolve_adjacent_refit_priors(prepared=p,prior_evidence=[],receipt_contract=contract);q=out['rows'][4]['outer_request'];e=evidence(q,fitter,contract)
   location=parent/'locations'/q['location_id'];numeric=parent/'numerical'/q['numerical_task_id'];location.mkdir(parents=True);numeric.mkdir(parents=True)
   rr=m.save(location/'request.json',q);base=deepcopy(common);base[rr['path']]=rr['sha256']
   inventory=[{k:r[k] for k in ('status','numerical_task_id','location_id')}|dict(coordinate_index=i,coordinate=[r['cutoff'],r['fx_mode'],r['lane']]) for i,r in enumerate(out['rows'])]
   raw=e['raw_result'];raw.update(request_reference=rr,source_hashes=base,input_references=refs,prior_evidence_references=[],coordinate_inventory=inventory)
   started=dict(schema='OUTER_LANE_CUTOFF_REFIT_STARTED_V1',request_reference=rr,numerical_task_id=q['numerical_task_id'],location_id=q['location_id'],source_hashes=base,input_references=refs,prior_evidence_references=[],coordinate_inventory=inventory,runtime_versions=raw['runtime_versions'],worker_environment=raw['worker_environment'],**m.FLAGS)
   m.save(numeric/'started.json',started);rawref=m.save(numeric/'raw_result.json',raw)
   post=e['postcheck'];post.update(request_reference=rr,raw_result_reference=rawref,source_hashes=base|{rawref['path']:rawref['sha256']},input_references=refs,prior_evidence_references=[],coordinate_inventory=inventory,saved_result_inspection=self.arithmetic(request=q,result=raw['result'],fitter_contract=fitter))
   postref=m.save(location/'postcheck.json',post);auditref=m.readback(postref,execute=True)
   report=m.loads(Path(auditref['path']).read_bytes());self.assertEqual(report['status'],'PASS');self.assertGreater(len(report['source_hashes']),110)
   bad=deepcopy(sa);bad['publication_reference']=refs['selection_index'];wrongrefs=deepcopy(refs);wrongpath=Path(refs['selection_audit']['path']);wrongpath.write_bytes(m.enc(bad));wrongrefs['selection_audit']['sha256']=m.filehash(wrongpath)
   with self.assertRaisesRegex(ValueError,'publication audit'):m.load_inputs(wrongrefs)
   wrongpath.write_bytes(m.enc(sa));contract=deepcopy(contract);contract['reader_reference']['sha256']='0'*64;cp=Path(refs['receipt_contract']['path']);cp.write_bytes(m.enc(contract));wrongrefs=deepcopy(refs);wrongrefs['receipt_contract']['sha256']=m.filehash(cp)
   with self.assertRaisesRegex(ValueError,'Contract fixes'):m.load_inputs(wrongrefs)


if __name__=='__main__':unittest.main()
