import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_historical_cross_k_prefix_independent_audit_20260923 import fixture
from scripts import ndx_historical_cross_k_prefix_independent_audit_20260923 as m


class PrefixIndependentReview(unittest.TestCase):
    def test_resigned_checkpoint_cannot_hide_changed_raw_or_fitter_source(self):
        for defect in ('raw_boolean','source','partition','old_identity'):
            args=list(copy.deepcopy(fixture()));docs=args[1]
            if defect=='raw_boolean':docs['raw']['fit_performed']=1
            elif defect=='source':
                docs['raw']['result']['source_hashes']={'fake.py':'0'*64}
                docs['result']['result']=copy.deepcopy(docs['raw']['result'])
            elif defect=='partition':docs['result']['archive_resolution']={}
            else:args[0]['task_id']=m.plan_reader.target_reader.JOB
            with self.subTest(defect=defect),patch.object(m.shape,'result_schema'),patch.object(m.scalar,'inspect_result',return_value={'risk_pass':True}),self.assertRaises(ValueError):m.inspect_task(*args)

    def test_publisher_whole_report_rebuild_rejects_scope_and_source_deletion(self):
        good=dict(index_reference={'path':'index.json','sha256':'a'*64},historical_expected_source_hashes={'raw':'b'*64},archive_resolution={},fitter_called=False,result_imported=False,complete_marker_raw_checkpoint_chain_verified=True)
        for key,replacement in [('historical_expected_source_hashes',{}),('fitter_called',0),('result_imported',True),('complete_marker_raw_checkpoint_chain_verified',1)]:
            bad=copy.deepcopy(good);bad[key]=replacement
            with self.subTest(key=key),patch.object(m,'build',return_value=good),patch.object(m,'publish') as publish:
                with self.assertRaises(ValueError):m.publish_verified('unused.json',bad)
                publish.assert_not_called()

    def test_index_cannot_reorder_prefix_or_use_external_task_as_new(self):
        row,_,entry,_,_,base,_=fixture()
        sources=dict(base)
        for key in ('started_reference','raw_reference','result_reference'):sources[entry[key]['path']]=entry[key]['sha256']
        folder=str(Path(entry['started_reference']['path']).parent.parent)
        value=dict(schema='HISTORICAL_CROSS_K_FINALIZED_PREFIX_V1',plan_reference=m.PLAN,independent_plan_audit_reference=m.AUDIT,folder=folder,canonical_task_count=31828,external_completed_reference_count=1,external_completed_reference=m.plan_reader.TARGET,pending_task_count=31827,completed_new_count=1,remaining_new_count=31826,entries=[entry],status='PARTIAL',finalized_after_full_source_verification=True,contains_new_historical_fit_results=True,historical_expected_source_hashes=sources,archive_resolution={},**dict.fromkeys(m.FALSE,False))
        self.assertEqual(m.validate_index(value,[row],base),{})
        for identifier in ('f'*64,m.plan_reader.target_reader.JOB):
            altered=copy.deepcopy(value);altered['entries'][0]['task_id']=identifier
            with self.assertRaises(ValueError):m.validate_index(altered,[row],base)


if __name__=='__main__':unittest.main()
