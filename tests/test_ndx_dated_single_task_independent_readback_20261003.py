"""Synthetic dated envelopes and complete metadata; no runner/fitter imports."""
from copy import deepcopy
from pathlib import Path
from datetime import date,timedelta
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_dated_single_task_independent_readback_20261003 as module
from backtest import ndx_dated_fixed_task_preparation_research as preparation
from test_ndx_dated_fixed_task_preparation_research import fixture as preparation_fixture
from test_ndx_single_task_raw_readback_research import case as numerical_case
def documents():
    a=preparation_fixture();r=module.ref
    # Rewrite only the externally declared fixture references, and recompute its
    # original metadata IDs before materializing the synthetic dated batch.
    a['training_reference']=r('panel');a['prior_preparation_reference']=r('prior_preparation');a['original_plan_reference']=r('plan')
    old=a['prior_preparation'];plan=a['original_lazy_plan'];old['materialized']['plan_reference']=r('plan')
    for c in old['materialized']['combinations']:
        for t in c['tasks']:
            t['location_identity']['plan_reference']=r('plan');t['location_id']=preparation.digest(t['location_identity'])
    out=preparation.prepare_dated_tasks(**a);panel=a['training_panel'];flags=dict.fromkeys(('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted'),False)
    q=dict(schema='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_DOCUMENT_V1',materialized=out,source_hashes={},training_fit_payload=panel['fit_payload'],complete_observed_provenance_and_missing=panel['original_provenance_and_missing'],preserved_evidence_sidecars=panel['preserved_evidence_sidecars'],original_coordinate_evidence=panel['original_coordinate_evidence'],evaluation_references=panel['evaluation_references'],late_pool_and_composition_selection=True,**flags)
    pub=dict(schema='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_PUBLICATION_V1',status='PUBLISHED_NEW_DATED_TASK_INPUTS_NOT_FITTED',preparation_reference=r('preparation'),source_hashes={})
    audit=dict(schema='DATED_FIXED_TASK_PREPARATION_INDEPENDENT_READBACK_V1',status='PASS',preparation_sha256=r('preparation')['sha256'],publication_sha256=r('publication')['sha256'],reader_sha256=r('audit_reader')['sha256'],combination_count=544,materialized_task_count=1632,new_numerical_ids=1632,new_location_ids=1632,old_id_intersection=0,original_provenance_count=101,preserved_sidecar_count=7,new_cutoff_completed_task_count=0)
    return dict(preparation=q,publication=pub,audit=audit,panel=dict(schema='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1',panel=panel,**flags),plan=dict(plan=plan),prior_preparation=old),plan['fitter_source_hashes']

def case():
    c=numerical_case();days=[];day=date(2026,3,20)
    while len(days)<126:
        if day.weekday()<5:days.append(day.isoformat())
        day-=timedelta(days=1)
    days.reverse();combo=c['combination'];combo['fit_matrix']['dates']=days;combo['fit_data_sha256']=module.digest(combo['fit_matrix'])
    identity=c['task']['numerical_identity'];identity.update(cutoff=days[-1],fit_data_sha256=combo['fit_data_sha256']);c['task']['numerical_task_id']=module.digest(identity)
    c['fitted'].update(cutoff=days[-1],fit_start=days[0],fit_end=days[-1],fit_data_sha256=combo['fit_data_sha256'])
    state=dict(task=c['task'],combination_identity=combo,input_references={},task_reference={'synthetic':'task'},source_hashes={},runtime=module.runtime())
    started=dict(schema='DATED_SINGLE_TASK_STARTED_V1',**deepcopy(state),planned_operation_counts=module.counts(c['task']),**dict.fromkeys(module.FALSE,False));sr=dict(path='started',sha256='a'*64)
    raw=dict(schema='DATED_SINGLE_TASK_RAW_V1',started_reference=sr,numerical_task_id=c['task']['numerical_task_id'],status='FIT_RETURNED',operation_counts=module.counts(c['task']),fitted=c['fitted'],error=None,returned_fit_count=1,internal_optimizer_call_count=None,source_hashes={},runtime=state['runtime'],**dict.fromkeys(module.FALSE,False))
    return dict(started=started,raw=raw,state=state,started_reference=sr,numerical_sources=c['numerical_sources'])

