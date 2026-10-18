"""Synthetic saved evidence only; no production task directories read."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_ctas_completed_index_20260925 as m


def fixture():
    tid='a'*64;task=dict(numerical_task_id=tid,numerical_identity=dict(weight_spec='equal_weight',fit_data_sha256='b'*64))
    pointer=dict(m.ref('queue'),json_pointer='/synthetic');folder=m.TASK_ROOT/tid
    refs={name:dict(path=str(folder/(name+'.json')),sha256='c'*64) for name in ('started','raw','postcheck')}
    numerical={f'num{i}':'d'*64 for i in range(25)};source={**m.PINS,**numerical}
    counts=dict(wrapper_call_attempt_count=1,deterministic_generation_request_count=1,numerical_fit_request_count=0,import_count=0)
    started=dict(schema='NEW_CUTOFF_CTAS_SINGLE_TASK_STARTED_V1',task=task,task_reference=pointer,source_hashes=source,runtime={},planned_operation_counts=counts)
    fitted=dict(fit_data_sha256='b'*64,targets={'synthetic':1},source_hashes=numerical)
    raw=dict(schema='NEW_CUTOFF_CTAS_SINGLE_TASK_RAW_V1',numerical_task_id=tid,source_hashes=source,runtime={},started_reference=refs['started'],operation_counts=counts,status='FIT_RETURNED',returned_fit_count=1,error=None,fitted=fitted,internal_optimizer_call_count=None)
    post=dict(schema='NEW_CUTOFF_CTAS_SINGLE_TASK_POSTCHECK_V1',numerical_task_id=tid,started_reference=refs['started'],raw_reference=refs['raw'],error=None)
    saved=dict(schema='NEW_CUTOFF_CTAS_SINGLE_TASK_INDEPENDENT_RAW_READBACK_V1',numerical_task_id=tid,independent_readback_performed=True,completed_saved_task_readbacks=1,
        input_references=dict(queue=m.ref('queue'),audit=m.ref('queue_audit'),rebinding=m.ref('rebinding'),rebinding_audit=m.ref('rebinding_audit')),source_hashes={**source,**{r['path']:r['sha256'] for r in refs.values()}},
        started_reference=refs['started'],raw_reference=refs['raw'],saved_postcheck=post,status='FITTED_FIVE_RISKS_PASSED',numerical_detail_status='FITTED_FIVE_RISKS_PASSED',
        saved_postcheck_failure_preserved=False,saved_postcheck_failure_kind=None,detail=dict(status='FITTED_FIVE_RISKS_PASSED',checks={name:True for name in m.RISK_NAMES}),
        **dict.fromkeys(('runner_called','fitter_called','optimization_repeated','promotion_allowed','execution_authorized','all_plan_tasks_completed'),False))
    return task,pointer,dict(path='audit',sha256='e'*64),dict(audit=saved,started=started,raw=raw,postcheck=post)


class Tests(unittest.TestCase):
    def test_available_hard_anchors_exact_and_missing_manifest_stops_reads(self):
        for role,(path,digest) in m.BOUND.items():
            if role!='manifest':self.assertEqual(m.sha((m.BASE/path).read_bytes()),digest)
        bound=deepcopy(m.BOUND);bound['manifest']=(bound['manifest'][0],None)
        with patch.object(m,'BOUND',bound),patch.object(m.Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.build()
            read.assert_not_called()
    def test_complete102_manifest_order_required(self):
        oldids=[f'old{i}' for i in range(402)];ids=[f'{i:064x}' for i in range(102)]
        reused=dict(rebinding_reference=m.ref('rebinding'),independent_readback_reference=m.ref('rebinding_audit'),numerical_task_ids=oldids)
        docs=dict(queue=dict(schema='NEW_CUTOFF_CTAS_COMBINATION_MATERIALIZATION_V1',full_plan_task_denominator=37740237,reused_completed_reference=reused,
            new_materializations=[dict(combinations=[dict(tasks=[dict(numerical_task_id=tid)])]) for tid in ids]),
            queue_audit=dict(status='PASSED',candidate_reference=m.ref('queue')),
            rebinding=dict(schema='NEW_CUTOFF_V6_COMPLETED_TASK_REBINDING_V1',externally_rebound_task_count=402,rows=[dict(numerical_task_id=tid) for tid in oldids]),
            rebinding_audit=dict(status='PASSED',candidate_reference=m.ref('rebinding'),numerical_contracts_unchanged=True,verified_numerical_task_ids=oldids),
            manifest=dict(schema='CTAS_COMPLETED_AUDIT_REFERENCES_V1',queue_reference=m.ref('queue'),expected_count=102,
                task_audit_references=[dict(numerical_task_id=tid,path=str(m.TASK_ROOT/tid/'independent_readback.json'),sha256='e'*64) for tid in ids]))
        self.assertEqual(len(m.tasks_and_references(docs)[0]),102)
        for attack in ('missing','duplicate','order','bool'):
            bad=deepcopy(docs);refs=bad['manifest']['task_audit_references']
            if attack=='missing':refs.pop()
            elif attack=='duplicate':refs[-1]=deepcopy(refs[0])
            elif attack=='order':refs.reverse()
            else:bad['manifest']['expected_count']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.tasks_and_references(bad)

    def test_numerical_exception_with_same_post_error_stays_numerical(self):
        args=fixture();item=args[3];error=dict(type='ValueError',message='synthetic numerical exception')
        item['raw'].update(status='FIT_EXCEPTION',returned_fit_count=0,fitted=None,error=error)
        item['postcheck']['error']=error
        item['audit'].update(status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',numerical_detail_status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',
            detail=dict(status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',error=error),saved_postcheck_failure_preserved=True,saved_postcheck_failure_kind='NUMERICAL_EXCEPTION_RECORDED')
        result=m.row_from_evidence(*args)
        self.assertEqual(result['status'],'NUMERICAL_EXCEPTION_NO_RETURNED_FIT');self.assertIsNone(result['targets'])
        item['postcheck']['error']=dict(type='ValueError',message='distinct source validation failure')
        with self.assertRaises(ValueError):m.row_from_evidence(*args)
        item['audit']['status']='VALIDATION_FAILURE_RECORDED';item['audit']['saved_postcheck_failure_kind']='VALIDATION_FAILURE_RECORDED'
        self.assertEqual(m.row_from_evidence(*args)['status'],'VALIDATION_FAILURE_RECORDED')

    def test_saved_pass_and_risk_failure_are_distinct(self):
        args=fixture();self.assertEqual(m.row_from_evidence(*args)['status'],'FITTED_FIVE_RISKS_PASSED')
        saved=args[3]['audit'];saved['detail']['checks']['MAX_SINGLE_WEIGHT']=False
        with self.assertRaises(ValueError):m.row_from_evidence(*args)
        saved['status']=saved['numerical_detail_status']=saved['detail']['status']='FITTED_FIVE_RISKS_FAILED'
        self.assertEqual(m.row_from_evidence(*args)['status'],'FITTED_FIVE_RISKS_FAILED')

    def test_validation_failure_not_pass_and_false_count_rejected(self):
        args=fixture();args[3]['postcheck']['error']={'type':'ValueError','message':'synthetic'}
        with self.assertRaises(ValueError):m.row_from_evidence(*args)
        args[3]['audit']['status']='VALIDATION_FAILURE_RECORDED';args[3]['audit']['saved_postcheck_failure_preserved']=True;args[3]['audit']['saved_postcheck_failure_kind']='VALIDATION_FAILURE_RECORDED'
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
