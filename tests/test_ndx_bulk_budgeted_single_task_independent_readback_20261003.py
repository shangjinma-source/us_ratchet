"""Only synthetic metadata/envelopes and temporary publication; never fit."""
from copy import deepcopy
from datetime import date,timedelta
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_bulk_budgeted_single_task_independent_readback_20261003 as module
from scripts import bulk_all_k_plan_20261003 as planner
from backtest.ndx_issuer_combination_index_research import IssuerCombinationIndex
spec=importlib.util.spec_from_file_location('fitfixture',Path(__file__).with_name('test_ndx_single_task_raw_readback_research.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

def documents():
    groups=[(f'I{i:03}',[f'S{i:03}']+(['ALT'] if i==0 else [])) for i in range(76)]
    index=IssuerCombinationIndex(groups);numerical={str(Path(f'synthetic_source_{i}.py').resolve()):'a'*64 for i in range(25)}
    plan=planner.prepare_lazy_plan(groups=groups,panel_reference=module.ref('panel'),panel_audit_reference=dict(path=str(Path('panel_audit.md').resolve()),sha256='f'*64),
        decision_cutoff='2026-09-21',parameters=module.PARAMETERS,fitter_source_hashes=numerical,previous_target_weights=None)
    rows=sorted([dict(security_id=s,issuer_id=i,ticker='T'+s,risk_chain='R'+i) for i,ss in groups for s in ss],key=lambda r:r['security_id']);columns=sorted(r['ticker'] for r in rows)
    days=[];day=date(2026,9,21)
    while len(days)<126:
        if day.weekday()<5:days.append(day.isoformat())
        day-=timedelta(days=1)
    days.reverse();by={r['security_id']:r for r in rows};fields=list(rows[0]);gaps=[dict(ticker=str(i)) for i in range(101)]
    flags=dict.fromkeys(('point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','fit_performed'),False)
    panel=dict(schema='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1',cutoff=days[-1],panel_content_sha256='b'*64,observed_provenance_and_missing=gaps,
        returns=dict(type='dataframe',index_kind='DatetimeIndex',index=[d+'T00:00:00' for d in days],columns=columns,dtypes=['float64']*77,data=[[.01]*77 for _ in days]),
        universe=dict(type='dataframe',index_kind='RangeIndex',index=list(range(77)),columns=fields,dtypes=['object']*4,data=[[r[f] for f in fields] for r in rows]),**flags)
    paneldoc=dict(schema='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1',panel=panel,**flags,**{k:[] for k in module.SIDECARS})
    sidecars={key:dict(module.ref('panel'),json_pointer='/'+key) for key in module.SIDECARS}
    combos=[];positions=[];ids=[]
    ctx=plan['context']
    for k in range(4,21):
        for rank in range(32):
            prefix=list(index.unrank(k,rank));order=sorted(prefix);selected={s:{f:by[s][f] for f in ('ticker','issuer_id','risk_chain')} for s in order}
            matrix=dict(dates=days,tickers=[by[s]['ticker'] for s in order],returns=[[.01]*k for _ in days]);sha=module.digest(matrix)
            pos=dict(k=k,rank=rank,prefix_security_ids=prefix,selection_kind='STRATIFIED_RANK',proposal_index=len(positions));positions.append(pos)
            tasks=[];stop=min(1000,index.count(k));shard=module.digest(dict(ctx,k=k,start=0,stop=stop))
            for specidx,spec in enumerate(module.SPECS):
                identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=days[-1],holding_count=k,selected=selected,weight_spec=spec,parameters=module.PARAMETERS,
                    requested_previous_target_weights=None,fit_data_sha256=sha,fitter_source_fingerprint=module.digest(numerical))
                location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=module.ref('plan'),plan_id=plan['plan_id'],shard_id=shard,
                    order_version=ctx['order_version'],group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=specidx,weight_spec=spec)
                task=dict(numerical_task_id=module.digest(identity),numerical_identity=identity,location_id=module.digest(location),location_identity=location,
                    status='MATERIALIZED_NOT_ATTEMPTED',fit_performed=False,anchor_alias_equivalence_verified=False,completed_reference=None,
                    complete_saved_rebinding_row=None,wrapper_call_attempt_count=0,expected_fitter_previous_target_weights={})
                tasks.append(task);ids.append(task['numerical_task_id'])
            combos.append(dict(k=k,rank=rank,prefix_security_ids=prefix,fitter_sorted_security_ids=order,selection_position=pos,fit_matrix=matrix,fit_data_sha256=sha,tasks=tasks))
    materialized=dict(schema='BULK_LAZY_TASK_MATERIALIZATION_V1',status='BOUNDED_INPUTS_MATERIALIZED_NO_EXECUTION',combination_count=544,materialized_task_count=1632,
        new_unattempted_task_count=1632,complete_saved_completed_task_count=504,selected_completed_intersection_count=0,new_wrapper_call_attempt_count=0,new_fit_count=0,
        fit_performed=False,full_shard_completed=False,all_plan_tasks_completed=False,fitter_source_hashes=numerical,plan_reference=module.ref('plan'),panel_reference=module.ref('panel'),
        panel_content_sha256='b'*64,combinations=combos,new_unattempted_numerical_task_ids=ids,selected_completed_numerical_task_ids=[],full_plan_task_denominator=plan['planned_canonical_task_count'])
    q=dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_V1',status='PREPARED_NOT_ATTEMPTED',source_hashes={},input_references={r:module.ref(r) for r in ('panel','plan','rebinding')},
        complete_observed_provenance_and_missing=gaps,preserved_evidence_sidecar_references=sidecars,materialized=materialized,
        schedule=dict(status='PLANNED_NOT_ATTEMPTED',materialization_allowed=True,positions=positions),full_plan_task_denominator=plan['planned_canonical_task_count'],
        **dict.fromkeys(('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','all_plan_tasks_completed','economic_comparison_performed','winner_selected','old_raw_reaudited'),False))
    audit=dict(status='PASS',preparation_sha256=module.ref('preparation')['sha256'],publication_sha256=module.ref('publication')['sha256'],reader_sha256=module.ref('audit_reader')['sha256'],
        combinations=544,tasks=1632,old_completed_reference_count=504,selected_completed_intersection_count=0,new_unattempted_tasks=1632,new_fit_count=0,cardinalities=list(range(4,21)),point_in_time_verified=False,full_search_completed=False,old_raw_readback_repeated=False)
    result=dict(preparation=q,publication=dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_PUBLICATION_V1',status='PREPARED_NOT_ATTEMPTED',preparation_reference=module.ref('preparation'),source_hashes={}),
        audit=audit,panel=paneldoc,plan=dict(plan=plan,complete_observed_provenance_and_missing=gaps,preserved_evidence_sidecar_references=sidecars),
        rebinding=dict(schema='BULK_COMPLETED_TASK_REBINDING_V1',numerical_contracts_unchanged=True,input_references=dict(plan=module.ref('plan')),rows=[dict(numerical_task_id=module.digest(['OLD',i])) for i in range(504)])),numerical
    docs=result[0]
    for obj in (docs['plan'], materialized):obj.update(flags)
    materialized['remaining_full_plan_uncompleted_count']=plan['planned_canonical_task_count']-504
    return docs,numerical


