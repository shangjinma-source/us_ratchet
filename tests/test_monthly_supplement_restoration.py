"""Full-month restoration reaches the real risk store; no live account writes."""
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_monthly_supplement_capture import restore_reviewed_monthly_history
from data.monthly_cap_exit_packet import apply_cap_exit_packet
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.monthly_cap_exit_reader_v2 import MonthlyCapExitReaderV2
from data.strategy_daily_rebound_archive import archive_rebound_evidence
import test_monthly_cap_topup_packet as fixture


class MonthlyRestorationTests(unittest.TestCase):
    def case(self):
        selected = fixture.target(20000, {'A': 180})
        full = fixture.packet(selected, {'A': [100, 80, 110]})
        days = [(date(2026, 10, 1) + timedelta(days=n)).isoformat()
                for n in range(30)
                if (date(2026, 10, 1) + timedelta(days=n)).weekday() < 5]
        self.assertEqual(len(days), 22)
        full['session_dates'] = days
        full['signal_date'] = days[-1]
        full['observed_at'] = days[-1] + 'T21:00:00+00:00'
        full['base_target']['monthly_decision_date'] = days[0]
        full['session_close_times']['closes'] = {d: d+'T20:00:00+00:00' for d in days}
        full['histories']['A']['units']['unit_asof'] = days[-1]
        full['histories']['A']['closes'] = [dict(date=d,
            completed_at=d+'T20:00:00+00:00', close=str(v))
            for d, v in zip(days, [100, 80] + [110]*20)]
        short = deepcopy(full)
        short['histories']['A']['closes'] = short['histories']['A']['closes'][-20:]
        return selected, full, short

    def restore(self, full, short):
        files = {'short.json': canonical(short), 'full.json': canonical(full)}
        hashes = {name: sha256(raw).hexdigest() for name, raw in files.items()}
        receipt = dict(normalized_inputs_path='short.json', source_sha256=hashes,
            monthly_history_inputs={'A': dict(path='full.json', sha256=hashes['full.json'])})
        return restore_reviewed_monthly_history(receipt=receipt, files=files,
            decision_date=short['base_target']['monthly_decision_date'])

    def test_early_exit_outside_twenty_rows_reaches_persistent_risk(self):
        selected, full, short = self.case()
        restored = self.restore(full, short)
        with TemporaryDirectory() as folder:
            store = MonthlyPeakExitStore(Path(folder)/'risk.sqlite')
            kwargs = dict(target=selected, risk_store=store, account_id='isolated',
                decision_date=full['session_dates'][0], expected_previous_session=None)
            with self.assertRaisesRegex(ValueError, 'CAP_COMPLETE_MONTHLY_HISTORY_REQUIRED'):
                apply_cap_exit_packet(inputs=short, **kwargs)
            result = apply_cap_exit_packet(inputs=restored, **kwargs)
            self.assertEqual(result['effective_target_quantities'], {'A': 0})
            self.assertTrue(result['signal_explanations']['A']['exited'])
            self.assertEqual(len(short['histories']['A']['closes']), 20)

    def test_rejects_conflicting_full_month_even_with_updated_content_hash(self):
        _, full, short = self.case()
        for field, error in [('price', 'PRICE_CHANGED'), ('units', 'UNITS_CHANGED'),
                             ('calendar', 'CALENDAR_CHANGED')]:
            with self.subTest(field=field):
                changed = deepcopy(full)
                if field == 'price': changed['histories']['A']['closes'][-1]['close'] = '111'
                if field == 'units': changed['histories']['A']['units']['basis_id'] = 'other'
                if field == 'calendar': changed['session_dates'] = changed['session_dates'][1:]
                with self.assertRaisesRegex(ValueError, error):
                    self.restore(changed, short)

    def test_reader_consumes_archived_monthly_rows_and_rejects_tampering(self):
        selected, full, short = self.case()
        for inputs in (full, short):
            inputs['base_target']['monthly_target_created_at'] = '2026-10-01T14:00:00+00:00'
        account = dict(account_id='isolated', revision='fixture-revision')
        files = {'short.json': canonical(short), 'full.json': canonical(full)}
        hashes = {name: sha256(raw).hexdigest() for name, raw in files.items()}
        receipt = dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',
            target_id=selected['target_id'], account_revision=account['revision'],
            normalized_inputs_path='short.json', source_sha256=hashes,
            monthly_history_inputs={'A': dict(path='full.json', sha256=hashes['full.json'])})
        with TemporaryDirectory() as folder:
            root = Path(folder)
            archive = archive_rebound_evidence(root=root/'source',
                receipt_bytes=canonical(receipt), files=files)
            validations = []
            # Source admission is stubbed: this tests reader/archive/risk integration only.
            reader = MonthlyCapExitReaderV2(
                source_reader=lambda *args: dict(signal={'policy_id': 'fixture'}, evidence_archive=archive),
                risk_store=MonthlyPeakExitStore(root/'risk.sqlite'),
                source_archive_root=root/'source', output_archive_root=root/'projected',
                release_bytes=b'fixture-release', validate_release=lambda: validations.append(True))
            result = reader(account, selected, full['observed_at'])
            self.assertEqual(result['signal']['effective_target_quantities'], {'A': 0})
            self.assertEqual(len(validations), 2)
            self.assertTrue(Path(result['evidence_archive']['complete_path']).is_file())
            risk_before = reader.risk_store.read('isolated')
            source_file = Path(archive['receipt_path']).parent/'sources'/(hashes['full.json']+'.bin')
            source_file.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'CAP_SOURCE_BYTES_CHANGED'):
                reader(account, selected, full['observed_at'])
            self.assertEqual(reader.risk_store.read('isolated'), risk_before)


if __name__ == '__main__':
    unittest.main()
