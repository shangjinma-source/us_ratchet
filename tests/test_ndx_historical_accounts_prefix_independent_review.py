import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_historical_cross_k_accounts_independent_audit_20260923 import skipped_fixture
from test_ndx_historical_cross_k_account_independent_research import fixture
from scripts import ndx_historical_cross_k_accounts_independent_audit_20260923 as m


class AccountPrefixReview(unittest.TestCase):
    def test_external_old_account_can_never_be_counted_as_new(self):
        original=fixture();args=list(skipped_fixture())
        args[2]=original['task'];args[3]=original['result'];args[4]=original['audited_detail'];args[7]=original['inputs'];args[8]=original['numerical_sources']
        with self.assertRaisesRegex(ValueError,'external'):m.inspect_entry(*args)

    def test_index_cannot_omit_started_or_shift_prefix_to_external(self):
        args=skipped_fixture();entry=args[0];base=args[6];folder=str(Path(entry['started_reference']['path']).parent.parent)
        sources=dict(base)
        for key in ('started_reference','result_reference'):sources[entry[key]['path']]=entry[key]['sha256']
        value=dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_INDEX_V1',plan_reference=m.PLAN,fit_prefix_audit_reference=args[5],folder=folder,audited_fit_task_count=1,completed_account_task_count=1,pending_account_task_count=0,entries=[entry],finalized_after_full_source_verification=True,external_completed_account_reference=m.EXTERNAL,external_account_imported=False,historical_expected_source_hashes=sources,archive_resolution={},**dict.fromkeys(m.FALSE,False))
        queue=[{'task_id':entry['task_id']}]
        for defect in ('source','old','zero_bool'):
            bad=copy.deepcopy(value)
            if defect=='source':del bad['historical_expected_source_hashes'][entry['started_reference']['path']]
            elif defect=='old':bad['entries'][0]['task_id']=m.prefix.plan_reader.target_reader.JOB
            else:bad['pending_account_task_count']=False
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_index(bad,queue,dict(base))

    def test_failed_risk_row_cannot_upgrade_saved_account_or_rewrite_risk_evidence(self):
        for defect in ('execution_bool','risk','source_flag'):
            args=list(copy.deepcopy(skipped_fixture()));saved=args[1]['result']
            if defect=='execution_bool':saved['execution_performed']=0
            elif defect=='risk':saved['failed_original_risk_checks']=[]
            else:saved['source_partition_verified_at_invocation_start']=1
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.inspect_entry(*args)

    def test_publication_requires_complete_rebuild_not_resigned_partition(self):
        good=dict(index_reference={'path':'index','sha256':'a'*64},historical_expected_source_hashes={'raw':'b'*64},archive_resolution={},external_account_imported=False)
        for key,replacement in [('historical_expected_source_hashes',{}),('external_account_imported',True),('extra_pit_certification',True)]:
            bad=copy.deepcopy(good);bad[key]=replacement
            with self.subTest(key=key),patch.object(m,'build',return_value=good),patch.object(m,'publish') as publish:
                with self.assertRaises(ValueError):m.publish_verified('unused.json',bad)
                publish.assert_not_called()


if __name__=='__main__':unittest.main()
