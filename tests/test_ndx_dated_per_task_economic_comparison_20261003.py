from copy import deepcopy
from pathlib import Path
import json
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from scripts import ndx_dated_per_task_economic_comparison_20261003 as m

def metadata():
    sources={};common={k:m.read(m.ref(k),sources) for k in m.BOUND if not k.endswith('_reader')}
    manifest=json.loads((m.ROOT/'research_contracts/dated_initial_economic_completed_20261003_v1.json').read_bytes())
    row=next(r for r in manifest['rows'] if r['numerical_task_id'].startswith('5302'))
    docs,refs=m.load_candidate(row['numerical_task_id'],row['account_readback'],row['continuous_readback'],sources)
    return row['numerical_task_id'],docs,refs,common

class Tests(unittest.TestCase):
    def test_saved_metadata_only_no_economic_calculation(self):
        args=metadata();self.assertEqual(m.validate_candidate(*args),'ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING')
        projected=m.project_inputs(*args);self.assertEqual(projected['source_references']['candidate_continuous']['json_pointer'],'/candidate');self.assertEqual(projected['source_references']['incumbent_continuous']['json_pointer'],'/tracks/incumbent');self.assertIsNotNone(projected['candidate_account'])
    def test_shared_control_or_input_mismatch(self):
        tid,docs,refs,common=metadata();docs['continuous']['immutable_control_reference']['sha256']='0'*64
        with self.assertRaises(ValueError):m.validate_candidate(tid,docs,refs,common)
        tid,docs,refs,common=metadata();docs['continuous_audit']['inputs_reference']['sha256']='0'*64
        with self.assertRaises(ValueError):m.validate_candidate(tid,docs,refs,common)
    def test_missing_integer_explicit_not_cash(self):
        tid,docs,refs,common=metadata();status='NOT_EXECUTED_NONPOSITIVE_TARGET'
        docs['account_audit'].update(attempt_outcome=status,accounting_verified=False,accounting=None);docs['postcheck']['status']=status;docs['raw'].update(status=status,account=None,engine_call_attempt_count=0,returned_account_count=0)
        self.assertEqual(m.validate_candidate(tid,docs,refs,common),status);self.assertIsNone(docs['raw']['account']);projected=m.project_inputs(tid,docs,refs,common);self.assertIsNone(projected['candidate_account']);self.assertIsNone(projected['source_references']['candidate_integer']);self.assertEqual(projected['candidate_integer_status']['evidence_reference']['json_pointer'],'/attempt_outcome')
        docs['raw']['returned_account_count']=False
        with self.assertRaises(ValueError):m.validate_candidate(tid,docs,refs,common)
    def test_receipt_failure_retains_artifacts_and_no_retry(self):
        tid,docs,refs,shared=metadata();result=dict(schema='DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1',status='ALL_FOUR_SAVED_TRACKS_DIAGNOSTIC_ONLY',formal_comparison_passed=False,winner_selected=False,integer_missing_replaced_with_cash=False)
        calls=[]
        def compare(**kwargs):calls.append(kwargs);return result
        core=SimpleNamespace(compare_per_task_paths=compare)
        handle=dict(immutable_control_account_reference=m.ref('incumbent_account'),immutable_control_continuous_reference=dict(m.ref('continuous'),json_pointer='/tracks/incumbent'),immutable_nav_reference=m.ref('nav_metrics'))
        cache={id(handle):(handle,shared,{},core)}
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);count=[0]
            def guarded(sources):
                count[0]+=1
                if count[0]==5:raise ValueError('publication source drift')
            with patch.object(m,'OUTPUT',output),patch.object(m,'_CACHE',cache),patch.object(m,'load_candidate',return_value=(docs,refs)),patch.object(m,'guard',side_effect=guarded):
                with self.assertRaises(ValueError):m.run(tid,refs['account_audit'],refs['continuous_audit'],execute=True,common=handle)
                self.assertEqual(len(calls),1);self.assertTrue((output/tid/'publication.json').exists());self.assertTrue((output/tid/'failure.json').exists())
                with self.assertRaises(ValueError):m.run(tid,refs['account_audit'],refs['continuous_audit'],execute=True,common=handle)
                self.assertEqual(len(calls),1)
    def test_explicit_execute_and_pending_pin(self):
        with patch.object(m,'load_common') as load:
            with self.assertRaises(ValueError):m.run('a'*64,{}, {})
            with self.assertRaises(ValueError):m.run('a'*64,{}, {},execute=1)
            load.assert_not_called()
        with patch.object(m,'CORE_SHA',None):
            with self.assertRaises(ValueError):m.load_common()
    def test_synthetic_real_core_interface(self):
        from backtest import ndx_dated_per_task_comparison_research as pure
        from test_ndx_dated_per_task_comparison_research import fixture
        docs=dict(account_audit={},continuous_audit={},inputs=dict(inputs=dict(original_task={},limitations={}),original_provenance_and_missing=[],preserved_evidence_sidecars={}))
        with patch.object(m,'project_inputs',return_value=fixture()):
            result=m.assemble('a'*64,docs,{}, {},pure)
        self.assertEqual(result['comparison']['schema'],'DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1');self.assertEqual(result['comparison_core_call_count'],1);self.assertFalse(result['shared_account_reexecuted'])
    def test_first_task_cannot_recalculate(self):
        with self.assertRaises(ValueError):m.check_task(m.TASK)

if __name__=='__main__':unittest.main()
