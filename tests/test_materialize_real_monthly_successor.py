"""Real market producer, entry verifier and successor planner; adoption boundary stubbed.

Actual persisted adoption replay has separate activation integration tests.
"""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_build_real_monthly_release_entry as entry_fixture
from api.strategy_rolling_composition import ROLLING_SOURCE_PATHS
from scripts.build_real_monthly_release_entry import build
from scripts.materialize_real_monthly_successor import run
from scripts.build_monthly_successor_plan import prepare

base_fixture = entry_fixture.fixture

def extended_fixture(folder):
    root, arguments, calls, bootstrap = base_fixture(folder)
    def save(path, value):
        raw = json.dumps(value).encode(); (root/path).write_bytes(raw)
        return sha256(raw).hexdigest()
    config = json.loads((root/'coordinator.json').read_bytes())
    settings = json.loads((root/'settings.json').read_bytes())
    schedule = json.loads((root/'schedule.json').read_bytes())
    for row in schedule['sessions']:
        row['timezone'] = 'America/New_York'
    for day in ('2026-12-31', '2027-01-01'):
        schedule['calendar'].append(day)
        schedule['sessions'].append(dict(date=day, timezone='America/New_York',
            open_at=day+'T09:30:00-05:00', close_at=day+'T16:00:00-05:00'))
    settings['fixed_source_hashes']['schedule.json'] = save('schedule.json', schedule)
    config['settings_sha256'] = save('settings.json', settings)
    arguments['coordinator_sha256'] = save('coordinator.json', config)
    return root, arguments, calls, bootstrap


