from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from data.followup_capture_recovery_v1 import recovery_attempt


class RecoveryTests(TestCase):
    def fixture(self,root):
        original=root/'attempt';original.mkdir()
        def save(path,value):
            body=json.dumps(value).encode();path.write_bytes(body);return sha256(body).hexdigest()
        prior={name:save(original/name,value) for name,value in {
            'started.json':dict(event_sha256='event',session='2026-10-22',expected_manifest_sha256=None),
            'failed.json':dict(reason='MATURED_HORIZON_UNRESOLVED'),
            'review.json':dict(status='EVIDENCE_REVIEW_ONLY')}.items()}
        diagnosis=save(root/'diagnosis.json',dict(rows=[dict(event_sha256='event',parse_error='bad XML')]))
        request=dict(schema='FOLLOWUP_CAPTURE_RECOVERY_V1',event_sha256='event',session='2026-10-22',
            expected_manifest_sha256=None,prior_files=prior,diagnosis='RSS_NON_XML_RESPONSE',
            diagnosis_reference=dict(path='diagnosis.json',sha256=diagnosis))
        digest=save(root/'request.json',request)
        options=dict(root=root,original=original,request_path='request.json',request_sha256=digest,
            event_sha256='event',session='2026-10-22',expected_manifest_sha256=None)
        return original,options

    def test_readonly_recovery_is_separate_from_original(self):
        with TemporaryDirectory() as directory:
            original,options=self.fixture(Path(directory));before={p.name:p.read_bytes() for p in original.iterdir()}
            destination,request=recovery_attempt(**options)
            self.assertEqual(destination,original/'recoveries'/options['request_sha256'])
            self.assertFalse(destination.exists())
            self.assertEqual(before,{p.name:p.read_bytes() for p in original.iterdir()})

    def test_changed_evidence_and_wrong_session_rejected(self):
        with TemporaryDirectory() as directory:
            original,options=self.fixture(Path(directory))
            with self.assertRaisesRegex(ValueError,'RECOVERY_BINDING'):
                recovery_attempt(**dict(options,session='2026-10-23'))
            (original/'failed.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'RECOVERY_PRIOR_CHANGED'):recovery_attempt(**options)

    def test_changed_diagnosis_and_completed_attempt_rejected(self):
        with TemporaryDirectory() as directory:
            original,options=self.fixture(Path(directory))
            (original/'complete.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'RECOVERY_COMPLETED_ATTEMPT'):recovery_attempt(**options)
            (Path(directory)/'diagnosis.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'RECOVERY_DIAGNOSIS_CHANGED'):recovery_attempt(**options)
