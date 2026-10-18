from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from scripts import ndx_cash_neighbor_combined_independent_readback_20261008 as subject
import test_ndx_cash_neighbor_combined_independent_readback_20261008 as fixture_module


class FinalGuards(unittest.TestCase):
    def test_complete_result_cannot_claim_continuous_monitoring(self):
        fixture_module.SourceTests.setUpClass()
        fixture=fixture_module.SourceTests();result=fixture.result()
        for value in (True,0,None):
            candidate=deepcopy(result);candidate['continuous_source_monitoring_claimed']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                subject.validate_recovery_result(candidate,candidate['registration_reference'],fixture.domain['segments'])

    def test_own_started_and_final_summary_drift_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            refs=[subject.save(Path(directory)/name,dict(status=name))for name in ('started.json','independent_readback.json')]
            subject.verify_saved_outputs(refs)
            for ref in refs:
                path=Path(ref['path']);original=path.read_bytes();path.write_bytes(b'{}')
                with self.subTest(path=path.name),self.assertRaises(ValueError):subject.verify_saved_outputs(refs)
                path.write_bytes(original)


if __name__=='__main__':unittest.main()
