from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from scripts import ndx_dated_per_task_economic_comparison_20261003 as m
from test_ndx_dated_per_task_economic_comparison_20261003 import metadata


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.saved=metadata()  # Saved metadata only; never metrics/account/audit replay.

    def test_all_five_json_pointer_roles(self):
        tid,docs,refs,common=deepcopy(self.saved);args=m.project_inputs(tid,docs,refs,common)
        expected={'candidate_integer':'/account','incumbent_integer':'/account','candidate_continuous':'/candidate','incumbent_continuous':'/tracks/incumbent','nav_metrics':'/metrics'}
        self.assertEqual({k:r['json_pointer'] for k,r in args['source_references'].items()},expected)
        self.assertEqual(args['candidate_continuous'],docs['continuous']['candidate'])
        self.assertEqual(args['incumbent_continuous'],common['continuous']['tracks']['incumbent'])
        self.assertEqual(args['candidate_integer_status']['evidence_reference'],dict(refs['account_audit'],json_pointer='/attempt_outcome'))

    def test_incompatible_sources_and_technical_failure_never_compute(self):
        for mutate in (
            lambda d:d['account_audit'].__setitem__('attempt_outcome','VALIDATION_FAILURE_RECORDED'),
            lambda d:d['raw'].__setitem__('engine_call_attempt_count',True),
            lambda d:d['continuous_audit'].__setitem__('numerical_task_id','0'*64),
            lambda d:d['continuous_publication'].__setitem__('diagnostic_reference',{}),
            lambda d:d['inputs']['inputs']['original_task']['numerical_identity'].__setitem__('requested_previous_target_weights',{}),
        ):
            tid,docs,refs,common=deepcopy(self.saved);mutate(docs);core=Mock()
            with self.assertRaises(ValueError):m.assemble(tid,docs,refs,common,core)
            core.compare_per_task_paths.assert_not_called()

    def test_original_first_namespace_and_hard_sources(self):
        with patch.object(m,'load_common') as load:
            with self.assertRaises(ValueError):m.run(m.TASK,{}, {},execute=True)
            load.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)):
            tid='a'*64;folder=Path(tmp)/tid;folder.mkdir();(folder/'failure.json').write_text('{}')
            with patch.object(m,'load_common') as load:
                with self.assertRaises(ValueError):m.run(tid,{}, {},execute=True)
                load.assert_not_called()
        self.assertEqual(m.sha(m.CORE.read_bytes()),m.CORE_SHA)
        self.assertEqual(m.sha(m.HELPER.read_bytes()),m.HELPER_SHA)
        with self.assertRaises(ValueError):m.guard({str(m.CORE):'a'*64})

if __name__=='__main__':unittest.main()
