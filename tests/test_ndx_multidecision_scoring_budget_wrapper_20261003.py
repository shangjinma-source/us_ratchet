from copy import deepcopy
from pathlib import Path
import tempfile,types,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_scoring_budget_20261003 as m
from test_ndx_multidecision_scoring_budget_research import fixture as budget_fixture


def fixture():
    reg,u,decisions=budget_fixture();refs={k:dict(path='/synthetic/'+k+'.json',sha256='a'*64) for k in m.BOUND};refs['rolling_fitter_manifest']=dict(path='/synthetic/rolling.json',sha256='b'*64)
    refs['policy']['sha256']=m.BOUND['policy'][1]
    false=dict(fit_performed=False,point_in_time_verified=False);sources={'/synthetic/source.py':'c'*64}
    h=dict(schema='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1',status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK',rows=[],security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7,original_provenance_and_missing=[{'i':i} for i in range(101)],preserved_evidence_sidecars={k:{'evidence':k} for k in m.SIDECARS},source_hashes=sources,**false)
    channels=[];mdv=dict(schema='CONDITIONAL_MULTIDECISION_LIQUIDITY_INPUTS_V2',status='PREPARED_CONDITIONAL_LIQUIDITY_NOT_ELIGIBILITY',historical_liquidity_qualified=False,historical_pool_eligibility_verified=False,execution_authorized=False,full_inventory=[{k:v[k] for k in ('security_id','issuer_id','ticker')} for v in u],original_provenance_and_missing=deepcopy(h['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(h['preserved_evidence_sidecars']),periods=[],**false)
    for j,d in enumerate(decisions):
        rows=[]
        for q in d['qualifications']:
            row=deepcopy(q['mdv_evidence']);row['reasons']=[];rows.append(row)
        mdv['periods'].append(dict(decision_date=d['cutoff'],rows=rows))
    for i,coordinate in enumerate(u):
        channel=dict(schema='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1',ticker=coordinate['ticker'],decisions=[],score_computed=False,missing_or_blocked_slots_dropped=False,unequal_window_pooling_allowed=False,**false);coverage=[]
        for j,d in enumerate(decisions):
            good=i<8;windows=[dict(status='CONDITIONAL_NUMERIC_WINDOW' if good else 'BLOCKED_WINDOW',blocked_price_slots=[] if good else [{'missing':'date'}]) for _ in range(13)]
            channel['decisions'].append(dict(cutoff=d['cutoff'],required_price_dates=d['scoring_price_dates'],windows=windows,window_count=13,complete_thirteen_window_numeric_supply=good))
            coverage.append(dict(cutoff=d['cutoff'],complete_thirteen_window_numeric_supply=good,blocked_window_count=0 if good else 13))
        channel['content_sha256']=m.sha(m.encoded(channel));channels.append(channel)
        h['rows'].append(dict(index=i,coordinate=coordinate,channel_reference=dict(path=f'/synthetic/channel_{i:03d}.json',sha256='d'*64),decision_coverage=coverage))
    ha=dict(schema='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2',status='PASS',index_reference=refs['history_index'],publication_reference=refs['history_publication'],reader_sha256=refs['history_reader']['sha256'],rows=[dict(deepcopy(r),inspection=dict(status='PASS',ticker=r['coordinate']['ticker'],window_count=78)) for r in h['rows']],security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7,**false)
    o=dict(schema='ORIGINAL_EIGHT_SCORING_INPUTS_DOCUMENT_V1',status='PUBLISHED_FIXED_DAILY_WEIGHT_RETURNS_PENDING_INDEPENDENT_READBACK',source_hashes=sources,scoring_inputs=dict(schema='ORIGINAL_EIGHT_FIXED_DAILY_WEIGHT_SCORING_INPUTS_V1',entry_fee_applied=False,score_computed=False,decisions=[dict(cutoff=d['cutoff'],price_dates=d['scoring_price_dates']) for d in decisions],**false),**false)
    oa=dict(schema='ORIGINAL_EIGHT_SCORING_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',inputs_reference=refs['original8_inputs'],publication_reference=refs['original8_publication'],reader_sha256=refs['original8_reader']['sha256'],arithmetic=dict(status='PASS',return_slot_count=3024,window_count=78),**false)
    target=dict(schema='MULTIDECISION_TARGET_SCORING_INPUTS_V1',modes=[dict(mode=mode,decisions=[dict(cutoff=d['cutoff'],required_price_dates=d['scoring_price_dates'],windows=[dict(status='CONDITIONAL_NUMERIC_WINDOW' if index else 'BLOCKED_WINDOW') for _ in range(13)],window_count=13,partial_window_pooling_allowed=False,scoring_allowed=False,complete_thirteen_window_numeric_supply=bool(index)) for d in decisions]) for index,mode in enumerate(m.MODES)])
    ti=dict(schema='MULTIDECISION_TARGET_SCORING_INPUTS_DOCUMENT_V1',status='PUBLISHED_CONDITIONAL_INPUTS_PENDING_INDEPENDENT_READBACK',target_inputs_reference=refs['target_inputs'],source_hashes=sources,**false)
    ta=dict(schema='MULTIDECISION_TARGET_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=refs['target_reader']['sha256'],index_reference=refs['target_index'],publication_reference=refs['target_publication'],source_hashes={refs['target_inputs']['path']:refs['target_inputs']['sha256']},**false)
    baseline={f'/synthetic/{i}.py':'e'*64 for i in range(25)}
    docs=dict(policy=reg,history_index=h,history_audit=ha,mdv_result=mdv,mdv_report=dict(schema='SAVED_MULTIDECISION_LIQUIDITY_PROBE_V2',status='PASS_DRAFT_DIAGNOSTIC_ONLY',result_reference=refs['mdv_result'],prepare_calls=1,independently_checked_security_periods=462,decision_contract_registered=False,selection_performed=False,**false),original8_inputs=o,original8_audit=oa,target_index=ti,target_inputs=target,target_audit=ta,fitter_container=dict(plan=dict(fitter_source_hashes=baseline)),mapping=dict(source_references={k:refs[k] for k in ('history_index','mdv_result')},fitter_source_hashes=baseline),rolling_fitter_manifest={})
    for role,parent,key,refkey,schema in [('history',h,'index_reference','history_index','MULTIDECISION_SCORING_HISTORY_PUBLICATION_V1'),('original8',o,'inputs_reference','original8_inputs','ORIGINAL_EIGHT_SCORING_INPUTS_PUBLICATION_V1'),('target',ti,'index_reference','target_index','MULTIDECISION_TARGET_SCORING_INPUTS_PUBLICATION_V1')]:
        docs[role+'_publication']=dict(schema=schema,status=parent['status'],source_hashes=sources,**false);docs[role+'_publication'][key]=refs[refkey]
    docs['target_publication']['target_inputs_reference']=refs['target_inputs']
    return docs,refs,channels


class Tests(unittest.TestCase):
    def test_projection_complete_and_real_shape(self):
        d,r,c=fixture();before=deepcopy(d);a=m.project_inputs(d,r,iter(c))
        self.assertEqual(d,before);self.assertEqual(len(a['universe']),77)
        self.assertEqual([sum(q['history_13_complete'] for q in x['qualifications']) for x in a['decisions']],[8]*6)
        self.assertEqual(a['decisions'][0]['incumbent_fee_reference']['json_pointer'],'/scoring_inputs/normalized_scoring_weights')
        self.assertEqual([x['complete_thirteen_windows'] for x in a['decisions'][0]['mode_sources']],[False,True])
        for mutation in ('date','coordinate','count','missing','extra','source'):
            dd,rr,cc=deepcopy((d,r,c))
            if mutation=='date':cc[76]['decisions'][0]['required_price_dates'].pop();cc[76]['content_sha256']=m.sha(m.encoded({k:v for k,v in cc[76].items() if k!='content_sha256'}))
            if mutation=='coordinate':dd['mdv_result']['periods'][5]['rows'][76]['coordinate']['issuer_id']='foreign'
            if mutation=='count':dd['mdv_report']['prepare_calls']=True
            if mutation=='missing':cc.pop()
            if mutation=='extra':cc.append(cc[0])
            if mutation=='source':dd['target_audit']['source_hashes'][r['target_inputs']['path']]='f'*64
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):m.project_inputs(dd,rr,iter(cc))
    def test_private_math_and_plan_only_synthetic(self):
        d,r,c=fixture();sources={};core=m.private_budget(sources);a=m.project_inputs(d,r,c);out=core.plan_multidecision_scoring_budget(**a);m.validate_result(out,a)
        self.assertEqual(len(out['rows']),6);self.assertIn(str(m.CORE),sources)
    def test_pending_before_io_and_conflict(self):
        with patch.object(m,'ROLLING_MANIFEST_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaises(ValueError):m.load_inputs()
        with self.assertRaises(ValueError):m.merge({str(Path('x').resolve()):'a'*64},'x','b'*64)
    def test_saved_outputs_and_publication_time_drift(self):
        d,r,c=fixture();a=m.project_inputs(d,r,c);core=m.private_budget({})
        for drift in (False,True):
            with self.subTest(drift=drift),tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'),patch.object(m,'load_inputs',return_value=(d,r,{},a,core)),patch.object(m,'space'):
                original=m.save
                def save(path,value,failure=False):
                    ref=original(path,value,failure)
                    if drift and path.name=='publication.json':(m.OUTPUT/'plan.json').write_bytes(b'changed')
                    return ref
                with patch.object(m,'save',side_effect=save):
                    if drift:
                        with self.assertRaisesRegex(ValueError,'Final output drift'):m.run(execute=True)
                        self.assertTrue((m.OUTPUT/'failure.json').exists())
                    else:
                        ref=m.run(execute=True);doc=m.loads(Path(ref['path']).read_bytes())
                        self.assertEqual(len(doc['original_provenance_and_missing']),101)
                        self.assertEqual(len(doc['preserved_evidence_sidecars']),7)
                        self.assertFalse(doc['score_dispatch_authorized'])
                        self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','raw_plan.json','plan.json','publication.json'})

    def test_return_persisted_before_incomplete_or_source_failure(self):
        d,r,c=fixture();a=m.project_inputs(d,r,c);core=m.private_budget({});original=core.plan_multidecision_scoring_budget(**a)
        for kind in ('incomplete','postguard'):
            plan=deepcopy(original)
            if kind=='incomplete':
                plan['rows'][0]['sampling']['complete']=False
                plan['content_sha256']=m.sha(m.encoded({k:v for k,v in plan.items() if k!='content_sha256'}))
            stub=types.SimpleNamespace(plan_multidecision_scoring_budget=lambda **kw:plan)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'),patch.object(m,'load_inputs',return_value=(d,r,{},a,stub)),patch.object(m,'space'),patch.object(m,'guard',side_effect=[None,ValueError('source changed')] if kind=='postguard' else None):
                with self.assertRaises(ValueError):m.run(execute=True)
                self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','raw_plan.json','failure.json'})
                raw=m.loads((m.OUTPUT/'raw_plan.json').read_bytes());self.assertEqual(raw['plan'],plan)
                self.assertFalse(raw['execution_authorized']);self.assertEqual(raw['input_references'],r)
                failed=m.loads((m.OUTPUT/'failure.json').read_bytes())
                self.assertEqual(failed['saved_references'][-1]['sha256'],m.sha((m.OUTPUT/'raw_plan.json').read_bytes()))

    def test_publish_failure_and_no_retry(self):
        d,r,c=fixture();a=m.project_inputs(d,r,c)
        core=types.SimpleNamespace(plan_multidecision_scoring_budget=lambda **kw: (_ for _ in ()).throw(RuntimeError('synthetic planning failure')))
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'),patch.object(m,'load_inputs',return_value=(d,r,{},a,core)),patch.object(m,'space'),patch.object(m,'guard'):
            with self.assertRaisesRegex(RuntimeError,'synthetic'):m.run(execute=True)
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','failure.json'})
            with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()
