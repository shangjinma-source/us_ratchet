"""Synthetic completion-index references; never read actual task directories."""
from copy import deepcopy
import unittest
import test_ndx_new_cutoff_multik_completed_index_20260925 as f
from scripts import ndx_new_cutoff_multik_completed_index_20260925 as m


def manifest_fixture():
    tasks=[dict(numerical_task_id=f'{i:064x}') for i in range(93)]
    old=[dict(numerical_task_id=f'{i:064x}') for i in range(93,96)]
    queue=dict(schema='SOURCE_BOUND_NEW_CUTOFF_MULTIK_MATERIALIZATION_V1',full_pool_planned_task_count=2355300,new_materializations=[dict(combinations=[dict(tasks=tasks)])],
               reused_completed_reference=dict(completed_tasks=old))
    manifest=dict(schema='MULTIK_COMPLETED_AUDIT_REFERENCES_V1',queue_reference=m.ref('queue'),expected_count=93,
        task_audit_references=[dict(numerical_task_id=t['numerical_task_id'],path=str(m.TASK_ROOT/t['numerical_task_id']/'independent_readback.json'),sha256='c'*64) for t in tasks])
    return dict(queue=queue,old_index=dict(schema='NEW_CUTOFF_COMPLETED_TASK_INDEX_V1',original_plan_task_denominator=2355300,completed_task_count=3,completed_tasks=old),queue_audit=dict(status='PASSED',candidate_reference=m.ref('queue')),manifest=manifest)


class IndependentReview(unittest.TestCase):
    def test_external_manifest_exact_order_ids_and_count(self):
        self.assertEqual(len(m.tasks_and_references(manifest_fixture())[0]),93)
        for attack in ('order','duplicate','old','bool','path'):
            docs=manifest_fixture();refs=docs['manifest']['task_audit_references']
            if attack=='order':refs.reverse()
            elif attack=='duplicate':refs[1]=deepcopy(refs[0])
            elif attack=='old':docs['old_index']['completed_tasks'][0]['numerical_task_id']=refs[0]['numerical_task_id']
            elif attack=='bool':docs['manifest']['expected_count']=True
            else:refs[0]['path']='untrusted/audit.json'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.tasks_and_references(docs)

    def test_original_five_named_checks_required(self):
        args=f.fixture();checks=args[3]['audit']['detail']['checks']
        checks['IMPOSTOR']=checks.pop(next(iter(checks)))
        with self.assertRaises(ValueError):m.row_from_evidence(*args)

    def test_missing_postcheck_recovery_preserves_pass_without_fake_post_reference(self):
        args=f.fixture();args[3]['audit']['saved_postcheck']=None;args[3]['postcheck']=None
        result=m.row_from_evidence(*args)
        self.assertIsNone(result['postcheck_reference'])
        self.assertEqual(result['status'],'FITTED_FIVE_RISKS_PASSED')

    def test_exception_cannot_be_counted_as_returned_or_original_risk_failure(self):
        args=f.fixture();item=args[3];saved=item['audit']
        item['raw'].update(status='FIT_EXCEPTION',returned_fit_count=0,fitted=None,error={'type':'ValueError','message':'source finally'})
        saved.update(status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',numerical_detail_status='NUMERICAL_EXCEPTION_NO_RETURNED_FIT',detail={'status':'NUMERICAL_EXCEPTION_NO_RETURNED_FIT','checks':None},saved_postcheck=None)
        item['postcheck']=None
        result=m.row_from_evidence(*args)
        self.assertEqual(result['returned_fit_count'],0);self.assertIsNone(result['targets'])
        saved['status']='FITTED_FIVE_RISKS_FAILED'
        with self.assertRaises(ValueError):m.row_from_evidence(*args)


if __name__=='__main__':unittest.main()
