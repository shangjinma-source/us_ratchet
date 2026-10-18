import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_history_failed_lineage_guard_20261008 as subject
import test_ndx_history_failed_lineage_guard_20261008 as fixtures


class IndependentLineageReview(unittest.TestCase):
    def test_resigned_success_audit_cannot_reuse_failed_counts(self):
        for value in (True,0,None):
            with tempfile.TemporaryDirectory() as directory:
                failed,audit,pins,digest=fixtures.Tests().fixture(Path(directory))
                document=json.loads(audit.read_bytes());document['previous_failed_counts_reused']=value
                raw=subject.encode(document);audit.write_bytes(raw);digest=hashlib.sha256(raw).hexdigest()
                with patch.multiple(subject,DIRECTORY=failed,AUDIT=audit,PINS=pins,AUDIT_SHA=digest):
                    with self.subTest(value=value),self.assertRaises(ValueError):
                        subject.diagnostic_members({**pins,str(audit):digest})

    def test_coherently_resigned_failure_cannot_change_original_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            failed,audit,pins,digest=fixtures.Tests().fixture(Path(directory))
            path=failed/'failure.json';failure=json.loads(path.read_bytes());failure['completed_channel_count']=7
            path.write_bytes(subject.encode(failure));pins[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            document=json.loads(audit.read_bytes());document['source_hashes']=pins
            document['previous_failed_attempt_references']['failure']['sha256']=pins[str(path)]
            audit.write_bytes(subject.encode(document));digest=hashlib.sha256(audit.read_bytes()).hexdigest()
            with patch.multiple(subject,DIRECTORY=failed,AUDIT=audit,PINS=pins,AUDIT_SHA=digest):
                with self.assertRaisesRegex(ValueError,'Failure semantics unchanged'):
                    subject.diagnostic_members({**pins,str(audit):digest})


if __name__=='__main__':unittest.main()