def case():
    c=f.case();state=dict(task=c['task'],combination_identity=c['combination'],input_references={},task_reference={'synthetic':'task'},source_hashes={},runtime=module.runtime())
    started=dict(schema='BULK_BUDGETED_SINGLE_TASK_STARTED_V1',**deepcopy(state),planned_operation_counts=module.counts(c['task']),**dict.fromkeys(module.FALSE,False))
    sr=dict(path='synthetic_started',sha256='a'*64)
    raw=dict(schema='BULK_BUDGETED_SINGLE_TASK_RAW_V1',started_reference=sr,numerical_task_id=c['task']['numerical_task_id'],status='FIT_RETURNED',operation_counts=module.counts(c['task']),fitted=c['fitted'],error=None,returned_fit_count=1,internal_optimizer_call_count=None,source_hashes={},runtime=state['runtime'],**dict.fromkeys(module.FALSE,False))
    return dict(started=started,raw=raw,state=state,started_reference=sr,numerical_sources=c['numerical_sources'])

class Tests(unittest.TestCase):
    def test_complete_contract_and_metadata_attacks(self):
        docs,_=documents();tasks,combos,num=module.validate_documents(docs)
        self.assertEqual((len(tasks),len(combos),len(num)),(1632,544,25))
        for mutate in (lambda d:d['panel']['panel']['returns']['index'].__setitem__(0,'2026-03-01junkT00:00:00'),lambda d:d['preparation']['materialized']['combinations'][0]['tasks'][0]['numerical_identity'].update(requested_previous_target_weights={}),lambda d:d['preparation']['preserved_evidence_sidecar_references'].pop('bulk_incremental_evidence_and_projection'),lambda d:d['preparation']['materialized'].update(new_fit_count=False)):
            bad=deepcopy(docs);mutate(bad)
            with self.assertRaises(ValueError):module.validate_documents(bad)

    def test_independent_fit_and_exact_started(self):
        a=case();detail=module.inspect_envelopes(**a);self.assertEqual(detail['status'],'FITTED_FIVE_RISKS_PASSED')
        for mutate in (lambda x:x['started']['planned_operation_counts'].update(wrapper_call_attempt_count=True),lambda x:x['raw'].update(returned_fit_count=True),lambda x:x['raw']['fitted']['targets'][next(iter(x['raw']['fitted']['targets']))].update(target_weight=.9)):
            bad=deepcopy(a);mutate(bad)
            with self.assertRaises(ValueError):module.inspect_envelopes(**bad)

    def test_four_outcome_semantics(self):
        a=case();sr=a['started_reference'];rr=dict(path='raw',sha256='b'*64);tid=a['state']['task']['numerical_task_id']
        for passed in (True,False):
            detail=dict(status='FITTED_FIVE_RISKS_PASSED' if passed else 'FITTED_FIVE_RISKS_FAILED',checks={'risk':passed})
            p=dict(schema='BULK_BUDGETED_SINGLE_TASK_POSTCHECK_V1',status='ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK' if passed else 'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK',started_reference=sr,raw_reference=rr,numerical_task_id=tid,checks=detail['checks'],error=None,**dict.fromkeys(module.FALSE,False))
            self.assertEqual(module.inspect_postcheck(p,sr,rr,tid,detail),'RISK_PASSED' if passed else 'RISK_FAILED')
        error=dict(type='ValueError',message='Numerical failure');detail=dict(status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',error=error,checks=None)
        p.update(status=detail['status'],error=error,checks=None)
        self.assertEqual(module.inspect_postcheck(p,sr,rr,tid,detail),'NUMERICAL_EXCEPTION')
        p.update(status='VALIDATION_FAILURE_RECORDED',error=dict(type='ValueError',message='Source drift'))
        self.assertEqual(module.inspect_postcheck(p,sr,rr,tid,detail),'VALIDATION_FAILURE')
        p.update(status=detail['status'])
        with self.assertRaises(ValueError):module.inspect_postcheck(p,sr,rr,tid,detail)

    def test_exception_has_no_invented_fit(self):
        a=case();a['raw'].update(status='FIT_EXCEPTION',fitted=None,error=dict(type='ArithmeticError',message='failure'),returned_fit_count=0)
        self.assertEqual(module.inspect_envelopes(**a)['status'],'NUMERICAL_EXCEPTION_NO_RETURNED_FIT')
        a['raw']['internal_optimizer_call_count']=0
        with self.assertRaises(ValueError):module.inspect_envelopes(**a)

    def test_external_post_anchor_and_no_repeat(self):
        a=case();tid=a['state']['task']['numerical_task_id']
        with tempfile.TemporaryDirectory() as td,patch.object(module,'OUTPUT_ROOT',Path(td)):
            folder=Path(td)/tid;folder.mkdir();refs={}
            a['started_reference']=dict(path=str(folder/'started.json'),sha256=module.codec.sha(module.codec.pretty(a['started'])));a['raw']['started_reference']=a['started_reference']
            for name,obj in [('started',a['started']),('raw',a['raw'])]:
                blob=module.codec.pretty(obj);(folder/(name+'.json')).write_bytes(blob);refs[name]=dict(path=str(folder/(name+'.json')),sha256=module.codec.sha(blob))
            detail=module.inspect_envelopes(**a)
            post=dict(schema='BULK_BUDGETED_SINGLE_TASK_POSTCHECK_V1',status='ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK',started_reference=refs['started'],raw_reference=refs['raw'],numerical_task_id=tid,checks=detail['checks'],error=None,**dict.fromkeys(module.FALSE,False))
            blob=module.codec.pretty(post);(folder/'postcheck.json').write_bytes(blob);pr=dict(path=str(folder/'postcheck.json'),sha256=module.codec.sha(blob))
            cache=dict(numerical=a['numerical_sources'],denominator=99999)
            with patch.object(module,'expected_state',return_value=(a['state'],cache)),patch.object(module,'guard'):
                with self.assertRaises(ValueError):module.readback(tid,dict(pr,sha256='0'*64),common={})
                r=module.readback(tid,pr,common={});self.assertEqual(module.codec.loads(Path(r['path']).read_bytes())['attempt_outcome'],'RISK_PASSED')
                with self.assertRaises(ValueError):module.readback(tid,pr,common={})

    def test_common_cannot_be_self_authorized(self):
        with self.assertRaises(ValueError):module.expected_state('a'*64,dict(ordered_task_ids=['a'*64]))

if __name__=='__main__':unittest.main()
