"""New-month native quantities on the actual split-prepared risk database.

This tests the risk boundary only, not source admission or the monthly selector.
"""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest

import test_split_three_clock_daily_20261105 as split_fixture
import test_saved_monthly_frontier_proposal as target_fixture
import test_monthly_cap_topup_packet as packet_fixture
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.saved_frontier_exit_packet_v1 import apply_frontier_exit_packet

ROOT = Path(__file__).resolve().parents[1]


class Tests(unittest.TestCase):
    def test_native_new_month_resets_risk_without_resplitting_target_or_history(self):
        with TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            _, accounts, arguments = split_fixture.Tests().case(folder, 'AS_TRADED')
            store = MonthlyPeakExitStore(arguments['risk_path'])
            account = accounts.read()['account_id']
            previous = store.read(account)
            old_prices = store.recorded_prices(account, previous['decision_date'])
            with closing(sqlite3.connect(arguments['risk_path'])) as connection:
                old_preparation = connection.execute('SELECT payload,digest FROM split_preparation').fetchall()
            target = target_fixture.native_fixture(month='2026-11')
            target['payload']['account_id'] = account
            target['payload']['decision']['payload']['input_binding']['account_id'] = account
            target_fixture.sign(target)
            proposal = build_frontier_proposal(target=target)
            domain = set(previous['peaks']) | set(proposal['payload']['proposed_target_quantities'])
            inputs = packet_fixture.packet(target, {sid: [100, 105, 110] for sid in domain})
            inputs = json.loads(json.dumps(inputs).replace('2026-10-', '2026-11-'))
            inputs['base_target'].update(origin_reference=proposal['proposal_id'],
                quantities={sid: proposal['payload']['proposed_target_quantities'].get(sid, 0) for sid in domain})
            for sid, history in inputs['histories'].items():
                unit = previous['unit_ids'].get(sid, 'unit-' + sid)
                inputs['base_target']['price_units'][sid] = unit
                history['units']['basis_id'] = unit
            values = dict(target=target, proposal=proposal, inputs=inputs, risk_store=store,
                account_id=account, decision_date='2026-11-20',
                expected_previous_session=previous['session_date'])
            with self.assertRaisesRegex(ValueError, 'FRONTIER_MONTHLY_RESET_BINDING'):
                apply_frontier_exit_packet(**values)
            self.assertEqual(store.read(account), previous)
            result = apply_frontier_exit_packet(**values, authorized_monthly_reset='2026-11-20')
            self.assertEqual(result['state']['target_month'], '2026-11')
            self.assertEqual(result['state']['unit_ids']['A'], 'unit-A8')
            self.assertEqual(result['state']['exited'], [])
            self.assertEqual(result['effective_target_quantities'], inputs['base_target']['quantities'])
            self.assertEqual(result['effective_target_quantities']['A'], proposal['payload']['proposed_target_quantities']['A'])
            self.assertEqual(store.recorded_prices(account, previous['decision_date']), old_prices)
            with closing(sqlite3.connect(arguments['risk_path'])) as connection:
                self.assertEqual(connection.execute('SELECT payload,digest FROM split_preparation').fetchall(), old_preparation)
            values['expected_previous_session'] = result['state']['session_date']
            repeated = apply_frontier_exit_packet(**values)
            self.assertEqual(repeated['state'], result['state'])
            self.assertEqual(repeated['effective_target_quantities'], result['effective_target_quantities'])


if __name__ == '__main__':
    unittest.main()
