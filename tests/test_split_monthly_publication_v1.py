"""Capture through persisted target using disposable split/account journals."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from core.strategy_account_ledger import canonical
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_monthly_target_service import StrategyMonthlyTargetService, LIFECYCLE_PATHS
from docs.candidates.strategy_account_split_target_service import StrategyAccountTargetService, MINIMUM_RUNTIME_PATHS
import test_split_evidence_provider_v1 as fixtures


class SplitMonthlyPublicationTests(unittest.TestCase):
    def test_frozen_target_must_bind_latest_split_before_execution_capture(self):
        with TemporaryDirectory() as folder:
            monthly, provider, store, state, _ = self.case(folder)
            target = monthly.generate(event_id='initial', reason='INITIAL',
                expected_revision=state['revision'], previous_target_id=None)
            for mode in ('missing', 'action', 'unit'):
                changed = deepcopy(target)
                decision = changed['payload']['decision']
                binding = decision['payload']['input_binding']
                if mode == 'missing':
                    binding.pop('recorded_split_bindings')
                elif mode == 'action':
                    binding['recorded_split_bindings']['A']['action_sha256'] = '0'*64
                else:
                    binding['marks']['A']['unit_id'] = 'old'
                decision['payload']['input_id'] = sha256(canonical(binding)).hexdigest()
                decision['decision_id'] = sha256(canonical(decision['payload'])).hexdigest()
                captures = len(list(provider.output.iterdir()))
                with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'SPLIT_FROZEN_TARGET'):
                    provider.execution(state, changed)
                self.assertEqual(len(list(provider.output.iterdir())), captures)
            provider.limits = lambda **kwargs: {'limits': {sid: dict(security_id=sid,
                price_basis=mark['price_basis'], observed_at=mark['observed_at'], buy='9', sell='11')
                for sid, mark in kwargs['market_capture']['marks'].items()}}
            evidence = provider.execution(state, target)
            self.assertEqual(evidence['marks']['A']['unit_id'], 'new')
            self.assertEqual(store.read(), state)

    def test_candidate_source_drift_is_rejected_before_capture(self):
        with TemporaryDirectory() as folder:
            monthly, provider, store, state, _ = self.case(folder)
            path = provider.root / 'docs/candidates/strategy_account_split_target_inputs.py'
            path.write_bytes(path.read_bytes() + b'\n# drift\n')
            monthly.selection.provider = Mock(side_effect=AssertionError('source drift must stop before capture'))
            with self.assertRaisesRegex(ValueError, 'RUNTIME_SOURCE_CHANGED'):
                monthly.generate(event_id='initial', reason='INITIAL', expected_revision=state['revision'], previous_target_id=None)
            self.assertIsNone(monthly.targets.current())
            self.assertEqual(store.read(), state)
            monthly.selection.provider.assert_not_called()

    def case(self, folder):
        provider, state, now = fixtures.SplitEvidenceProviderTests().case(folder)
        root = Path(__file__).resolve().parents[1]
        pins = {}
        for name in MINIMUM_RUNTIME_PATHS | LIFECYCLE_PATHS:
            raw = (root / name).read_bytes()
            path = provider.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        store = SplitStrategyAccountStore(Path(folder)/'account.sqlite3', clock=lambda: now[0])
        current = store.initialize(state['account_id'], operation_id='temporary-test')
        for row in state['events']:
            current, _ = store.append(row['payload'], expected_revision=current['revision'])
        self.assertEqual(current, state)
        selection = StrategyAccountTargetService(store=store, evidence_provider=provider.selection,
            runtime_root=provider.root, runtime_pins=pins, maximum_mark_age_seconds=900,
            execution_fee_bps='0', clock=lambda: now[0])
        targets = StrategyMonthlyTargetStore(Path(folder)/'targets.sqlite3')
        execution = Mock(side_effect=AssertionError('target selection does not execute'))
        monthly = StrategyMonthlyTargetService(selection_service=selection, target_store=targets,
            execution_provider=execution, clock=lambda: now[0])
        return monthly, provider, store, state, execution

    def test_capture_search_publish_restart_read_and_retry(self):
        with TemporaryDirectory() as folder:
            monthly, provider, store, state, execution = self.case(folder)
            request = dict(event_id='initial', reason='INITIAL', expected_revision=state['revision'], previous_target_id=None)
            result = monthly.generate(**request)
            payload = result['payload']
            self.assertEqual(payload['target_month'], '2026-11')
            self.assertEqual(payload['decision']['core_calls'], 1)
            self.assertEqual(payload['decision']['payload']['input_binding']['strategy_shares']['A'], 16)
            self.assertEqual(payload['target_quantities'], payload['decision']['payload']['search_result']['selected']['quantities'])
            self.assertTrue(payload['decision']['execution_blocked'])
            self.assertEqual(StrategyMonthlyTargetStore(monthly.targets.path).current(), result)
            monthly.selection.provider = Mock(side_effect=AssertionError('retry must not repeat capture/search'))
            self.assertEqual(monthly.generate(**request), result)
            self.assertEqual(len(monthly.targets.history()), 1)
            self.assertEqual(store.read(), state)
            execution.assert_not_called()

    def test_changed_cash_during_capture_cannot_publish_target(self):
        with TemporaryDirectory() as folder:
            monthly, provider, store, state, _ = self.case(folder)
            def changing(snapshot):
                evidence = provider.selection(snapshot)
                store.append(dict(event_id='cash-changed', kind='CASH_CONFIRM', amount='70',
                    cash_basis='AVAILABLE_AFTER_RESERVATIONS'), expected_revision=state['revision'])
                return evidence
            monthly.selection.provider = changing
            with self.assertRaisesRegex(ValueError, 'ACCOUNT_CHANGED_DURING_TARGET'):
                monthly.generate(event_id='initial', reason='INITIAL', expected_revision=state['revision'], previous_target_id=None)
            self.assertIsNone(monthly.targets.current())
            self.assertIsNone(monthly.selection.current)


if __name__ == '__main__':
    unittest.main()