class Tests(unittest.TestCase):
    def test_all_new_contracts(self):
        docs,_=documents();tasks,combos,sources=module.validate_documents(docs)
        self.assertEqual((len(tasks),len(combos),len(sources)),(1632,544,25))
        for mode in ('prior','location','future','sidecar','count'):
            bad=deepcopy(docs);m=bad['preparation']['materialized'];t=m['combinations'][-1]['tasks'][-1]
            if mode=='prior':t['numerical_identity']['requested_previous_target_weights']={}
            elif mode=='location':t['location_identity']['rank']=True;t['location_id']=module.digest(t['location_identity'])
            elif mode=='future':bad['panel']['panel']['fit_payload']['returns']['index'][-1]='2026-03-23T00:00:00'
            elif mode=='sidecar':bad['preparation']['preserved_evidence_sidecars'].popitem()
            else:m['new_fit_count']=False
            m['content_sha256']=module.digest({k:v for k,v in m.items() if k!='content_sha256'})
            with self.subTest(mode=mode),self.assertRaises(ValueError):module.validate_documents(bad)

    def test_equal_five_risks_and_exact_envelopes(self):
        args=case();self.assertEqual(module.inspect_envelopes(**args)['status'],'FITTED_FIVE_RISKS_PASSED')
        for mode in ('counts','authority','raw','source'):
            bad=deepcopy(args)
            if mode=='counts':bad['raw']['returned_fit_count']=True
            elif mode=='authority':bad['started']['historical_pool_eligibility_verified']=True
            elif mode=='raw':bad['raw']['fitted']['targets'][next(iter(bad['raw']['fitted']['targets']))]['target_weight']=.9
            else:bad['raw']['fitted']['source_hashes']={}
            with self.subTest(mode=mode),self.assertRaises(ValueError):module.inspect_envelopes(**bad)

    def test_exception_and_four_statuses(self):
        a=case();a['raw'].update(status='FIT_EXCEPTION',fitted=None,error=dict(type='ArithmeticError',message='no return'),returned_fit_count=0)
        detail=module.inspect_envelopes(**a);rr=dict(path='raw',sha256='b'*64);tid=a['state']['task']['numerical_task_id']
        p=dict(schema='DATED_SINGLE_TASK_POSTCHECK_V1',status=detail['status'],started_reference=a['started_reference'],raw_reference=rr,numerical_task_id=tid,checks=None,error=detail['error'],**dict.fromkeys(module.FALSE,False))
        self.assertEqual(module.inspect_postcheck(p,a['started_reference'],rr,tid,detail),'NUMERICAL_EXCEPTION')
        p.update(status='VALIDATION_FAILURE_RECORDED',error=dict(type='ValueError',message='drift'));self.assertEqual(module.inspect_postcheck(p,a['started_reference'],rr,tid,detail),'VALIDATION_FAILURE')
        for passed in (True,False):
            d=dict(status='FITTED_FIVE_RISKS_PASSED' if passed else 'FITTED_FIVE_RISKS_FAILED',checks={'risk':passed})
            p.update(status='ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK' if passed else 'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK',checks=d['checks'],error=None)
            self.assertEqual(module.inspect_postcheck(p,a['started_reference'],rr,tid,d),'RISK_PASSED' if passed else 'RISK_FAILED')

    def test_external_anchor_and_one_publication(self):
        a=case();tid=a['state']['task']['numerical_task_id']
        with tempfile.TemporaryDirectory() as folder,patch.object(module,'OUTPUT_ROOT',Path(folder)):
            root=Path(folder)/tid;root.mkdir();refs={}
            blob=module.codec.pretty(a['started']);(root/'started.json').write_bytes(blob);a['started_reference']=dict(path=str(root/'started.json'),sha256=module.codec.sha(blob));a['raw']['started_reference']=a['started_reference']
            blob=module.codec.pretty(a['raw']);(root/'raw.json').write_bytes(blob);rr=dict(path=str(root/'raw.json'),sha256=module.codec.sha(blob))
            detail=module.inspect_envelopes(**a);post=dict(schema='DATED_SINGLE_TASK_POSTCHECK_V1',status='ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK',started_reference=a['started_reference'],raw_reference=rr,numerical_task_id=tid,checks=detail['checks'],error=None,**dict.fromkeys(module.FALSE,False))
            blob=module.codec.pretty(post);(root/'postcheck.json').write_bytes(blob);pr=dict(path=str(root/'postcheck.json'),sha256=module.codec.sha(blob))
            with patch.object(module,'expected_state',return_value=(a['state'],dict(numerical=a['numerical_sources'],denominator=6222659648236112670))),patch.object(module,'guard'):
                with self.assertRaises(ValueError):module.readback(tid,dict(pr,sha256='0'*64),common={})
                out=module.readback(tid,pr,common={});v=module.codec.loads(Path(out['path']).read_bytes());self.assertEqual(v['attempt_outcome'],'RISK_PASSED');self.assertEqual(v['externally_completed_task_count'],0)
                with self.assertRaises(ValueError):module.readback(tid,pr,common={})

    def test_unissued_common_and_source_conflict(self):
        with self.assertRaises(ValueError):module.expected_state('a'*64,dict(ordered_task_ids=['a'*64]))
        with self.assertRaises(ValueError):module.merge({'x':'a'},{'x':'b'})

if __name__=='__main__':unittest.main()


