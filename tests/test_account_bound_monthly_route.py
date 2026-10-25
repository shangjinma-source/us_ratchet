"""Real store and route integration; final daily execution is deliberately stubbed."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.bootstrap_current_quantity_v2_simulation import run as bootstrap
from scripts.monthly_runtime_routes import publish, resolve
from scripts.run_account_bound_scheduled_simulation import run
from test_run_account_bound_scheduled_simulation import pair
from test_bootstrap_current_quantity_v2_simulation import fetch, NOW


def save(path, value):
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


def setup(root):
    config, args = pair(root)
    calendar = json.loads((root/'schedule.json').read_bytes())
    calendar['sessions'].append(dict(date='2026-11-02',
        open_at='2026-11-02T09:30:00-05:00', close_at='2026-11-02T16:00:00-05:00'))
    config['schedule']['sha256'] = save(root/'schedule.json', calendar)
    args['bootstrap_sha256'] = save(args['bootstrap_config'], config)
    base = json.loads(args['daily_config'].read_bytes())
    base['schedule_sha256'] = config['schedule']['sha256']
    args['daily_sha256'] = save(args['daily_config'], base)
    bootstrap(config_path=args['bootstrap_config'], config_sha256=args['bootstrap_sha256'],
              execute=True, clock=lambda: NOW, fetch=fetch)
    # This tests routing and identity, not validation/execution of monthly research.
    candidate = dict(base, monthly={'path': 'monthly-fixture.json', 'sha256': 'a'*64},
                     monthly_blob_root=str(root/'monthly-blobs'))
    path = root/'candidate.json'
    digest = save(path, candidate)
    directory = root/'releases'
    publish(directory=directory, session='2026-11-02', base_path=args['daily_config'],
            base_hash=args['daily_sha256'], candidate_path=path, candidate_hash=digest)
    args['monthly_runtime_directory'] = directory
    return config, args, candidate, path, digest


class AccountBoundMonthlyRouteTests(unittest.TestCase):
    def dispatch(self, args):
        return patch('scripts.run_account_bound_scheduled_simulation._now',
                     return_value=datetime.fromisoformat('2026-11-02T15:00:00+00:00'))

    def test_real_route_passes_selected_path_hash_and_preserves_store(self):
        with TemporaryDirectory() as folder:
            config, args, candidate, path, digest = setup(Path(folder))
            before = Path(config['database_path']).read_bytes()
            selected = resolve(directory=args['monthly_runtime_directory'], session='2026-11-02',
                               base_path=args['daily_config'], base_hash=args['daily_sha256'])
            self.assertEqual(selected, (str(path), digest))
            base = json.loads(args['daily_config'].read_bytes())
            self.assertEqual({k for k in base if base[k] != candidate[k]}, {'monthly', 'monthly_blob_root'})
            with self.dispatch(args), patch('scripts.run_account_bound_scheduled_simulation.run_runtime',
                                           return_value={'status': 'CAPTURED'}) as daily:
                self.assertEqual(run(**args, execute=True)['status'], 'CAPTURED')
                actual = daily.call_args.kwargs
                self.assertEqual(actual['config_path'], str(path))
                self.assertEqual(actual['config_sha256'], digest)
                self.assertEqual(actual['session'], '2026-11-02')
                self.assertEqual(actual['triggered_at'], '2026-11-02T15:00:00+00:00')
                self.assertTrue(actual['execute'])
                self.assertTrue(callable(actual['clock']))
            self.assertEqual(Path(config['database_path']).read_bytes(), before)

    def test_foreign_account_guard_blocks_before_daily_on_valid_route(self):
        with TemporaryDirectory() as folder:
            config, args, _, _, _ = setup(Path(folder))
            before = Path(config['database_path']).read_bytes()
            config['account_id'] = 'foreign-expected-account'
            args['bootstrap_sha256'] = save(args['bootstrap_config'], config)
            with self.dispatch(args), patch('scripts.run_account_bound_scheduled_simulation.run_runtime') as daily:
                with self.assertRaisesRegex(ValueError, 'ACCOUNT_BINDING_ORIGIN_MISMATCH'):
                    run(**args, execute=True)
                daily.assert_not_called()
            self.assertEqual(Path(config['database_path']).read_bytes(), before)

    def test_changed_candidate_identity_even_with_updated_release_hash_is_rejected(self):
        for key in ('database_path', 'simulation_id'):
            with self.subTest(key=key), TemporaryDirectory() as folder:
                config, args, candidate, path, _ = setup(Path(folder))
                before = Path(config['database_path']).read_bytes()
                candidate[key] = str(Path(folder)/'foreign.sqlite3') if key == 'database_path' else 'foreign-simulation'
                digest = save(path, candidate)
                slot = args['monthly_runtime_directory']/'2026-11.json'
                release = json.loads(slot.read_bytes()); release['config_sha256'] = digest
                save(slot, release)
                with self.dispatch(args), patch('scripts.run_account_bound_scheduled_simulation.run_runtime') as daily:
                    with self.assertRaisesRegex(ValueError, 'MONTHLY_ROUTE_CHANGED_BASE_CONFIGURATION'):
                        run(**args, execute=True)
                    daily.assert_not_called()
                self.assertEqual(Path(config['database_path']).read_bytes(), before)

    def test_bad_base_and_candidate_bytes_fail_before_daily(self):
        for mode in ('base_hash', 'base_bytes', 'candidate_bytes'):
            with self.subTest(mode=mode), TemporaryDirectory() as folder:
                config, args, _, path, _ = setup(Path(folder))
                before = Path(config['database_path']).read_bytes()
                if mode == 'base_hash': args['daily_sha256'] = '0'*64
                else:
                    target = args['daily_config'] if mode == 'base_bytes' else path
                    target.write_bytes(target.read_bytes()+b' ')
                with self.dispatch(args), patch('scripts.run_account_bound_scheduled_simulation.run_runtime') as daily:
                    with self.assertRaises(ValueError): run(**args, execute=True)
                    daily.assert_not_called()
                self.assertEqual(Path(config['database_path']).read_bytes(), before)


if __name__ == '__main__': unittest.main()
