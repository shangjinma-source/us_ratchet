import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import review_saved_monthly_latched_half as reviewer


class SavedReviewGateTests(unittest.TestCase):
    def source_files(self, root):
        for name in reviewer.REVIEWER_PATHS:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic immutable source')

    def test_partial_arm_rejected_before_loading_inputs(self):
        with TemporaryDirectory() as directory, patch.object(reviewer, 'ROOT', Path(directory)):
            self.source_files(Path(directory))
            arm = Path(directory) / reviewer.OUTPUT / ('slippage5__' + reviewer.ARM)
            arm.mkdir(parents=True)
            (arm / 'terminal.json').write_text(json.dumps({'status': 'FAILED'}))
            with patch.object(reviewer, 'prepare_run', side_effect=AssertionError('NO_INPUT_LOAD')):
                with self.assertRaisesRegex(ValueError, 'COMPLETED_ARM_REQUIRED'):
                    reviewer.run('slippage5')

    def test_saved_receipt_and_outcome_corruption_rejected(self):
        for fault in ('receipt', 'outcome'):
            with self.subTest(fault=fault), TemporaryDirectory() as directory, patch.object(reviewer, 'ROOT', Path(directory)):
                self.source_files(Path(directory))
                root = Path(directory) / reviewer.OUTPUT
                arm = root / ('slippage5__' + reviewer.ARM)
                arm.mkdir(parents=True)
                (arm / 'terminal.json').write_text(json.dumps({'status': 'COMPLETE', 'outcome_sha256': 'a' * 64}))
                (arm / 'outcome.json').write_text('{}')
                (root / 'preflight.json').write_text(json.dumps({'version': 'tampered' if fault == 'receipt' else 'approved'}))
                with patch.object(reviewer, 'prepare_run', return_value=({}, {}, None, {'version': 'approved'})), \
                     patch.object(reviewer, 'review', side_effect=AssertionError('NO_UNBOUND_REVIEW')):
                    message = 'SAVED_PREFLIGHT_CHANGED' if fault == 'receipt' else 'OUTCOME_TERMINAL_MISMATCH'
                    with self.assertRaisesRegex(ValueError, message):
                        reviewer.run('slippage5')

    def test_preflight_or_reviewer_edit_during_review_is_rejected(self):
        for fault in ('preflight', 'reviewer'):
            with self.subTest(fault=fault), TemporaryDirectory() as directory, patch.object(reviewer, 'ROOT', Path(directory)):
                self.source_files(Path(directory))
                root = Path(directory) / reviewer.OUTPUT
                arm = root / ('slippage5__' + reviewer.ARM)
                arm.mkdir(parents=True)
                (arm / 'outcome.json').write_bytes(b'{}')
                (arm / 'metrics.json').write_bytes(b'{}')
                (arm / 'terminal.json').write_text(json.dumps({'status': 'COMPLETE',
                    'outcome_sha256': reviewer.sha256(b'{}').hexdigest()}))
                receipt = {'source_hashes': {}}
                (root / 'preflight.json').write_text(json.dumps(receipt))

                def mutate(**kwargs):
                    target = root / 'preflight.json' if fault == 'preflight' else Path(directory) / reviewer.REVIEWER_PATHS[1]
                    target.write_text('changed during review')
                    return {}

                with patch.object(reviewer, 'prepare_run', return_value=({'ohlc': {}}, {}, None, receipt)), \
                     patch.object(reviewer, 'review', side_effect=mutate), \
                     patch.object(reviewer, 'review_signals', return_value={}), \
                     patch.object(reviewer, 'verify_pins'):
                    message = 'RESULT_CHANGED_DURING_REVIEW' if fault == 'preflight' else 'REVIEWER_CHANGED_DURING_REVIEW'
                    with self.assertRaisesRegex(ValueError, message):
                        reviewer.run('slippage5')


if __name__ == '__main__':
    unittest.main()
