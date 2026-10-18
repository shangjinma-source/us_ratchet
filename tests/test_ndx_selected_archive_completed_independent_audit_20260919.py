from copy import deepcopy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_selected_archive_completed_independent_audit_20260919 as m


class Tests(unittest.TestCase):
    def test_atomic_publication_failure_has_no_official_partial_file(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'verify_report'):
            path=Path(folder)/'audit.json';report=dict(completed=2)
            with patch.object(m.os,'link',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):m.publish_verified(path,report)
            self.assertFalse(path.exists());self.assertEqual(list(Path(folder).iterdir()),[])
            m.publish_verified(path,report);before=path.read_bytes()
            with self.assertRaises(FileExistsError):m.publish_verified(path,dict(completed=3))
            self.assertEqual(before,path.read_bytes())

    def fixture(self):
        row=dict(new_job_id='abc',task={'x':1});ref=dict(path='manifest',sha256='hard')
        value=dict(schema='SELECTED_ARCHIVE_RESOLUTION_TASK_V1',new_job_id='abc',original=row,
            manifest_path='manifest',manifest_sha256='hard',result={'window':[1]},input_digests={'original':'a','corrected':'b'},
            saved_result_revalidation_scope=m.original.SCOPE,mode='ONE_NEW_INPUT_FULL_V3_EVALUATION_NO_OLD_WINDOW_REUSE')
        for key in m.FLAGS+('original_historical_provenance_verified','non20_risk_projection_fields_independently_recomputed',
            'binary_float_ledger_hash_independently_verified','source_closure_finalized'):value[key]=False
        return row,ref,value

    def test_new_numeric_view_preserves_all_result_without_mutating_wrapper(self):
        row,ref,value=self.fixture();before=deepcopy(value)
        view=m.audit_view(value,row,ref,None,lambda *a:self.fail('No legacy read'))
        self.assertEqual(view['result'],value['result']);self.assertEqual(value,before)
        self.assertEqual(view['manifest_sha256'],m.original.MANIFEST_SHA)

    def test_whole_old_wrapper_and_modes_reject_resigning(self):
        row,ref,value=self.fixture();entry=dict(path='old',sha256='h')
        old=dict(result=deepcopy(value['result']),input_digests=value['input_digests'],metadata='original')
        value.update(mode='LEGACY_COMPLETED_RESULT_RESTORED_NO_NEW_FIT',legacy_completed_artifact=entry,legacy_original_wrapper=deepcopy(old))
        self.assertEqual(m.audit_view(value,row,ref,entry,lambda *a:old),old)
        for field in ('metadata','result'):
            bad=deepcopy(value);bad['legacy_original_wrapper'][field]='forged'
            with self.assertRaises(ValueError):m.audit_view(bad,row,ref,entry,lambda *a:old)
        with self.assertRaises(ValueError):m.audit_view(value,row,ref,None,lambda *a:old)
        value['non20_risk_projection_fields_independently_recomputed']=True
        with self.assertRaises(ValueError):m.audit_view(value,row,ref,entry,lambda *a:old)

    def test_prefix_denominator_scope_status_strict(self):
        manifest=dict(planned=3,tasks=[dict(new_job_id=k) for k in ('a','b','c')]);ref={'path':'p','sha256':'h'}
        final=dict(schema='SELECTED_ARCHIVE_RESOLUTION_FINALIZATION_V1',planned=3,completed=2,status='PARTIAL',immutable_numerical_source_closure_verified=True,original_historical_provenance_verified=False)
        index=dict(schema='SELECTED_ARCHIVE_RESOLUTION_COMPLETION_INDEX_V1',manifest=ref,planned=3,status='PARTIAL',completed=[dict(path='a.json',sha256='a'),dict(path='b.json',sha256='b')],finalization=final)
        for value in (final,index):value.update({key:False for key in m.FLAGS})
        self.assertEqual(m.check_index(index,manifest,ref),['a','b'])
        for mode in ('count','order','scope','status'):
            bad=deepcopy(index)
            if mode=='count':bad['finalization']['completed']=True
            if mode=='order':bad['completed'].reverse()
            if mode=='scope':bad['original_live_price_paths_verified']=True
            if mode=='status':bad['status']='COMPLETE'
            with self.assertRaises(ValueError):m.check_index(bad,manifest,ref)

    def test_end_verifier_rechecks_archives_and_loader_gap(self):
        report=dict(schema=m.SCHEMA,historical_expected_source_hashes=dict(m.LOADED),live_verified_source_hashes={},archive_resolutions=[{}]*85,historical_gap_observations=[{}]*26,tasks=[dict(historical_loader_provenance_gaps=['gap'])])
        for key in m.FLAGS+('optimizer_or_original_simulator_called','saved_non20_fields_independently_recomputed','binary_float_ledger_hash_independently_verified','nominal_quote_authenticity_verified','dynamic_next_open_execution_validated'):report[key]=False
        checked={k:report[k] for k in ('live_verified_source_hashes','archive_resolutions','historical_gap_observations')}
        with patch.object(m.archive,'load_contract',return_value={}),patch.object(m.archive,'verify_expected_sources',return_value=checked) as verify,patch.object(m.original,'verify_gaps') as gap:
            m.verify_report(report);self.assertEqual(verify.call_count,1);gap.assert_called_once_with(['gap'])
            verify.side_effect=ValueError('changed archived bytes')
            with self.assertRaises(ValueError):m.verify_report(report)


if __name__=='__main__':unittest.main()
