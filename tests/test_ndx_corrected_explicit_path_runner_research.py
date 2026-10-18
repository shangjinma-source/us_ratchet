import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_corrected_explicit_path_runner_research as runner


class Tests(unittest.TestCase):
    def arguments(self, folder):
        path = Path(folder) / 'path.json'
        calendar = Path(folder) / 'calendar.json'
        path.write_text('{}', encoding='utf8')
        calendar.write_text('[]', encoding='utf8')
        return dict(path_path=str(path), path_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    calendar_path=str(calendar), calendar_sha256=hashlib.sha256(calendar.read_bytes()).hexdigest(),
                    output=str(Path(folder) / 'result.json'))

    def test_default_preflight_never_builds_or_creates_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            with patch.object(runner.core, 'prepare_explicit_path'), patch.object(runner.core, 'build_path_targets') as build:
                result = runner.run(**arguments)
                build.assert_not_called()
            self.assertFalse(result['fit_performed'])
            self.assertFalse(Path(arguments['output'] + '.started.json').exists())

    def test_marker_precedes_interrupt_and_reentry_never_prepares(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            marker = Path(arguments['output'] + '.started.json')
            def interrupted(prepared):
                self.assertEqual(json.loads(marker.read_text())['status'], 'STARTED_NOT_COMPLETED')
                raise KeyboardInterrupt()
            with patch.object(runner.core, 'prepare_explicit_path'), patch.object(runner.core, 'build_path_targets', side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    runner.run(**arguments, execute=True)
            self.assertFalse(Path(arguments['output']).exists())
            with patch.object(runner.core, 'prepare_explicit_path') as prepare:
                with self.assertRaises(FileExistsError):
                    runner.run(**arguments, execute=True)
                prepare.assert_not_called()

    def test_ordinary_failure_is_preserved_without_partial_schedule(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            with patch.object(runner.core, 'prepare_explicit_path'), patch.object(runner.core, 'build_path_targets', side_effect=ValueError('bad second period')):
                with self.assertRaisesRegex(ValueError, 'bad second period'):
                    runner.run(**arguments, execute=True)
            failure = json.loads(Path(arguments['output'] + '.failure.json').read_text())
            self.assertFalse(failure['partial_schedule_returned'])
            self.assertFalse(failure['automatic_retry_allowed'])
            self.assertNotIn('schedule', failure)
            self.assertFalse(Path(arguments['output']).exists())

    def test_marker_mutation_prevents_result_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = self.arguments(folder)
            def mutated(prepared):
                Path(arguments['output'] + '.started.json').write_text('{}')
                return {}
            with patch.object(runner.core, 'prepare_explicit_path'), patch.object(runner.core, 'build_path_targets', side_effect=mutated):
                with self.assertRaisesRegex(ValueError, 'SHA differs'):
                    runner.run(**arguments, execute=True)
            self.assertFalse(Path(arguments['output']).exists())


if __name__ == '__main__':
    unittest.main()
