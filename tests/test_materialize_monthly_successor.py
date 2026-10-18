import json
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from unittest.mock import patch
import unittest

from test_monthly_automatic_review_request import automatic_fixture
from scripts.coordinate_monthly_simulation import run as coordinate
from scripts.materialize_monthly_successor import run, calendar_source
from scripts.build_monthly_successor_plan import prepare


def completed_fixture(directory):
    root, args, calls, daily, inputs, save = automatic_fixture(directory)
    config = json.loads((root/'coordinator.json').read_bytes())
    settings = json.loads((root/'settings.json').read_bytes())
    schedule = json.loads((root/'schedule.json').read_bytes())
    for row in schedule['sessions']: row['timezone'] = 'America/New_York'
    # Synthetic sparse calendar, not a real trading-session assertion.
    for day in ('2026-12-31', '2027-01-01'):
        schedule['calendar'].append(day)
        schedule['sessions'].append(dict(date=day,timezone='America/New_York',
            open_at=day+'T09:30:00-05:00',close_at=day+'T16:00:00-05:00'))
    settings['fixed_source_hashes']['schedule.json'] = save('schedule.json', schedule)
    config['settings_sha256'] = save('settings.json', settings)
    args['config_sha256'] = save('coordinator.json', config)
    result = coordinate(**args, execute=True)
    assert result['status'] == 'MONTHLY_RUNTIME_PUBLISHED', result
    return root, args, calls, daily


class MaterializationTests(unittest.TestCase):
    def test_completed_pipeline_to_next_coordinator_registry_and_idempotency(self):
        with TemporaryDirectory() as directory:
            root, previous, calls, daily = completed_fixture(directory)
            before = Path(daily['database_path']).read_bytes()
            args = dict(previous_coordinator=root/'coordinator.json', previous_sha256=previous['config_sha256'],
                        output_directory='successor', clock=previous['clock'])
            checked = run(**args)
            self.assertEqual(checked['status'], 'SUCCESSOR_COORDINATOR_PREFLIGHT')
            self.assertFalse((root/'successor').exists())
            created = run(**args, execute=True)
            self.assertEqual(created['target_month'], '2027-01')
            self.assertEqual(run(**args, execute=True), created)
            config = json.loads(Path(created['coordinator_path']).read_bytes())
            settings = json.loads((root/config['settings_path']).read_bytes())
            _, validated = prepare(settings['plan_path'], settings['plan_sha256'], root=root, clock=previous['clock'])
            self.assertFalse(validated['ready_after_close'])
            self.assertEqual(config['daily_config'], str(root/'daily.json'))
            self.assertEqual(Path(daily['database_path']).read_bytes(), before)
            self.assertEqual(len(calls), 1)
            complete_path = root/'successor/materialization.complete.json'
            complete_raw = complete_path.read_bytes(); complete = json.loads(complete_raw)
            complete['input_hashes'].pop(next(iter(complete['input_hashes'])))
            complete_path.write_text(json.dumps(complete))
            with self.assertRaisesRegex(ValueError, 'INPUT_CLOSURE_CHANGED'): run(**args, execute=True)
            complete_path.write_bytes(complete_raw)
            started_path = root/'successor/materialization.started.json'
            started_raw = started_path.read_bytes(); started_path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'MATERIALIZATION_START_CHANGED'): run(**args, execute=True)
            started_path.write_bytes(started_raw)
            manifest = json.loads((root/'prepared/manifest.json').read_bytes())
            source = root/manifest['candidates'][0]['training_source']
            original = source.read_bytes(); source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'SUCCESSOR_INPUT_CHANGED'): run(**args, execute=True)
            source.write_bytes(original)
            (root/'successor/registry.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'SUCCESSOR_OUTPUT_CHANGED'): run(**args, execute=True)

    def test_incomplete_previous_or_partial_materialization_does_not_overwrite(self):
        with TemporaryDirectory() as directory:
            root, previous, _, _ = completed_fixture(directory)
            args = dict(previous_coordinator=root/'coordinator.json', previous_sha256=previous['config_sha256'],
                        output_directory='successor', clock=previous['clock'])
            (root/'successor').mkdir(); (root/'successor/materialization.started.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'PARTIAL_OUTPUT_NO_OVERWRITE'): run(**args, execute=True)
            (root/'stages/bind.complete.json').unlink()
            with self.assertRaisesRegex(ValueError, 'PREVIOUS_MONTH_INCOMPLETE'): run(**args)

    def test_calendar_source_outside_root_rejected_before_read(self):
        with TemporaryDirectory() as directory:
            parent = Path(directory); root = parent/'root'; root.mkdir()
            outside = parent/'outside.json'; outside.write_bytes(b'{}')
            expected = sha256(b'{}').hexdigest()
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('must not read outside root')):
                for path in ('../outside.json', str(outside)):
                    with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'CALENDAR_PATH_INVALID'):
                        calendar_source(root, path, expected)


if __name__ == '__main__':
    unittest.main()
