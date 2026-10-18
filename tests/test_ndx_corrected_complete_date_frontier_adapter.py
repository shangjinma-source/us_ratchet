from copy import deepcopy
from pathlib import Path
import unittest
from scripts import ndx_corrected_complete_date_frontier_research as module


class Tests(unittest.TestCase):
    def fixture(self):
        path=str((module.ROOT/'synthetic_complete.json').resolve());sha='a'*64
        audit=dict(schema='SELECTED_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1',date='2023-04-03',output_path=path,output_sha256=sha,source_hashes=dict(module.independent_diff.LOADED,**{path:sha}),
            original_count=5,selected_replaced=2,unrelated_records_exact=3,whole_date_task_map_verified=True,ordered_full_record_diff_verified=True,full_new_results_match_external_checkpoints=True,output_source_partitions_reverified=True,
            numerical_recomputation_performed=False,merger_called=False,historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False,selection_performed=False,training_performed=False)
        arguments=dict(date='2023-04-03',complete_path=path,complete_sha256=sha,parent=dict(original_count=5,pending_count=2,available_count=3),complete=dict(input_artifact_binding_verified=True))
        return audit,arguments

    def test_exact_full_diff_binding_and_false_scope(self):
        report,args=self.fixture();module.validate_diff(report,**args)
        for defect in ('sha','path','date','bool_count','count','source','flag','reader'):
            bad=deepcopy(report);arguments=deepcopy(args)
            if defect=='sha':bad['output_sha256']='b'*64
            elif defect=='path':bad['output_path']=str(Path(args['complete_path']).with_name('other.json'))
            elif defect=='date':bad['date']='2023-05-01'
            elif defect=='bool_count':bad['selected_replaced']=True
            elif defect=='count':bad['original_count']=4
            elif defect=='source':bad['source_hashes']={}
            elif defect=='flag':bad['promotion_allowed']=True
            else:arguments['complete']['input_artifact_binding_verified']=False
            with self.subTest(defect=defect),self.assertRaises(ValueError):module.validate_diff(bad,**arguments)

    def test_missing_date_does_not_fallback_to_another_cohort(self):
        with self.assertRaisesRegex(ValueError,'Exactly one'):
            module.build(date='2099-01-01',complete_path='unused',complete_sha256='0'*64,diff_path='unused',diff_sha256='0'*64)


if __name__=='__main__':unittest.main()
