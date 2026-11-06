import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.research.build_roa_monthly_adoption_request import handoff, follow


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        raw=b'{"schema":"fixture"}'
        (self.root/'launcher.json').write_bytes(raw)
        self.args=dict(root=self.root,descriptor_path='launcher.json',
                       descriptor_sha256=sha256(raw).hexdigest(),output_directory='tmp/handoff')

    def test_wait_never_creates_attempt_or_calls_adopter(self):
        with patch('scripts.research.build_roa_monthly_adoption_request.build',return_value={'status':'WAIT_PREPARED_MONTH'}), patch('scripts.research.advance_roa_monthly_release.advance') as advance:
            self.assertEqual(handoff(**self.args,execute=True)['status'],'WAIT_PREPARED_MONTH')
            advance.assert_not_called()
        self.assertFalse((self.root/'tmp').exists())

    def test_preview_does_not_persist_request(self):
        with patch('scripts.research.build_roa_monthly_adoption_request.build',return_value={'request':{'month':'2026-12'}}), patch('scripts.research.advance_roa_monthly_release.advance',return_value={'status':'PREVIEW'}) as advance:
            handoff(**self.args)
            self.assertFalse(advance.call_args.kwargs['execute'])
        self.assertFalse((self.root/'tmp').exists())

    def test_lost_acknowledgment_resumes_original_request_without_rebuild(self):
        request={'month':'2026-12','active':{'sha256':'original'}}
        with patch('scripts.research.build_roa_monthly_adoption_request.build',return_value={'request':request}) as build, patch('scripts.research.advance_roa_monthly_release.advance',side_effect=[TimeoutError(),{'status':'RESUMED'}]) as advance:
            with self.assertRaises(TimeoutError):handoff(**self.args,execute=True)
            self.assertEqual(handoff(**self.args,execute=True)['status'],'RESUMED')
            self.assertEqual(build.call_count,1)
            self.assertEqual(advance.call_args.kwargs['request'],request)

    def test_partial_request_requires_reconciliation(self):
        (self.root/'tmp/handoff').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'PARTIAL_HANDOFF'):handoff(**self.args,execute=True)

    def test_different_descriptor_cannot_resume(self):
        out=self.root/'tmp/handoff';out.mkdir(parents=True)
        (out/'handoff-request.json').write_text(json.dumps({'scope':{},'request':{}}))
        with self.assertRaisesRegex(ValueError,'HANDOFF_SCOPE_CHANGED'):handoff(**self.args,execute=True)

    def test_follow_wait_does_not_advance_or_leave_lock(self):
        with patch('scripts.research.build_roa_monthly_adoption_request.handoff',return_value={'status':'WAIT_PREPARED_MONTH'}):
            follow(**self.args,execute=True)
        self.assertFalse((self.root/'tmp/handoff/cursor.json').exists())
        self.assertFalse((self.root/'tmp/handoff/follow.lock').exists())

    def test_follow_uses_next_descriptor_only_after_verified_success(self):
        raw=b'{"next":true}';(self.root/'next.json').write_bytes(raw)
        successor=dict(path='next.json',sha256=sha256(raw).hexdigest())
        result=dict(status='MONTH_RUNTIME_AND_NEXT_TASK_VERIFIED',next_month={'launcher':successor})
        with patch('scripts.research.build_roa_monthly_adoption_request.handoff',side_effect=[result,{'status':'WAIT_PREPARED_MONTH'}]) as call:
            self.assertTrue(follow(**self.args,execute=True)['follow_cursor_advanced'])
            follow(**self.args,execute=True)
            self.assertEqual(call.call_args.kwargs['descriptor_path'],'next.json')

    def test_follow_partial_runtime_keeps_original_descriptor(self):
        with patch('scripts.research.build_roa_monthly_adoption_request.handoff',return_value={'status':'WAIT_RUNTIME_RECONCILIATION_NO_REPEAT_RESTART'}) as call:
            follow(**self.args,execute=True);follow(**self.args,execute=True)
            self.assertEqual(call.call_args.kwargs['descriptor_path'],'launcher.json')
        self.assertFalse((self.root/'tmp/handoff/cursor.json').exists())


if __name__=='__main__':unittest.main()
