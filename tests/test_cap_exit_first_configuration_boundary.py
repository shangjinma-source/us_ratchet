"""Isolated V24 risk-reader boundary; not a live monthly execution acceptance."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from data.monthly_cap_exit_reader_v3 import MonthlyCapExitReaderV3
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_daily_rebound_archive import archive_rebound_evidence


class FirstConfigurationBoundaryTests(TestCase):
    def test_new_month_requires_configuration_close_not_training_cutoff(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            account = dict(account_id='isolated', revision='revision')
            target = dict(target_id='new-month', payload=dict(target_month='2026-12'))
            store = MonthlyPeakExitStore(root/'risk.sqlite')
            for signal_date, blocked in [('2026-11-30', True), ('2026-12-01', False)]:
                inputs = dict(signal_date=signal_date, base_target=dict(
                    monthly_target_created_at='2026-12-01T15:00:00+00:00',
                    monthly_decision_date='2026-11-30'))
                files = {'inputs.json': canonical(inputs)}
                receipt = dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',
                    account_revision=account['revision'], target_id=target['target_id'],
                    normalized_inputs_path='inputs.json',
                    source_sha256={name: sha256(body).hexdigest() for name, body in files.items()})
                archive = archive_rebound_evidence(root=root/'source',
                    receipt_bytes=canonical(receipt), files=files)
                reader = MonthlyCapExitReaderV3(
                    source_reader=lambda *args: dict(signal={}, evidence_archive=archive),
                    risk_store=store, source_archive_root=root/'source',
                    output_archive_root=root/'projected', release_bytes=b'fixture',
                    validate_release=lambda: None, risk_history=None)
                # Mock only the downstream projection: this tests admission dates,
                # not price verification, execution sizing or actual trade results.
                with patch('data.monthly_cap_exit_reader_v3.apply_cap_exit_packet',
                           return_value={'effective_target_quantities': {}}) as projection:
                    if blocked:
                        with self.assertRaisesRegex(ValueError, 'WAIT_FIRST_CONFIGURATION_CLOSE'):
                            reader(account, target, datetime.fromisoformat('2026-12-01T15:00:00+00:00'))
                        projection.assert_not_called()
                        self.assertFalse((root/'projected').exists())
                    else:
                        reader(account, target, datetime.fromisoformat('2026-12-02T15:00:00+00:00'))
                        self.assertEqual(projection.call_args.kwargs['decision_date'], '2026-12-01')
                self.assertIsNone(store.read(account['account_id']))
