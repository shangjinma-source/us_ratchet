"""Candidate epoch behavior; no production account or clock changes."""
from datetime import datetime
from unittest import TestCase
from data.monthly_risk_epoch import initial_completed_risk_session, validate_monthly_epoch


class EpochTests(TestCase):
    def test_previous_month_only_final_trading_close_allowed(self):
        dates = ['2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03', '2026-12-01']
        for day in ['2026-10-30', '2026-11-02']:
            validate_monthly_epoch(decision_date=day,target_month='2026-11',session_dates=dates)
        for day in ['2026-10-29', '2026-12-01']:
            with self.assertRaisesRegex(ValueError,'RISK_EPOCH_MONTH_BOUNDARY'):
                validate_monthly_epoch(decision_date=day,target_month='2026-11',session_dates=dates)

    def setUp(self):
        self.created = '2026-12-01T15:00:00+00:00'
        self.target = {'payload': {'created_at': self.created}}
        self.inputs = dict(base_target=dict(monthly_target_created_at=self.created,
            monthly_decision_date='2026-10-14'), signal_date='2026-11-30',
            session_dates=['2026-11-30', '2026-12-01', '2026-12-02'],
            session_close_times={'closes': {day: day+'T21:00:00+00:00'
                for day in ['2026-11-30', '2026-12-01', '2026-12-02']}})

    def epoch(self, now='2026-12-01T15:00:00+00:00'):
        return initial_completed_risk_session(inputs=self.inputs, target=self.target,
            now=datetime.fromisoformat(now))

    def test_first_intraday_selection_uses_prior_completed_close(self):
        self.assertEqual(self.epoch(), '2026-11-30')

    def test_delayed_refresh_keeps_selection_epoch(self):
        self.inputs['signal_date'] = '2026-12-01'
        self.assertEqual(self.epoch('2026-12-02T15:00:00+00:00'), '2026-11-30')

    def test_after_close_selection_uses_that_close(self):
        created = '2026-12-01T21:01:00+00:00'
        self.inputs['base_target']['monthly_target_created_at'] = created
        self.target['payload']['created_at'] = created
        self.inputs['signal_date'] = '2026-12-01'
        self.assertEqual(self.epoch(created), '2026-12-01')

    def test_creation_binding_cannot_be_rewritten(self):
        self.inputs['base_target']['monthly_target_created_at'] = '2026-11-30T22:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'RISK_CREATION_BINDING'):
            self.epoch()

    def test_future_creation_and_stale_signal_rejected(self):
        with self.assertRaisesRegex(ValueError, 'RISK_CREATION_TIME'):
            self.epoch('2026-12-01T14:00:00+00:00')
        with self.assertRaisesRegex(ValueError, 'LATEST_COMPLETED_SIGNAL_REQUIRED'):
            self.epoch('2026-12-02T15:00:00+00:00')

    def test_no_prior_completed_close_does_not_fall_back_to_training(self):
        self.inputs['session_dates'] = ['2026-12-01', '2026-12-02']
        self.inputs['signal_date'] = '2026-12-01'
        with self.assertRaisesRegex(ValueError, 'RISK_SELECTION_CLOSE_REQUIRED'):
            self.epoch('2026-12-02T15:00:00+00:00')


class ReaderContinuityTests(TestCase):
    def test_first_day_then_exit_rebound_and_new_capital_keep_exit(self):
        from hashlib import sha256
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from core.strategy_account_ledger import canonical
        from data.monthly_cap_exit_reader_v4 import MonthlyCapExitReaderV4
        from data.monthly_peak_exit_store import MonthlyPeakExitStore
        from data.strategy_daily_rebound_archive import archive_rebound_evidence
        from test_monthly_peak_exit_history import MonthlyHistoryTests

        def target(created, quantity):
            binding = dict(strategy_equity='4000', search_arguments=dict(
                entered_cash='4000', prices={'A': '100'}))
            selected = dict(input_binding=binding, input_id=sha256(canonical(binding)).hexdigest(),
                target_quantities={'A': quantity})
            payload = dict(account_id='test', target_month='2026-10', created_at=created,
                target_quantities={'A': quantity}, decision=dict(payload=selected,
                decision_id=sha256(canonical(selected)).hexdigest()))
            return dict(payload=payload, target_id=sha256(canonical(payload)).hexdigest())

        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = MonthlyPeakExitStore(root/'risk.sqlite')
            account = dict(account_id='test', revision='isolated')
            monthly = target('2026-10-02T14:00:00+00:00', 10)
            for now, signal, quantity in [
                ('2026-10-02T14:00:00+00:00', '2026-10-01', 10),
                ('2026-10-05T14:00:00+00:00', '2026-10-02', 0),
                ('2026-10-06T14:00:00+00:00', '2026-10-05', 0),
            ]:
                if signal == '2026-10-05':
                    monthly = target(now, 20)  # Same-month added capital/new target.
                inputs = MonthlyHistoryTests().inputs()
                inputs['observed_at'] = now
                inputs['signal_date'] = signal
                inputs['base_target'].update(origin_reference=monthly['target_id'],
                    monthly_target_created_at=monthly['payload']['created_at'])
                history = inputs['histories']['A']
                history['units']['unit_asof'] = signal
                history['closes'] = [row for row in history['closes'] if row['date'] <= signal]
                files = {'inputs.json': canonical(inputs)}
                receipt = dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',
                    account_revision=account['revision'], target_id=monthly['target_id'],
                    normalized_inputs_path='inputs.json',
                    source_sha256={name: sha256(raw).hexdigest() for name, raw in files.items()})
                archive = archive_rebound_evidence(root=root/'source',
                    receipt_bytes=canonical(receipt), files=files)
                reader = MonthlyCapExitReaderV4(source_reader=lambda *args:
                    dict(signal={}, evidence_archive=archive), risk_store=store,
                    source_archive_root=root/'source', output_archive_root=root/'output',
                    release_bytes=b'isolated', validate_release=lambda: None, risk_history=None)
                first = reader(account, monthly, datetime.fromisoformat(now))
                self.assertEqual(first['signal']['effective_target_quantities'], {'A': quantity})
                saved = store.read('test')
                self.assertEqual(saved['decision_date'], '2026-10-01')
                reader(account, monthly, datetime.fromisoformat(now))
                self.assertEqual(store.read('test'), saved, 'repeat refresh must retain risk state')
            self.assertEqual(store.read('test')['exited'], ['A'])
