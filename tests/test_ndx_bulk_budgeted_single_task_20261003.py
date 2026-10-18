"""Synthetic metadata and mocked single attempts; no saved queue or fit runs."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import date,timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_bulk_budgeted_single_task_20261003 as module
from scripts import bulk_all_k_plan_20261003 as planner
from backtest.ndx_issuer_combination_index_research import IssuerCombinationIndex


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
    return dict(preparation=q,publication=dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_PUBLICATION_V1',status='PREPARED_NOT_ATTEMPTED',preparation_reference=module.ref('preparation'),source_hashes={}),
        audit=audit,panel=paneldoc,plan=dict(plan=plan,complete_observed_provenance_and_missing=gaps,preserved_evidence_sidecar_references=sidecars),
        rebinding=dict(schema='BULK_COMPLETED_TASK_REBINDING_V1',numerical_contracts_unchanged=True,input_references=dict(plan=module.ref('plan')),rows=[dict(numerical_task_id=module.digest(['OLD',i])) for i in range(504)])),numerical


def small_state():
    selected={f'S{i}':dict(ticker=f'T{i}',issuer_id=f'I{i}',risk_chain=f'R{i}') for i in range(4)}
    identity=dict(selected=selected,parameters=module.PARAMETERS,weight_spec='equal_weight',requested_previous_target_weights=None,cutoff='2026-09-21',fit_data_sha256='a'*64)
    return dict(task=dict(numerical_identity=identity,numerical_task_id=module.digest(identity)),returns=module.pd.DataFrame(),combination_identity={},source_hashes={},runtime=module.runtime(),input_references={})


class Tests(unittest.TestCase):
    def test_complete_synthetic_queue_and_mutations(self):
        docs,num=documents();result=module.validate_common(docs,num)
        self.assertEqual(len(result['tasks']),1632)
        for mutate in (lambda d:d['preparation']['materialized'].update(materialized_task_count=True),
                       lambda d:d['preparation']['preserved_evidence_sidecar_references'].popitem(),
                       lambda d:d['panel']['panel']['returns']['data'][0].__setitem__(0,True),
                       lambda d:d['preparation']['materialized']['combinations'][0]['tasks'][0]['numerical_identity'].update(schema='WRONG')):
            bad=deepcopy(docs);mutate(bad)
            with self.assertRaises(ValueError):module.validate_common(bad,num)

    def test_all_seven_roots_reject_before_load(self):
        tid='a'*64
        for which in range(7):
            with tempfile.TemporaryDirectory() as td:
                roots=[Path(td)/str(i) for i in range(7)];(roots[which]/tid).mkdir(parents=True)
                with patch.object(module,'OLD_ROOTS',tuple(roots[:6])),patch.object(module,'OUTPUT_ROOT',roots[6]),patch.object(module,'load_common') as load:
                    with self.assertRaises(ValueError):module.preflight(tid)
                    load.assert_not_called()

    def attempt(self,td,fit,guard=None,post=None):
        state=small_state();tid=state['task']['numerical_task_id'];stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(module,'OUTPUT_ROOT',Path(td)/'new'))
        stack.enter_context(patch.object(module,'OLD_ROOTS',()))
        stack.enter_context(patch.object(module,'preflight',return_value=state))
        stack.enter_context(patch.object(module,'guard',side_effect=guard))
        fitter=stack.enter_context(patch.object(module.fitter,'refit_dynamic_cutoff_weights',side_effect=fit))
        stack.enter_context(patch.object(module,'postflight',return_value=post or dict(PASS=True)))
        return tid,fitter

    def test_no_execute_no_files_no_fit_and_strict_bool(self):
        with tempfile.TemporaryDirectory() as td:
            tid,fit=self.attempt(td,lambda **kw:{})
            module.run(tid);fit.assert_not_called();self.assertFalse((Path(td)/'new').exists())
            with self.assertRaises(ValueError):module.run(tid,execute=1)

    def test_returned_raw_survives_post_source_drift_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            calls=[]
            def guard(_):
                calls.append(1)
                if len(calls)>1:raise ValueError('drift')
            tid,fit=self.attempt(td,lambda **kw:dict(targets='retained'),guard)
            ref=module.run(tid,execute=True);post=json.loads(Path(ref['path']).read_bytes());raw=json.loads((Path(ref['path']).parent/'raw.json').read_bytes())
            self.assertEqual(raw['fitted'],dict(targets='retained'));self.assertEqual(post['status'],'VALIDATION_FAILURE_RECORDED')
            with self.assertRaises(ValueError):module.run(tid,execute=True)
            self.assertEqual(fit.call_count,1)

    def test_exception_and_risk_failure_distinct(self):
        for error in (True,False):
            with tempfile.TemporaryDirectory() as td:
                def fit(**kw):
                    if error:raise ArithmeticError('no return')
                    return dict(returned=True)
                tid,mock=self.attempt(td,fit,post=dict(PASS=False))
                ref=module.run(tid,execute=True);post=json.loads(Path(ref['path']).read_bytes());raw=json.loads((Path(ref['path']).parent/'raw.json').read_bytes())
                self.assertEqual(post['status'],'NUMERICAL_EXCEPTION_NO_RETURNED_FIT' if error else 'ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK')
                self.assertEqual(raw['returned_fit_count'],0 if error else 1);self.assertIsNone(raw['internal_optimizer_call_count'])

    def test_common_handle_forgery_rejected(self):
        with patch.object(module,'check_roots'),patch.object(module.fitter,'refit_dynamic_cutoff_weights') as fit:
            with self.assertRaises(ValueError):module.preflight('a'*64,common=dict(ordered_task_ids=[]))
            fit.assert_not_called()


if __name__=='__main__':unittest.main()