class RealSuccessorTests(unittest.TestCase):
    def setup_case(self, folder):
        helper = entry_fixture.EntryTests()
        with patch('test_build_real_monthly_release_entry.fixture', extended_fixture):
            root, arguments = helper.setup_package(folder)
        descriptor = json.loads((root/'approved.json').read_bytes())
        for path in ROLLING_SOURCE_PATHS:
            raw = (Path(__file__).resolve().parents[1]/path).read_bytes()
            target = root/path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            descriptor['source_pins'][path] = sha256(raw).hexdigest()
        entry = build(**arguments)
        registry_hash = helper.save(root, 'active-registry.json', dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1', entries=[entry]))
        archive_hash = helper.save(root, 'archive.json', {'entries': []})
        snapshot = dict(registry_path='active-registry.json', registry_sha256=registry_hash,
                        archive_path='archive.json', archive_sha256=archive_hash)
        descriptor.update(snapshot)
        arguments['descriptor_sha256'] = helper.save(root, 'approved.json', descriptor)
        arguments.update(output_directory='next-real-month', clock=lambda: datetime.fromisoformat('2026-12-01T16:00:00+00:00'))
        return root, arguments, dict(snapshot, revision=1)

    def test_real_plan_no_paper_account_and_create_only_replay(self):
        with TemporaryDirectory() as folder:
            root, arguments, snapshot = self.setup_case(folder)
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', return_value=snapshot), \
                 patch('socket.socket', side_effect=AssertionError('NO_NETWORK')):
                before = {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(run(**arguments)['status'], 'REAL_SUCCESSOR_PREFLIGHT')
                self.assertEqual(before, {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
                result = run(**arguments, execute=True)
                self.assertEqual(result['target_month'], '2027-01')
                self.assertEqual(run(**arguments, execute=True), result)
                config = json.loads((root/result['coordinator_path']).read_bytes())
                settings = json.loads((root/config['settings_path']).read_bytes())
                _, verified = prepare(settings['plan_path'], settings['plan_sha256'], root=root, clock=arguments['clock'])
                self.assertFalse(verified['ready_after_close'])
                self.assertFalse((root/'data/strategy_account').exists())
                (root/'next-real-month/boundary.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'SUCCESSOR_OUTPUT_CHANGED'):
                    run(**arguments, execute=True)

    def test_absent_adoption_blocks_and_partial_output_not_replaced(self):
        with TemporaryDirectory() as folder:
            root, arguments, snapshot = self.setup_case(folder)
            # Exercise the actual read-only activation store on an absent DB.
            with self.assertRaisesRegex(ValueError, 'REAL_ADOPTION_REQUIRED'):
                run(**arguments, execute=True)
            self.assertFalse((root/'data/strategy_account').exists())
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', return_value=dict(snapshot, revision=0)):
                with self.assertRaisesRegex(ValueError, 'REAL_ADOPTION_REQUIRED'):
                    run(**arguments, execute=True)
            self.assertFalse((root/'next-real-month').exists())
            (root/'next-real-month').mkdir()
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', return_value=snapshot):
                with self.assertRaisesRegex(ValueError, 'PARTIAL_OUTPUT_NO_OVERWRITE'):
                    run(**arguments, execute=True)

    def test_active_registry_cannot_substitute_another_market(self):
        with TemporaryDirectory() as folder:
            root, arguments, snapshot = self.setup_case(folder)
            registry = json.loads((root/'active-registry.json').read_bytes())
            registry['entries'][0]['publication_sha256'] = '0'*64
            raw = json.dumps(registry).encode()
            (root/'active-registry.json').write_bytes(raw)
            snapshot['registry_sha256'] = sha256(raw).hexdigest()
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', return_value=snapshot):
                with self.assertRaisesRegex(ValueError, 'ACTIVE_MARKET_MISMATCH'):
                    run(**arguments, execute=True)
            self.assertFalse((root/'next-real-month').exists())
    def test_current_pointer_and_source_gate_enforced(self):
        with TemporaryDirectory() as folder:
            root, arguments, snapshot = self.setup_case(folder)
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', side_effect=[snapshot, dict(snapshot, revision=2)]):
                with self.assertRaisesRegex(ValueError, 'ACTIVE_RELEASE_CHANGED'):
                    run(**arguments, execute=True)
            self.assertFalse((root/'next-real-month').exists())
            (root/'api/strategy_rolling_composition.py').write_text('changed')
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', return_value=snapshot):
                with self.assertRaises(ValueError):
                    run(**arguments, execute=True)
            self.assertFalse((root/'next-real-month').exists())

    def test_reuse_after_next_adoption_requires_preserved_entry_and_untampered_completion(self):
        with TemporaryDirectory() as folder:
            root, arguments, snapshot = self.setup_case(folder)
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', return_value=snapshot):
                expected = run(**arguments, execute=True)
            registry = json.loads((root/'active-registry.json').read_bytes())
            registry['entries'].append(dict(target_month='2027-01', synthetic_next_month=True))
            raw = json.dumps(registry).encode(); (root/'later-registry.json').write_bytes(raw)
            later = dict(snapshot, revision=2, registry_path='later-registry.json', registry_sha256=sha256(raw).hexdigest())
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', return_value=later):
                self.assertEqual(run(**arguments), expected)
                self.assertEqual(run(**arguments, execute=True), expected)
                path = root/'next-real-month/materialization.complete.json'
                saved = path.read_bytes(); completion = json.loads(saved)
                completion['binding']['complete_sha256'] = '0'*64
                path.write_text(json.dumps(completion))
                with self.assertRaisesRegex(ValueError, 'COMPLETION_CHANGED'):
                    run(**arguments)
                path.write_bytes(saved)
            registry['entries'][0]['publication_sha256'] = '0'*64
            raw = json.dumps(registry).encode(); (root/'later-registry.json').write_bytes(raw)
            later['registry_sha256'] = sha256(raw).hexdigest()
            with patch('scripts.materialize_real_monthly_successor.MonthlyReleaseActivation.snapshot', return_value=later):
                with self.assertRaisesRegex(ValueError, 'ACTIVE_MARKET_MISMATCH'):
                    run(**arguments)

if __name__ == '__main__':
    unittest.main()
