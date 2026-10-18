from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from data.strategy_account_runtime import build_runtime, RUNTIME_PATHS, ACCOUNT_ID
from data.current_research_capital_decision_v2 import REQUIRED_PINS


class RuntimeTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        source = Path(__file__).resolve().parents[1]
        pins = {}
        for name in RUNTIME_PATHS:
            raw = (source/name).read_bytes()
            destination = root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        configuration = dict(schema='REAL_STRATEGY_RUNTIME_V1', target_month='2026-10',
            training_manifest='training.json', training_sha256='a'*64,
            training_closed_at='2026-10-14T20:00:00Z', identity_manifest='identity.json',
            identity_sha256='b'*64, runtime_pins=pins)
        return root, configuration

    def test_construction_and_reads_do_not_create_accounts_or_fetch(self):
        with TemporaryDirectory() as directory:
            root, configuration = self.fixture(directory)
            with patch('data.strategy_account_evidence_provider.StrategyAccountEvidenceProvider.__call__',
                       side_effect=AssertionError('no fetch')):
                service = build_runtime(root=root, configuration=configuration)
                self.assertIsNone(service.accounts.read())
                self.assertIsNone(service.current())
                provider = service.execution_provider.__self__
                self.assertEqual(provider.runtime_pins,
                                 {name: configuration['runtime_pins'][name] for name in REQUIRED_PINS})
            self.assertFalse((root/'data/strategy_account').exists())

    def test_next_month_cannot_relabel_saved_training_and_configuration_is_copied(self):
        with TemporaryDirectory() as directory:
            root, configuration = self.fixture(directory)
            now = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)
            service = build_runtime(root=root, configuration=configuration, clock=lambda: now)
            configuration['target_month'] = '2026-11'
            with patch('data.strategy_account_evidence_provider.StrategyAccountEvidenceProvider.__call__',
                       side_effect=AssertionError('must reject before fetch')):
                with self.assertRaisesRegex(ValueError, 'CURRENT_MONTH_TRAINING_DEPLOYMENT_REQUIRED'):
                    service.selection.provider({})
            self.assertFalse((root/'data/strategy_account').exists())

    def test_changed_source_and_wrong_account_rejected(self):
        with TemporaryDirectory() as directory:
            root, configuration = self.fixture(directory)
            service = build_runtime(root=root, configuration=configuration)
            service.accounts.initialize('other-account', operation_id='test-init')
            with self.assertRaisesRegex(ValueError, 'ACCOUNT_SCOPE_MISMATCH'):
                service.accounts.read()
            (root/'data/strategy_account_runtime.py').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'RUNTIME_SOURCE_CHANGED'):
                build_runtime(root=root, configuration=configuration)


if __name__ == '__main__':
    unittest.main()
