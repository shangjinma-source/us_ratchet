import copy
import unittest
from unittest.mock import patch
from scripts import ndx_latest_fourteen_incremental_plan_20260919 as m


class IncrementIOTests(unittest.TestCase):
    def test_unsealed_audit_never_reads_or_fits(self):
        with patch.object(m.old.batch,'read',side_effect=AssertionError('no read')) as read:
            with self.assertRaises(ValueError):m.build(new_audit_path='unknown',new_audit_sha='0'*64,index_path='i',index_sha='h',old_audit_path='a',old_audit_sha='h',completed_prefix_confirmed=True)
            self.assertEqual(read.call_count,0)

    def test_only_completed_exact_task_matrix_reference_eligible(self):
        task=dict(selected={'s':{'ticker':'A','issuer_id':'i','risk_chain':'r'}},parameters={'fit_days':126})
        row=dict(task=task,old_equivalent_task_id='old',fit_data_sha256='m',status='PENDING_OLD_OR_NEW',completed_old_result_verified=False,result_reused=False)
        plan=dict(tasks=[copy.deepcopy(row),dict(copy.deepcopy(row),old_equivalent_task_id=None)])
        old=dict(canonical_tasks=[dict(task,task_id='old')])
        audit=dict(details=[dict(task_id='old',fit_data_sha256='m',checkpoint_reference={'path':'result','sha256':'h'})])
        m.mark_completed(plan,old,audit)
        self.assertEqual(plan['completed_old_reference_count'],1)
        self.assertFalse(plan['tasks'][0]['result_reused'])
        self.assertEqual(plan['tasks'][1]['status'],'PENDING_OLD_OR_NEW')
        for defect in ('matrix','risk'):
            bad=copy.deepcopy(row)
            if defect=='matrix':bad['fit_data_sha256']='different'
            else:bad['task']['selected']['s']['risk_chain']='other'
            with self.assertRaises(ValueError):m.mark_completed({'tasks':[bad]},old,audit)

    def test_unfinished_old_task_is_not_reused_or_refitted(self):
        plan={'tasks':[dict(task={},old_equivalent_task_id='old',fit_data_sha256='m',status='PENDING_OLD_OR_NEW',completed_old_result_verified=False,result_reused=False)]}
        m.mark_completed(plan,{'canonical_tasks':[{'task_id':'old'}]},{'details':[]})
        self.assertEqual(plan['completed_old_reference_count'],0)
        self.assertFalse(plan['tasks'][0]['completed_old_result_verified'])
        with self.assertRaises(ValueError):m.publish_verified('unused',{})

    def test_publisher_whole_plan_rebuild_rejects_resigned_scope_or_sources(self):
        sources=dict(m.LOADED)
        for ref in (m.PLAN,m.PANEL14,m.panel14.PANEL,m.OLD_INDEX,m.OLD_AUDIT):sources[ref['path']]=ref['sha256']
        sources[str(m.AUDIT14_PATH)]='a'*64
        value=dict(schema='SOURCE_BOUND_FOURTEEN_INCREMENTAL_PLAN_V1',historical_expected_source_hashes=sources,
            result_import_performed=False,fit_performed=False,automatic_refit_authorized=False,point_in_time_verified=False,promotion_allowed=False,
            delta={'completed_old_reference_count':764})
        with patch.object(m,'AUDIT14_SHA','a'*64),patch.object(m,'build',return_value=value),patch.object(m.old.batch.recipe,'exclusive_publish',side_effect=AssertionError('must reject before publish')):
            for kind in ('scope','sources','plan','extra'):
                bad=copy.deepcopy(value)
                if kind=='scope':bad['result_import_performed']=True
                elif kind=='sources':bad['historical_expected_source_hashes'].pop(next(iter(m.LOADED)))
                elif kind=='plan':bad['delta']['completed_old_reference_count']=763
                else:bad['unverified_authorization']=True
                with self.subTest(kind=kind),self.assertRaises(ValueError):m.publish_verified('unused',bad)


if __name__=='__main__':unittest.main()
