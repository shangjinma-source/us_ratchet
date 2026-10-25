"""Actual market producer and successor replay with isolated synthetic calendar/data."""
from datetime import datetime
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_build_real_monthly_release_entry as fixture
from test_materialize_real_monthly_successor import extended_fixture
from scripts.materialize_paper_monthly_successor_v3 import run
from scripts.build_monthly_successor_plan import prepare


class PaperSuccessorTests(unittest.TestCase):
    def setup_case(self, folder):
        with patch('test_build_real_monthly_release_entry.fixture', extended_fixture):
            root, args = fixture.EntryTests().setup_package(folder)
        complete = json.loads((root/args['complete_path']).read_bytes())
        args.update(expected_binding=complete['binding'], terminal_month='2027-10',
                    output_directory='paper-next-month',
                    clock=lambda: datetime.fromisoformat('2026-12-01T16:00:00+00:00'))
        return root, args

    def test_plan_replay_without_account_adoption_and_tamper_rejection(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            with patch('socket.socket', side_effect=AssertionError('NO_NETWORK')):
                before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(run(**args)['status'], 'PAPER_SUCCESSOR_PREFLIGHT')
                self.assertEqual(before, {p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                result = run(**args, execute=True)
                self.assertEqual(result['target_month'], '2027-01')
                self.assertEqual(run(**args, execute=True), result)
                config = json.loads((root/result['coordinator_path']).read_bytes())
                settings = json.loads((root/config['settings_path']).read_bytes())
                _, verified = prepare(settings['plan_path'], settings['plan_sha256'], root=root, clock=args['clock'])
                self.assertFalse(verified['ready_after_close'])
                self.assertFalse((root/'data/strategy_account').exists())
                self.assertFalse(list(root.rglob('*.sqlite*')))
                (root/'paper-next-month/boundary.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'SUCCESSOR_OUTPUT_CHANGED'):
                    run(**args, execute=True)

    def test_binding_future_time_and_study_end_rejected_without_output(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            for overrides, reason in [
                ({'expected_binding': {}}, 'COMPLETION_BINDING'),
                ({'clock': lambda:datetime.fromisoformat('2026-01-01T00:00:00+00:00')}, 'COMPLETION_BINDING'),
                ({'terminal_month': '2026-12'}, 'STUDY_FINISHED'),
            ]:
                with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                    run(**dict(args, **overrides), execute=True)
                self.assertFalse((root/'paper-next-month').exists())

    def test_failed_and_partial_evidence_preserved(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            failed = root/'real-market/failed.json'
            failed.write_text('{"failure":"synthetic"}')
            with self.assertRaisesRegex(ValueError, 'FAILED_PRESERVED'):
                run(**args, execute=True)
            self.assertEqual(failed.read_text(), '{"failure":"synthetic"}')
            self.assertFalse((root/'paper-next-month').exists())
        with TemporaryDirectory() as folder:
            root, args = self.setup_case(folder)
            (root/'paper-next-month').mkdir()
            with self.assertRaisesRegex(ValueError, 'PARTIAL_OUTPUT_NO_OVERWRITE'):
                run(**args, execute=True)
            self.assertEqual(list((root/'paper-next-month').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
