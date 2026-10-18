"""Synthetic saved evidence only; no production task directories read."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_multik_completed_index_20260925 as m


def fixture():
    tid='a'*64;task=dict(numerical_task_id=tid,numerical_identity=dict(weight_spec='equal_weight',fit_data_sha256='b'*64))
    pointer=dict(m.ref('queue'),json_pointer='/synthetic');folder=m.TASK_ROOT/tid
    refs={name:dict(path=str(folder/(name+'.json')),sha256='c'*64) for name in ('started','raw','postcheck')}
    numerical={f'num{i}':'d'*64 for i in range(25)};source={**m.PINS,**numerical}
    counts=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=1,numerical_fit_request_count=0,import_count=0)
    started=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_STARTED_V1',task=task,task_reference=pointer,source_hashes=source,runtime={},planned_operation_counts=counts)
    fitted=dict(fit_data_sha256='b'*64,targets={'synthetic':1},source_hashes=numerical)
    raw=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_RAW_V1',numerical_task_id=tid,source_hashes=source,runtime={},started_reference=refs['started'],operation_counts=counts,status='FIT_RETURNED',returned_fit_count=1,error=None,fitted=fitted,internal_optimizer_call_count=None)
    post=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_POSTCHECK_V1',numerical_task_id=tid,started_reference=refs['started'],raw_reference=refs['raw'],error=None)
    saved=dict(schema='NEW_CUTOFF_MULTIK_SINGLE_TASK_INDEPENDENT_RAW_READBACK_V1',numerical_task_id=tid,independent_readback_performed=True,completed_saved_task_readbacks=1,
        input_references=dict(queue=m.ref('queue'),audit=m.ref('queue_audit'),completed_index=m.ref('old_index')),source_hashes={**source,**{r['path']:r['sha256'] for r in refs.values()}},
        started_reference=refs['started'],raw_reference=refs['raw'],saved_postcheck=post,status='FITTED_FIVE_RISKS_PASSED',numerical_detail_status='FITTED_FIVE_RISKS_PASSED',
        detail=dict(status='FITTED_FIVE_RISKS_PASSED',checks={name:True for name in m.RISK_NAMES}),
        **dict.fromkeys(('runner_called','fitter_called','optimization_repeated','promotion_allowed','execution_authorized','all_plan_tasks_completed'),False))
    return task,pointer,dict(path='audit',sha256='e'*64),dict(audit=saved,started=started,raw=raw,postcheck=post)


class Tests(unittest.TestCase):
    def test_saved_pass_and_risk_failure_are_distinct(self):
        args=fixture();self.assertEqual(m.row_from_evidence(*args)['status'],'FITTED_FIVE_RISKS_PASSED')
        saved=args[3]['audit'];saved['detail']['checks']['MAX_SINGLE_WEIGHT']=False
        with self.assertRaises(ValueError):m.row_from_evidence(*args)
        saved['status']=saved['numerical_detail_status']=saved['detail']['status']='FITTED_FIVE_RISKS_FAILED'
        self.assertEqual(m.row_from_evidence(*args)['status'],'FITTED_FIVE_RISKS_FAILED')

    def test_validation_failure_not_pass_and_false_count_rejected(self):
        args=fixture();args[3]['postcheck']['error']={'type':'ValueError','message':'synthetic'}
        with self.assertRaises(ValueError):m.row_from_evidence(*args)
        args[3]['audit']['status']='VALIDATION_FAILURE_RECORDED'
        self.assertEqual(m.row_from_evidence(*args)['status'],'VALIDATION_FAILURE_RECORDED')
        args[3]['raw']['returned_fit_count']=True
        with self.assertRaises(ValueError):m.row_from_evidence(*args)

    def test_source_pointer_attempt_attacks(self):
        for attack in ('source','pointer','attempt'):
            args=fixture()
            if attack=='source':args[3]['audit']['source_hashes'].pop('num0')
            elif attack=='pointer':args[3]['started']['task_reference']={'wrong':True}
            else:args[3]['raw']['operation_counts']=dict(wrapper_call_attempt_count=2)
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.row_from_evidence(*args)

    def test_pending_manifest_and_existing_namespace_before_io(self):
        bound=deepcopy(m.BOUND);bound['manifest']=(bound['manifest'][0],None)
        with patch.object(m,'BOUND',bound),patch.object(m,'load_bound') as load:
            with self.assertRaises(ValueError):m.build()
            load.assert_not_called()
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'index.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()


if __name__=='__main__':unittest.main()
