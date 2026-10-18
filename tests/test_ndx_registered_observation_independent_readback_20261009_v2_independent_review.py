"""Independent final-publication failure guards for disposable V5 observations."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_registered_observation_independent_readback_20261009_v2 as reader
from test_ndx_registered_observation_independent_readback_20261009_v2 import saved_context,read_context

class IndependentObservationReadbackV2Review(unittest.TestCase):
    def test_after_report_ancestor_drift_and_new_partial_namespace_preserve_failed_report(self):
        for attack in ('capture_audit_start','new_partial_attempt'):
            with self.subTest(attack=attack),TemporaryDirectory(prefix='SYNTHETIC_AUDITOR_OBSERVER_V2_')as folder:
                context,payload,receipt=saved_context(Path(folder));output=Path(payload['path']).parent;original=reader.save
                def late_drift(path,value):
                    item=original(path,value)
                    if path.name=='independent_readback.json':
                        if attack=='capture_audit_start':
                            target=Path(context[2]['readback_reference']['path']).parent/'started.json';target.write_bytes(target.read_bytes()+b'\n')
                        else:
                            directory=context[0]/'unrelated_late_namespace';directory.mkdir()
                            (directory/'observation_payload.json').write_bytes(reader.enc(dict(schema='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1')))
                    return item
                with patch.object(reader,'save',side_effect=late_drift),self.assertRaises(ValueError):read_context(context,payload,receipt)
                self.assertTrue((output/'independent_readback.json').is_file());self.assertTrue((output/'failure.json').is_file())
                failure=reader.decode((output/'failure.json').read_bytes())
                self.assertEqual(failure['status'],'INDEPENDENT_READBACK_FAILED_NO_RETRY');self.assertIs(failure['partial_evidence_preserved'],True)
                self.assertTrue(all(failure[key]is False for key in reader.WRITER_FALSE))
                report=(output/'independent_readback.json').read_bytes()
                with self.assertRaises(ValueError):read_context(context,payload,receipt)
                self.assertEqual((output/'independent_readback.json').read_bytes(),report)

    def test_mutable_claim_pre_read_and_resource_createonly_failure_preservation(self):
        with TemporaryDirectory(prefix='SYNTHETIC_AUDITOR_OBSERVER_V2_GATES_')as folder:
            root=Path(folder);live=root/'live.csv';live.write_bytes(b'immutable-looking')
            with patch.object(reader,'CURRENT',{'QQQ':live,'SPY':live}),patch.object(Path,'read_bytes',side_effect=AssertionError('Mutable read')):
                with self.assertRaisesRegex(ValueError,'Live cache'):reader.consume(dict(path=str(live),sha256=reader.sha(b'immutable-looking')),{})
            output=root/'report.json';reader.save(output,dict(synthetic=True));old=output.read_bytes()
            with self.assertRaises(FileExistsError):reader.save(output,{})
            with patch.object(reader.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(ValueError,'Resource stop'):reader.save(root/'new_report.json',{})
                reader.save(root/'failure.json',dict(status='INDEPENDENT_READBACK_FAILED_NO_RETRY'))
            self.assertFalse((root/'new_report.json').exists());self.assertEqual(output.read_bytes(),old)

if __name__=='__main__':unittest.main()
