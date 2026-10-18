"""Synthetic publication integration; no production accounts or selection."""
from copy import deepcopy
from unittest.mock import patch
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.current_quantity_v2_current_cash_plan import canonical
from data.strategy_account_monthly_release import resolve_monthly_runtime, RELEASE_PATHS
from data.strategy_account_runtime import build_runtime
from data.strategy_account_monthly_release import validate_account_identity_coverage
from core.strategy_account_ledger import replay
from scripts.publish_monthly_market_configuration import publish
from test_publish_monthly_market_configuration import inputs


class MonthlyReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        receipt = publish(**inputs(self.root))
        self.receipt = receipt
        config = json.loads((self.root/receipt['config_path']).read_bytes())
        manifest = json.loads((self.root/config['market_entries'][0]['manifest_path']).read_bytes())
        self.identity = {'candidates': manifest['candidates'], 'source_hashes': manifest['source_hashes']}
        for candidate in self.identity['candidates']:
            candidate['identity_source_references'] = ['synthetic-evidence.json']
        source_root = Path(__file__).resolve().parents[1]
        pins = {}
        for path in RELEASE_PATHS:
            raw = (source_root/path).read_bytes()
            target = self.root/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            pins[path] = sha256(raw).hexdigest()
        self.entry = dict(target_month='2026-12', publication_path='receipt.json',
            publication_sha256=self.put('receipt.json', receipt), identity_manifest='identity-release.json',
            identity_sha256=self.put('identity-release.json', self.identity), runtime_pins=pins)
        self.registry = dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1', entries=[self.entry])

    def put(self, name, value):
        raw = canonical(value)
        (self.root/name).write_bytes(raw)
        return sha256(raw).hexdigest()

    def resolve(self, now='2026-12-01T15:00:00+00:00', account_state=None):
        digest = self.put('registry.json', self.registry)
        return resolve_monthly_runtime(root=self.root, registry_path='registry.json',
            registry_sha256=digest, clock=lambda: datetime.fromisoformat(now), account_state=account_state)

    def test_real_publisher_output_resolves_read_only(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.resolve()
        self.assertEqual(result['schema'], 'REAL_STRATEGY_RUNTIME_V1')
        self.assertEqual(result['target_month'], '2026-12')
        self.assertEqual(result['training_closed_at'], '2026-11-02T16:00:00-05:00')
        runtime = build_runtime(root=self.root, configuration=result,
                                clock=lambda: datetime.fromisoformat('2026-12-01T15:00:00+00:00'))
        self.assertIsNone(runtime.selection.store.read())
        self.assertFalse((self.root/'data/strategy_account').exists())
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        after.pop(Path('registry.json'))
        self.assertEqual(before, after)

    def holding_event(self, *, identity=True, ticker='DEPARTED', side='BUY', event_id='fill'):
        event = dict(event_id=event_id, kind='DIRECT_FILL', security_id='departed-id',
                     side=side, quantity=2, price='10', fees='0',
                     executed_at='2026-11-01T15:00:00+00:00')
        if identity:
            event['identity_evidence'] = dict(ticker=ticker, security_id='departed-id',
                source_references=['old.json'], source_hashes={'old.json': '1'*64})
        return event

    def add_departed_identity(self):
        self.identity['candidates'].append(dict(ticker='DEPARTED', security_id='departed-id',
            issuer_id='departed-issuer', status='READY_CONDITIONAL', identity_reviewed=True,
            identity_source_references=['synthetic-evidence.json']))
        self.entry['identity_sha256'] = self.put('identity-release.json', self.identity)

    def coverage(self, state):
        return validate_account_identity_coverage(self.root, self.entry, state)

    def test_departed_holding_passes_resolver_without_writes_or_fetch(self):
        self.add_departed_identity()
        state = replay('isolated', [self.holding_event()])
        before_state = deepcopy(state)
        self.put('registry.json', self.registry)
        before_files = {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            configuration = self.resolve(account_state=state)
            result = validate_account_identity_coverage(self.root, configuration, state)
        self.assertEqual(set(result['identities']), {'departed-id'})
        self.assertEqual(result['account_revision'], state['revision'])
        self.assertEqual(state, before_state)
        self.assertEqual(before_files, {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.root/'data/strategy_account').exists())

    def test_missing_new_identity_blocks_resolver(self):
        state = replay('isolated', [self.holding_event()])
        with self.assertRaisesRegex(ValueError, 'IDENTITY_NOT_UNIQUE_OR_UNAVAILABLE'):
            self.resolve(account_state=state)

    def test_missing_recorded_identity_and_tampered_state_fail(self):
        self.add_departed_identity()
        state = replay('isolated', [self.holding_event(identity=False)])
        with self.assertRaisesRegex(ValueError, 'HELD_OR_PENDING_IDENTITY_MISSING'):
            self.coverage(state)
        state['shares']['departed-id'] = 0
        with self.assertRaisesRegex(ValueError, 'ACCOUNT_REPLAY_MISMATCH'):
            self.coverage(state)

    def test_pending_only_needs_identity_but_closed_and_zero_do_not(self):
        event = dict(event_id='open',kind='ORDER_OPEN',order_id='order',security_id='departed-id',
                     side='BUY',quantity=2,limit_price='10',fee_per_share='0',
                     identity_evidence=self.holding_event()['identity_evidence'])
        state = replay('isolated', [event])
        with self.assertRaisesRegex(ValueError, 'IDENTITY_NOT_UNIQUE_OR_UNAVAILABLE'):
            self.coverage(state)
        closed = replay('isolated', [event,dict(event_id='cancel',kind='CANCEL',order_id='order')])
        self.assertEqual(self.coverage(closed)['identities'], {})
        zero = replay('isolated', [self.holding_event(identity=False),
            self.holding_event(identity=False,side='SELL',event_id='sold')])
        self.assertEqual(self.coverage(zero)['identities'], {})
        self.add_departed_identity()
        self.assertEqual(set(self.coverage(state)['identities']), {'departed-id'})

    def test_conflicting_recorded_ticker_sid_drift_rename_and_hash_fail(self):
        self.add_departed_identity()
        state = replay('isolated', [self.holding_event(), self.holding_event(ticker='RENAMED',event_id='other')])
        with self.assertRaisesRegex(ValueError, 'RECORDED_TICKER_CONFLICT'):
            self.coverage(state)
        state = replay('isolated', [self.holding_event()])
        original = deepcopy(self.identity)
        for key,value,reason in [('security_id','wrong','IDENTITY_MAPPING_CHANGED'),
                                 ('ticker','RENAMED','IDENTITY_NOT_UNIQUE_OR_UNAVAILABLE')]:
            self.identity = deepcopy(original)
            self.identity['candidates'][-1][key] = value
            self.entry['identity_sha256'] = self.put('identity-release.json',self.identity)
            with self.assertRaisesRegex(ValueError, reason):
                self.coverage(state)
        self.identity = original
        self.entry['identity_sha256'] = self.put('identity-release.json',self.identity)
        (self.root/'synthetic-evidence.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'IDENTITY_SOURCE_CHANGED'):
            self.coverage(state)

    def test_missing_month_and_new_york_boundary_do_not_fallback(self):
        for now in ['2027-01-01T15:00:00+00:00', '2026-12-01T02:00:00+00:00']:
            with self.subTest(now=now), self.assertRaisesRegex(ValueError, 'CURRENT_MONTH_RELEASE_REQUIRED'):
                self.resolve(now)

    def test_duplicate_month_refused(self):
        self.registry['entries'].append(dict(self.entry))
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_RELEASE_MONTH'):
            self.resolve()

    def test_active_open_not_reached(self):
        with self.assertRaisesRegex(ValueError, 'RELEASE_DECISION_BOUNDARY_INVALID'):
            self.resolve('2026-12-01T14:00:00+00:00')

    def test_receipt_time_status_and_binding_fail(self):
        for key, value in [('published_at', '2026-12-02T15:00:00+00:00'),
                           ('published_at', '2026-11-01T15:00:00+00:00'),
                           ('status', 'BLOCKED'), ('config_sha256', '0'*64)]:
            with self.subTest(key=key, value=value):
                receipt = dict(self.receipt, **{key: value})
                self.entry['publication_sha256'] = self.put('receipt.json', receipt)
                with self.assertRaises(ValueError):
                    self.resolve()

    def test_source_drift_and_registry_hash_fail(self):
        (self.root/'published/manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'REGISTRY_SOURCE_CHANGED'):
            self.resolve()
        with self.assertRaises(ValueError):
            resolve_monthly_runtime(root=self.root, registry_path='registry.json', registry_sha256='0'*64)

    def test_identity_issuer_mismatch_fails(self):
        self.identity['candidates'][0]['issuer_id'] = 'WRONG'
        self.entry['identity_sha256'] = self.put('identity-release.json', self.identity)
        with self.assertRaisesRegex(ValueError, 'RELEASE_IDENTITY_BINDING_MISMATCH'):
            self.resolve()

    def test_runtime_pin_drift_fails(self):
        path = sorted(RELEASE_PATHS)[0]
        (self.root/path).write_bytes(b'changed')
        self.entry['runtime_pins'][path] = sha256(b'changed').hexdigest()
        with self.assertRaisesRegex(ValueError, 'EXECUTING_COMPOSITION_SOURCE_CHANGED'):
            self.resolve()

    def test_unsafe_publication_path_fails(self):
        self.entry['publication_path'] = '../receipt.json'
        with self.assertRaises(ValueError):
            self.resolve()


if __name__ == '__main__':
    unittest.main()
