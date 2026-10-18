from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_h_failed_export_recovery_independent_readback_v3_20261008 as subject
import test_ndx_h_failed_export_recovery_independent_readback_v2_20261008 as original_tests
import test_ndx_h_v2_metadata_independent_review_20261008 as original_review


def evidence(value):
    return [dict(numerical_task_id='a'*64, engine_normalization_evidence=dict(float_total=value, unchanged_number=1.0, nested={'x':1.0}), original_target_evidence={'target':1.0})]


class OriginalStructuralTests(original_tests.Tests):
    def setUp(self):
        patcher=patch.object(original_tests,'r',subject);patcher.start();self.addCleanup(patcher.stop)


class OriginalMetadataTests(original_review.IndependentMetadataReview):
    def setUp(self):
        patcher=patch.object(original_review,'subject',subject);patcher.start();self.addCleanup(patcher.stop)


class EngineLeafTests(unittest.TestCase):
    def test_only_float_total_leaf_can_change_safe_numeric_representation(self):
        for value in (-(2**53-1),0,1,2**53-1):
            subject.exact_engine_evidence(evidence(value),evidence(float(value)))
            subject.exact_engine_evidence(evidence(float(value)),evidence(value))
        for mutation in ('other_leaf','nested_leaf','target','identity','extra_key'):
            left=evidence(1);right=evidence(1.0)
            if mutation=='other_leaf':left[0]['engine_normalization_evidence']['unchanged_number']=1
            elif mutation=='nested_leaf':left[0]['engine_normalization_evidence']['nested']['x']=1
            elif mutation=='target':left[0]['original_target_evidence']['target']=1
            elif mutation=='identity':left[0]['numerical_task_id']='b'*64
            else:left[0]['extra']=False
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):subject.exact_engine_evidence(left,right)
        with self.assertRaises(ValueError):subject.exact(1,1.0)

    def test_unsafe_fraction_bool_and_nonfinite_cross_representation_rejected(self):
        for actual,expected in ((2**53,float(2**53)),(2**53+1,float(2**53+1)),(1,1.25),(True,1.0),(1,True),(1,math.nextafter(1.0,2.0)),(float('nan'),float('nan')),(float('inf'),float('inf'))):
            with self.subTest(actual=actual,expected=expected),self.assertRaises(ValueError):subject.exact_engine_evidence(evidence(actual),evidence(expected))

    def test_v2_snapshot_fixed_hashes_authority_and_namespace(self):
        sources=subject.failed_v2_predecessor()
        self.assertEqual(sources[str(subject.FAILED_V2_READER)],subject.FAILED_V2_READER_SHA)
        saved=subject.loads(subject.FAILED_V2_SNAPSHOT.read_bytes())
        for field,value in (('exit_code',True),('original_handle',35504),('retry_allowed',True),('static_readback_passed',True),('visual_acceptance_passed',0)):
            altered=deepcopy(saved);altered[field]=value
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'snapshot.json';raw=subject.enc(altered);path.write_bytes(raw)
                with patch.object(subject,'FAILED_V2_SNAPSHOT',path),patch.object(subject,'FAILED_V2_SNAPSHOT_SHA',subject.sha(raw)),self.assertRaises(ValueError):subject.failed_v2_predecessor()
        with patch.object(subject,'names',return_value=['started.json','failure.json','independent_readback.json']),self.assertRaisesRegex(ValueError,'Exact V2 failed namespace'):subject.failed_v2_predecessor()

    def test_all_1264_observed_differences_fit_only_the_allowed_leaf(self):
        folder=subject.ROOT/'tmp/h_recovery_v2_readback_failure_20261008_v1'
        raw=(folder/'engine_inventory_report.json').read_bytes()
        self.assertEqual(subject.sha(raw),'e6912a330a9c1ce847945591b47e6c5f95eda3b346eea6f8d47bff307d128499')
        report=subject.loads(raw);difference=report['differences_reference'];lines=Path(difference['path']).read_bytes()
        self.assertEqual(subject.sha(lines),difference['sha256'])
        rows=[subject.loads(line)for line in lines.splitlines()]
        self.assertEqual(len(rows),1264)
        self.assertEqual((report['package_count'],report['task_count'],len(report['affected_packages'])),(277,1632,261))
        for row in rows:
            self.assertTrue(row['path'].endswith('/engine_normalization_evidence/float_total'))
            subject.exact_engine_evidence(evidence(row['actual']),evidence(row['expected']))


if __name__=='__main__':unittest.main()
