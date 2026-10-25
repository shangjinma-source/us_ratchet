from copy import deepcopy
from contextlib import closing
from pathlib import Path
import sqlite3
import json
from tempfile import TemporaryDirectory
import unittest

from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.monthly_peak_exit_history import monthly_exit_observations
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.saved_frontier_exit_packet_v1 import apply_frontier_exit_packet
from test_saved_monthly_frontier_proposal import native_fixture
from test_monthly_cap_topup_packet import packet, DAYS


class FrontierExitPacketTests(unittest.TestCase):
    def test_new_month_requires_explicit_reset_and_retains_price_history(self):
        target = native_fixture()
        proposal = build_frontier_proposal(target=target)
        account = target['payload']['account_id']
        current = packet(target, {'A': [100, 105, 110], 'B': [100, 105, 110]})
        current['base_target'].update(origin_reference=proposal['proposal_id'],
            quantities=proposal['payload']['proposed_target_quantities'])
        old = json.loads(json.dumps(current).replace('2026-10-', '2026-09-'))
        with TemporaryDirectory() as folder:
            store = MonthlyPeakExitStore(Path(folder) / 'risk.sqlite')
            store.advance(account_id=account, expected_previous_session=None,
                observations=monthly_exit_observations(**old), baseline_targets={'A': 99, 'B': 99},
                target_month='2026-09')
            kwargs = dict(target=target, proposal=proposal, inputs=current, risk_store=store,
                account_id=account, decision_date=DAYS[0], expected_previous_session='2026-09-22')
            with self.assertRaisesRegex(ValueError, 'FRONTIER_MONTHLY_RESET_BINDING'):
                apply_frontier_exit_packet(**kwargs)
            result = apply_frontier_exit_packet(**kwargs, authorized_monthly_reset=DAYS[0])
            self.assertEqual(result['state']['target_month'], '2026-10')
            self.assertTrue(store.recorded_prices(account, '2026-09-20'))
            self.assertTrue(store.recorded_prices(account, DAYS[0]))

    def test_real_store_expansion_preserves_exited_and_all_tables(self):
        target = native_fixture()
        proposal = build_frontier_proposal(target=target)
        account = target['payload']['account_id']
        def inputs(histories):
            value = packet(target, histories)
            value['base_target']['origin_reference'] = proposal['proposal_id']
            value['base_target']['quantities'] = {sid: proposal['payload']['proposed_target_quantities'].get(sid, 0)
                                                  for sid in histories}
            return value
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'risk.sqlite'
            store = MonthlyPeakExitStore(path)
            initial = inputs({'A': [100, 80, 110]})
            store.advance(account_id=account, expected_previous_session=None,
                observations=monthly_exit_observations(**initial), baseline_targets={'A': 99}, target_month='2026-10')
            kwargs = dict(target=target, proposal=proposal, risk_store=store, account_id=account,
                decision_date=DAYS[0], expected_previous_session=DAYS[-1])
            full = inputs({'A': [100, 80, 110], 'B': [100, 105, 110]})
            broken = deepcopy(full)
            broken['histories']['B']['closes'] = broken['histories']['B']['closes'][1:]
            before = store.read(account)
            with self.assertRaisesRegex(ValueError, 'CAP_COMPLETE_MONTHLY_HISTORY_REQUIRED'):
                apply_frontier_exit_packet(**kwargs, inputs=broken)
            self.assertEqual(store.read(account), before)
            result = apply_frontier_exit_packet(**kwargs, inputs=full)
            self.assertEqual(result['effective_target_quantities'], {'A': 0, 'B': 99})
            self.assertIn('A', result['state']['exited'])
            with closing(sqlite3.connect(path)) as connection:
                for table in ('risk_state', 'risk_prices', 'risk_domain_evidence'):
                    self.assertGreater(connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0], 0)
            with self.assertRaisesRegex(ValueError, 'FRONTIER_RISK_DOMAIN_INCOMPLETE'):
                apply_frontier_exit_packet(**kwargs, inputs=inputs({'B': [100, 105, 110]}))
            with self.assertRaisesRegex(ValueError, 'FRONTIER_SAME_MONTH_EPOCH_CHANGED'):
                apply_frontier_exit_packet(**dict(kwargs, decision_date=DAYS[1]), inputs=full)
