import copy
import unittest
from unittest.mock import patch
from scripts import ndx_fourteen_incremental_independent_audit_20260919 as m


class DeltaAuditTests(unittest.TestCase):
    def test_unsealed_never_reads_or_fits(self):
        with patch.object(m,'RUNNER_SHA',None),patch.object(m.scalar,'read',side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):m.build('absent','0'*64,completed_prefix_confirmed=True)

    def test_only_finalized_exact_new_prefix_and_strict_types(self):
        tasks=[{'task_id':'a'},{'task_id':'b'}];entries=[{'task_id':'a'}]
        index=dict(schema='FOURTEEN_INCREMENTAL_BOUNDED_INDEX_V1',plan_reference=dict(path=str(m.PLAN),sha256=m.PLAN_SHA),output_directory=str(m.ROOT),original_reference_count=764,
            new_input_planned=31064,new_input_completed=1,new_input_pending=31063,status='PARTIAL',finalized_after_full_source_verification=True,entries=entries,old_results_imported=0,**dict.fromkeys(m.FALSE,False))
        m.validate_index(index,tasks)
        for field,value in [('finalized_after_full_source_verification',False),('new_input_completed',True),('old_results_imported',1),('promotion_allowed',True),('entries',[{'task_id':'b'}])]:
            bad=copy.deepcopy(index);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.validate_index(bad,tasks)

    def test_publication_rebuild_rejects_extra_scope_and_source_deletion(self):
        expected=dict(schema=m.SCHEMA,index_reference={'path':'bound','sha256':'a'*64},historical_expected_source_hashes={'source':'h'},**dict.fromkeys((*m.FALSE,'old_result_numerical_audit_repeated','solver_called','owner_check_result_called','constrained_projection_optimality_independently_verified','risk_chain_projection_metadata_independently_recomputed'),False))
        with patch.object(m,'build',return_value=expected),patch.object(m.scalar,'exclusive_publish',side_effect=AssertionError('must reject')):
            for defect in ('source','extra','scope'):
                bad=copy.deepcopy(expected)
                if defect=='source':bad['historical_expected_source_hashes']={}
                elif defect=='extra':bad['execution_approved']=True
                else:bad['solver_called']=True
                with self.assertRaises(ValueError):m.publish_verified('unused',bad)


if __name__=='__main__':unittest.main()
