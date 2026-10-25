from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from core.strategy_account_store import StrategyAccountStore
from data.strategy_continuous32_target_service import (
    StrategyContinuous32TargetService, MINIMUM_RUNTIME_PATHS, PROFILE_ID,
)
import test_strategy_account_evidence_provider as provider_fixtures

ROOT = Path(__file__).resolve().parents[1]


class ContinuousServiceTests(unittest.TestCase):
    def fixture(self, directory, selection_only=False):
        provider, state, now, sources = provider_fixtures.ProviderTests().fixture(directory)
        pins = {}
        for name in MINIMUM_RUNTIME_PATHS:
            raw = (ROOT / name).read_bytes()
            path = sources / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        store = StrategyAccountStore(Path(directory) / 'account.sqlite3', clock=lambda: now[0])
        store.initialize(state['account_id'], operation_id='init')
        for row in state['events']:
            store.append(row['payload'], expected_revision=store.read()['revision'])
        service = StrategyContinuous32TargetService(
            store=store, evidence_provider=provider.selection if selection_only else provider,
            runtime_root=sources, runtime_pins=pins, maximum_mark_age_seconds=120,
            execution_fee_bps='0', clock=lambda: now[0])
        return service, store, provider, now

    def test_real_provider_sqlite_select_without_execution_or_mutation(self):
        with TemporaryDirectory() as directory:
            service, store, provider, now = self.fixture(directory, True)
            before = store.path.read_bytes()
            with patch.object(provider, 'limits', side_effect=AssertionError('selection has no orders')):
                result = service.select()
            self.assertEqual(result['status'], 'READY', result)
            self.assertEqual(result['selector_profile'], PROFILE_ID)
            decision, limits, state = service.current
            self.assertIsNone(limits)
            self.assertEqual(decision['payload']['input_binding']['account_revision'], state['revision'])
            self.assertEqual(decision['payload']['input_binding']['strategy_equity'], '120')
            self.assertEqual(store.path.read_bytes(), before)
            # The original bound execution provider accepts the new immutable
            # decision without relabelling its method or repeating selection.
            def limits(**options):
                return {'limits': {sid: dict(security_id=sid, price_basis=mark['price_basis'],
                    observed_at=mark['observed_at'], buy='9', sell='11')
                    for sid, mark in options['market_capture']['marks'].items()}}
            provider.limits = limits
            frozen = deepcopy(decision)
            evidence = provider.execution(state, {'payload': {'decision': decision}})
            self.assertIn('limits', evidence)
            self.assertEqual(decision, frozen)
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(service.preview()['reason'], 'EXECUTION_LIMITS_REQUIRED')

    def test_actual_generate_preview_then_cash_change_is_rejected(self):
        with TemporaryDirectory() as directory:
            service, store, _, _ = self.fixture(directory)
            before = store.path.read_bytes()
            result = service.generate()
            self.assertEqual(result['status'], 'READY', result)
            self.assertEqual(service.preview()['status'], 'READY')
            self.assertEqual(store.path.read_bytes(), before)
            store.append(dict(event_id='new-cash', kind='CASH_CONFIRM', amount='81',
                              cash_basis='AVAILABLE_AFTER_RESERVATIONS'),
                         expected_revision=store.read()['revision'])
            self.assertEqual(service.preview()['reason'], 'ACCOUNT_CHANGED_DURING_TARGET')
            self.assertIsNone(service.current)

    def test_profile_tampering_expiry_and_pin_change(self):
        for mode in ('profile', 'expired', 'pin'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                service, _, _, now = self.fixture(directory)
                self.assertEqual(service.generate()['status'], 'READY')
                if mode == 'profile':
                    service.current[0]['payload']['input_binding']['selector_profile'] = 'OTHER'
                elif mode == 'expired':
                    now[0] += timedelta(seconds=121)
                else:
                    (service.root / 'data/strategy_continuous32_target_service.py').write_text('changed')
                result = service.preview()
                self.assertNotEqual(result['status'], 'READY')
                self.assertIsNone(service.current)

    def test_source_conflict_rejected_before_search(self):
        with TemporaryDirectory() as directory:
            service, _, provider, _ = self.fixture(directory)
            def conflict(state):
                evidence = provider(state)
                evidence['source_package']['source_hashes']['data/strategy_continuous32_target_decision.py'] = '0'*64
                return evidence
            service.provider = conflict
            with patch('data.strategy_continuous32_target_service.decide_target') as selector:
                result = service.select()
            self.assertEqual(result['reason'], 'CONTINUOUS32_SOURCE_CONFLICT')
            selector.assert_not_called()


if __name__ == '__main__':
    unittest.main()
