from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_prospective_paper_cap_daily_v1 import CODE_PATHS, project_paper_cap_daily
from data.strategy_prospective_paper_daily_v1 import verify_prospective_daily
from test_strategy_prospective_paper_integration_v1 import fixture


class PaperCapDailyTests(unittest.TestCase):
    def test_admitted_next_session_projection_and_rejected_sources(self):
        with TemporaryDirectory() as folder:
            release = canonical(dict(schema='PAPER_CAP_EXIT_PROJECTION_RELEASE_V1',
                policy_id='MONTHLY_CAP50_EXIT20', approved=True, orders_allowed=False,
                approved_at='2026-11-03T14:58:00+00:00'))
            session = dict(date='2026-11-04', open='2026-11-04T14:30:00+00:00',
                           close='2026-11-04T21:00:00+00:00')
            args = fixture(folder, extra_code_paths=CODE_PATHS,
                extra_sources={'policy/cap.json': release}, extra_sessions=[session])
            store = MonthlyPeakExitStore(Path(folder) / 'risk.sqlite')
            def run(value):
                return project_paper_cap_daily(daily_arguments=value, risk_store=store,
                                              cap_release_path='policy/cap.json')
            self.assertEqual(run(args)['status'], 'WAIT_FIRST_CONFIGURATION_CLOSE')
            self.assertFalse(store.path.exists())
            inputs = json.loads(args['files']['normalized.json'])
            inputs['signal_date'] = '2026-11-03'
            inputs['observed_at'] = '2026-11-03T21:00:00+00:00'
            inputs['session_dates'].append('2026-11-03')
            inputs['session_close_times']['closes']['2026-11-03'] = inputs['observed_at']
            for history in inputs['histories'].values():
                history['closes'] = history['closes'][1:] + [dict(date='2026-11-03',
                    completed_at=inputs['observed_at'], close='101')]
                history['units']['unit_asof'] = '2026-11-03'
            args['files']['normalized.json'] = canonical(inputs)
            monthly = deepcopy(inputs)
            monthly['base_target']['monthly_decision_date'] = '2026-11-03'
            args['files']['monthly.json'] = canonical(monthly)
            args['now'] = '2026-11-04T15:00:10+00:00'
            receipt = json.loads(args['receipt_bytes'])
            receipt.update(available_at='2026-11-04T15:00:02+00:00',
                source_received_at='2026-11-04T15:00:01+00:00',
                valid_from='2026-11-04T15:00:02+00:00', valid_until=session['close'],
                execution_session=session, market_asof=inputs['observed_at'],
                monthly_history_inputs={'B': dict(path='monthly.json',
                    sha256=sha256(args['files']['monthly.json']).hexdigest())},
                source_sha256={p: sha256(raw).hexdigest() for p, raw in args['files'].items()})
            args['receipt_bytes'] = canonical(receipt)
            args['trusted_receipt_sha256'] = sha256(args['receipt_bytes']).hexdigest()
            before = deepcopy(args)
            self.assertEqual(verify_prospective_daily(**args)['signal']['effective_target_quantities'], {'B': 20})
            result = run(args)
            self.assertEqual(result['status'], 'PAPER_CAP_EXIT_PROJECTION_READY')
            self.assertEqual(result['projection']['effective_target_quantities'], {'B': 10})
            self.assertEqual(args, before)
            namespace = result['projection']['risk_namespace']
            saved = store.read(namespace)
            bad = deepcopy(args)
            bad['files']['normalized.json'] += b' '
            with self.assertRaisesRegex(ValueError, 'DAILY_SOURCE_HASH_MISMATCH'):
                run(bad)
            bad = deepcopy(args)
            changed = dict(receipt, account_revision='foreign')
            bad['receipt_bytes'] = canonical(changed)
            bad['trusted_receipt_sha256'] = sha256(bad['receipt_bytes']).hexdigest()
            with self.assertRaisesRegex(ValueError, 'DAILY_RECEIPT_BINDING_MISMATCH'):
                run(bad)
            # Even a newly reviewed digest must not override overlapping prices
            # or unit/calendar evidence in the daily packet.
            for mode in ('price', 'units', 'calendar'):
                bad = deepcopy(args)
                conflict = deepcopy(monthly)
                if mode == 'price':
                    conflict['histories']['B']['closes'][-1]['close'] = '102'
                elif mode == 'units':
                    conflict['histories']['B']['units']['basis_id'] = 'other'
                else:
                    conflict['base_target']['monthly_decision_date'] = '2026-11-02'
                bad['files']['monthly.json'] = canonical(conflict)
                changed = deepcopy(receipt)
                digest = sha256(bad['files']['monthly.json']).hexdigest()
                changed['source_sha256']['monthly.json'] = digest
                changed['monthly_history_inputs']['B']['sha256'] = digest
                bad['receipt_bytes'] = canonical(changed)
                bad['trusted_receipt_sha256'] = sha256(bad['receipt_bytes']).hexdigest()
                with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_MONTHLY_'):
                    run(bad)
                self.assertEqual(store.read(namespace), saved)
            expired = dict(args, now='2026-11-04T21:00:00+00:00')
            self.assertEqual(run(expired)['status'], 'WAIT_FRESH_SIGNAL')
            self.assertEqual(store.read(namespace), saved)


if __name__ == '__main__':
    unittest.main()
