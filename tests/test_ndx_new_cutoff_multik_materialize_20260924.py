"""Synthetic interval dispatch only: no actual panel slice or fitting."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_multik_materialize_20260924 as module


def base():
    return dict(plan=dict(all_k_combination_count=786431,necessary_bound_excluded_combination_count=1331,
        planned_canonical_task_count=2355300,cardinalities=[dict(k=k,necessary_bound_certificates=['bound'] if k<4 else [],combination_count=2) for k in range(1,20)],
        shards=[dict(k=k,start=0,stop=2,shard_id=str(k)) for k in range(4,20)]),panel={'synthetic':True})


def stub(**argument):
    k=int(argument['shard_id']);combinations=[]
    for rank in range(argument['start'],argument['stop']):
        combinations.append(dict(tasks=[dict(numerical_task_id=f'{k}:{rank}:{spec}') for spec in range(3)]))
    return dict(k=k,combination_count=len(combinations),materialized_task_count=3*len(combinations),completed_task_count=0,combinations=combinations)


class Tests(unittest.TestCase):
    def test_completed_reference_preserves_full_rows_and_rejects_fake_completion(self):
        old=module.codec.loads(Path(module.ref('old_materialized')['path']).read_bytes())
        audit=module.codec.loads(Path(module.ref('old_materialization_audit')['path']).read_bytes())
        combo=old['materialization']['combinations'][0];rows=[];sources={}
        for position,task in enumerate(combo['tasks']):
            equal=position==0
            row=dict(full_task=deepcopy(task),numerical_task_id=task['numerical_task_id'],weight_spec=task['numerical_identity']['weight_spec'],
                fit_data_sha256=combo['fit_data_sha256'],status='COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED',targets={'preserved':'synthetic'},
                task_reference=dict(module.ref('old_materialized'),json_pointer='/materialization/combinations/0/tasks/'+str(position)),
                operation_counts=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0))
            for key in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):
                row[key]=dict(path=f'synthetic/{position}/{key}',sha256='a'*64);sources[row[key]['path']]='a'*64
            rows.append(row)
        index=dict(schema='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1',input_references=dict(plan=module.ref('plan'),materialized=module.ref('old_materialized'),materialization_audit=module.ref('old_materialization_audit')),
            completed_tasks=rows,completed_task_count=3,completed_combination_count=1,completed_original_risk_pass_count=3,completed_original_risk_failure_count=0,
            original_plan_task_denominator=2355300,remaining_plan_task_count=2355297,original_plan_combination_denominator=785100,remaining_plan_combination_count=785099,
            completed_coordinate=dict(k=4,rank=0,prefix_security_ids=combo['prefix_security_ids']),source_hashes=sources,
            fit_performed=False,promotion_allowed=False,full_shard_completed=False,all_plan_tasks_completed=False)
        documents=dict(completed_index=index,old_materialized=old,old_materialization_audit=audit)
        result=module.completed_reference(documents);self.assertEqual(result['completed_tasks'],rows)
        for attack in ('bool','task','ref'):
            bad=deepcopy(documents)
            if attack=='bool':bad['completed_index']['completed_original_risk_failure_count']=False
            elif attack=='task':bad['completed_index']['completed_tasks'][0]['full_task']['numerical_task_id']='wrong'
            else:bad['completed_index']['source_hashes'].clear()
            with self.subTest(attack=attack),self.assertRaises(ValueError):module.completed_reference(bad)

    def test_intervals_skip_completed_rank_and_keep_all_k(self):
        with patch.object(module.materializer,'materialize_slice') as call:
            args=module.batch_arguments(base());call.assert_not_called()
        self.assertEqual(len(args),16)
        self.assertEqual([(a['start'],a['stop']) for a in args],[(1,2)]+[(0,2)]*15)
        self.assertEqual(sum(a['stop']-a['start'] for a in args),31)

    def test_dispatch_exactly_31_new_combinations_93_new_tasks(self):
        with patch.object(module.materializer,'materialize_slice',side_effect=stub) as call:
            result=module.materialize_batch(module.batch_arguments(base()),['4:0:0','4:0:1','4:0:2'])
        self.assertEqual(call.call_count,16)
        self.assertEqual(sum(v['materialized_task_count'] for v in result),93)
        self.assertEqual(call.call_args_list[0].kwargs['start'],1)

    def test_reused_or_duplicate_identity_rejected(self):
        def attack(**argument):
            value=stub(**argument);value['combinations'][0]['tasks'][0]['numerical_task_id']='old';return value
        with patch.object(module.materializer,'materialize_slice',side_effect=attack),self.assertRaises(ValueError):
            module.materialize_batch(module.batch_arguments(base()),['old','old2','old3'])

    def test_denominator_bool_missing_k_and_coverage_attack(self):
        for attack in ('count','missing_k','overlap','gap','excluded'):
            value=base();plan=value['plan']
            if attack=='count':plan['all_k_combination_count']=True
            elif attack=='missing_k':plan['cardinalities'].pop()
            elif attack=='overlap':plan['shards'].append(deepcopy(plan['shards'][0]))
            elif attack=='gap':plan['shards'][0]['stop']=1
            else:plan['cardinalities'][4]['necessary_bound_certificates']=['new bound']
            with self.subTest(attack=attack),self.assertRaises(ValueError):module.batch_arguments(value)

    def test_pending_anchor_and_existing_output_fail_before_build(self):
        bound=deepcopy(module.BOUND);bound['completed_index']=(bound['completed_index'][0],None)
        with patch.object(module,'BOUND',bound),patch.object(module.materializer,'materialize_slice') as call:
            with self.assertRaises(ValueError):module.build()
            call.assert_not_called()
        with tempfile.TemporaryDirectory() as directory,patch.object(module,'OUTPUT',Path(directory)/'queue.json'),patch.object(module,'build') as build:
            with self.assertRaises(ValueError):module.publish()
            build.assert_not_called()


if __name__=='__main__':unittest.main()
