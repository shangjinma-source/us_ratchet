"""Real producer/publisher/resolver integration using isolated synthetic market data."""
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_real_monthly_market_preparation import fixture
from scripts.run_real_monthly_market_preparation import run
from scripts.build_real_monthly_release_entry import build
from data.strategy_account_monthly_release import RELEASE_PATHS, resolve_monthly_runtime


class EntryTests(unittest.TestCase):
    def setup_package(self, folder):
        root, arguments, _, _ = fixture(folder)
        # The market-only fixture omits the real runtime identity manifest's
        # nested source map. Add the same explicit evidence binding used there.
        identity = json.loads((root/'auto-identities.json').read_bytes())
        identity['source_hashes'] = {name: sha256((root/name).read_bytes()).hexdigest()
            for name in identity['candidates'][0]['identity_source_references']}
        identity_hash = self.save(root, 'auto-identities.json', identity)
        bootstrap_descriptor = json.loads((root/'descriptor.json').read_bytes())
        bootstrap_descriptor['source_hashes']['auto-identities.json'] = identity_hash
        descriptor_hash = self.save(root, 'descriptor.json', bootstrap_descriptor)
        bootstrap = json.loads((root/'bootstrap.json').read_bytes())
        bootstrap['descriptor']['sha256'] = descriptor_hash
        arguments['bootstrap_sha256'] = self.save(root, 'bootstrap.json', bootstrap)
        run(**arguments, execute=True)
        pins = {}
        for path in RELEASE_PATHS:
            raw = (Path(__file__).resolve().parents[1]/path).read_bytes()
            destination = root/path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            pins[path] = sha256(raw).hexdigest()
        self.save(root, 'approved.json', {'source_pins': pins})
        return root, dict(root=root, complete_path='real-market/complete.json',
            complete_sha256=sha256((root/'real-market/complete.json').read_bytes()).hexdigest(),
            descriptor_path='approved.json', descriptor_sha256=sha256((root/'approved.json').read_bytes()).hexdigest())

    def save(self, root, path, value):
        raw = json.dumps(value).encode()
        (root/path).write_bytes(raw)
        return sha256(raw).hexdigest()

    def test_real_producer_entry_resolver_and_no_writes(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_package(folder)
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')):
                entry = build(**args)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
            digest = self.save(root, 'registry.json', dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1', entries=[entry]))
            configuration = resolve_monthly_runtime(root=root, registry_path='registry.json', registry_sha256=digest,
                clock=lambda: datetime.fromisoformat('2026-12-01T15:00:00+00:00'))
            self.assertEqual(configuration['target_month'], '2026-12')
            self.assertEqual(configuration['runtime_pins'], entry['runtime_pins'])
            self.assertFalse((root/'data/strategy_account').exists())

    def test_changed_output_rejected(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_package(folder)
            (root/'prepared/input.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                build(**args)

    def test_missing_approved_pin_cannot_be_generated(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_package(folder)
            args['descriptor_sha256'] = self.save(root, 'approved.json', {'source_pins': {}})
            with self.assertRaisesRegex(ValueError, 'APPROVED_RUNTIME_PINS_REQUIRED'):
                build(**args)

    def test_rebound_identity_rejected(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_package(folder)
            complete = json.loads((root/args['complete_path']).read_bytes())
            complete['result']['identity_sha256'] = '0'*64
            args['complete_sha256'] = self.save(root, args['complete_path'], complete)
            with self.assertRaisesRegex(ValueError, 'MARKET_RESULT_BINDING_MISMATCH'):
                build(**args)

    def test_runtime_drift_is_not_reapproved(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_package(folder)
            (root/sorted(RELEASE_PATHS)[0]).write_text('changed')
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                build(**args)

    def test_completion_after_open_rejected(self):
        with TemporaryDirectory() as folder:
            root, args = self.setup_package(folder)
            complete = json.loads((root/args['complete_path']).read_bytes())
            complete['at'] = '2026-12-01T20:00:00+00:00'
            args['complete_sha256'] = self.save(root, args['complete_path'], complete)
            with self.assertRaisesRegex(ValueError, 'MARKET_COMPLETION_WINDOW_INVALID'):
                build(**args)


if __name__ == '__main__':
    unittest.main()
