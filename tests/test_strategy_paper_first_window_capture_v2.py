from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from data.strategy_paper_first_window_capture_v2 import capture_first_window, load_first_window_archive
from data.strategy_paper_first_window_core_v2 import review_source_window
import test_strategy_paper_first_window_core_v2 as fixtures


class FirstCaptureTests(unittest.TestCase):
    def test_transport_review_archive_and_no_blind_repeat(self):
        with TemporaryDirectory() as folder:
            account, context = fixtures.PaperSourceWindowTests().case(folder)
            root = Path(folder)
            binding = dict(account_id=context['account_id'],account_revision=context['account_revision'],
                           target_id=context['target_id'],session='2026-11-03')
            calls=[]
            def daily(*args):
                calls.append('daily')
                return dict(status=200,body=context['capture_files']['daily.response.bin'])
            def official():
                calls.append('official')
                return dict(status=200,body=context['capture_files']['official.response.bin'])
            def review(**arguments):
                return review_source_window(**dict(context,capture_files=arguments['capture_files']))
            args=dict(directory=root/'first',review_arguments=dict(configuration_sha256=context['configuration_sha256']),
                      read_binding=lambda:binding,fetch_daily=daily,fetch_official=official)
            before=account.store.path.read_bytes()
            with patch('data.strategy_paper_first_window_capture_v2.verified_first_window_context',return_value=context), \
                 patch('data.strategy_paper_first_window_capture_v2.review_paper_first_window',side_effect=review):
                result=capture_first_window(**args)
                self.assertEqual(result['status'],'FIRST_WINDOW_REVIEWED_NOT_ADMITTED')
                self.assertTrue((root/'first/complete.json').is_file())
                self.assertFalse((root/'first/failed.json').exists())
                self.assertEqual(capture_first_window(**args)['status'],'NEEDS_RECOVERY')
            restored=load_first_window_archive(root=root,directory=root/'first',
                trusted_complete_sha256=result['complete_sha256'],expected_binding=binding)
            self.assertEqual(restored['files'],result['files'])
            self.assertEqual(restored['receipt_bytes'],result['receipt_bytes'])
            (root/'first/receipt.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'ARCHIVE_HASH'):
                load_first_window_archive(root=root,directory=root/'first',
                    trusted_complete_sha256=result['complete_sha256'],expected_binding=binding)
            self.assertEqual(calls,['daily','official'])
            self.assertEqual(account.store.path.read_bytes(),before)

    def test_transport_failure_preserves_evidence_and_refuses_retry(self):
        with TemporaryDirectory() as folder:
            _, context=fixtures.PaperSourceWindowTests().case(folder)
            binding=dict(account_id=context['account_id'],account_revision=context['account_revision'],
                         target_id=context['target_id'],session='2026-11-03')
            calls=[]
            def broken(*args):
                calls.append('daily');return dict(status=503,body=b'Unavailable')
            args=dict(directory=Path(folder)/'first',review_arguments=dict(configuration_sha256=context['configuration_sha256']),
                      read_binding=lambda:binding,fetch_daily=broken,fetch_official=lambda: self.fail('unexpected RSS'))
            with patch('data.strategy_paper_first_window_capture_v2.verified_first_window_context',return_value=context):
                with self.assertRaises(Exception):capture_first_window(**args)
                self.assertTrue((Path(folder)/'first/failed.json').is_file())
                self.assertEqual(capture_first_window(**args)['status'],'NEEDS_RECOVERY')
            self.assertEqual(calls,['daily'])


if __name__=='__main__':unittest.main()
