from copy import deepcopy
import math
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_h_failed_export_recovery_independent_readback_v2_20261008 as subject


class IndependentMetadataReview(unittest.TestCase):
    def test_safe_signed_boundary_symmetry_and_nested_structure(self):
        for integer in (-(2**53-1), -7, 0, 7, 2**53-1):
            for left,right in ((integer,float(integer)),(float(integer),integer)):
                with self.subTest(left=left,right=right):
                    subject.exact_display_metadata({'a':[left,{'flag':False}]},{'a':[right,{'flag':False}]})
        for left,right in ((-(2**53),float(-(2**53))),(-2**53-1,float(-2**53-1)),
                (0,math.nextafter(0.,1.)),(1,math.nextafter(1.,2.)),(True,1.),
                ({'x':False},{'x':0}),({'x':[1]}, {'x':(1,)})):
            with self.subTest(left=left,right=right),self.assertRaises(ValueError):
                subject.exact_display_metadata(left,right)

    def test_nonfinite_and_original_exact_gate_unchanged(self):
        for value in (float('nan'),float('inf'),float('-inf')):
            with self.assertRaises(ValueError):subject.exact_display_metadata(value,value)
        for left,right in ((1,1.),(False,0),('1',1)):
            with self.assertRaises(ValueError):subject.exact(left,right)
        subject.exact_display_metadata({'fraction':1.25},{'fraction':1.25})
        with self.assertRaises(ValueError):subject.exact_display_metadata({'fraction':1.25},{'fraction':1.2500000000000002})

    def test_resigned_snapshot_cannot_change_failure_authority_or_exit_type(self):
        original=subject.loads(subject.FAILED_SNAPSHOT.read_bytes())
        for field,value in (('exit_code',True),('static_readback_passed',True),('visual_acceptance_passed',0),('retry_allowed',True)):
            document=deepcopy(original);document[field]=value
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'snapshot.json';raw=subject.enc(document);path.write_bytes(raw)
                with patch.object(subject,'FAILED_SNAPSHOT',path),patch.object(subject,'FAILED_SNAPSHOT_SHA',subject.sha(raw)):
                    with self.subTest(field=field),self.assertRaises(ValueError):subject.failed_predecessor()

    def test_extra_old_failure_namespace_output_rejected(self):
        with patch.object(subject,'names',return_value=['failure.json','started.json','independent_readback.json']):
            with self.assertRaisesRegex(ValueError,'Exact old failed namespace'):
                subject.failed_predecessor()


if __name__=='__main__':unittest.main()
