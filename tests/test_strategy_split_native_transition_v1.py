from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from api.strategy_account_split_v1 import SplitStrategyAccountService
from core.strategy_account_store import StrategyAccountStore
from core.monthly_peak_exit import advance_monthly_exit
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.strategy_account_split_migration_v1 import prepare_split_account
from data.strategy_split_native_projection_v1 import project_native_split
from test_saved_monthly_frontier_proposal import native_fixture


class NativeSplitTransitionTests(unittest.TestCase):
    def test_migrated_ledger_native_target_cost_and_risk_share_one_unit_transition(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            clock = lambda: datetime.fromisoformat('2026-10-29T15:00:00+00:00')
            old = StrategyAccountStore(root/'old.sqlite3', clock=clock)
            state = old.initialize('synthetic-account', operation_id='init')
            state, _ = old.append(dict(event_id='buy', kind='DIRECT_FILL', security_id='A', side='BUY',
                quantity=14, price='100', fees='0', executed_at='2026-10-20T15:00:00Z'), expected_revision=state['revision'])
            original_bytes = old.path.read_bytes()
            prepare_split_account(source_path=old.path, destination_path=root/'new.sqlite3', expected_revision=state['revision'])
            service = SplitStrategyAccountService(database_path=root/'new.sqlite3', account_id='synthetic-account',
                clock=clock, resolver=lambda ticker: None)
            event = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='action', security_id='A', ratio=8,
                effective_at='2026-10-29T13:30:00Z', broker_confirmed_at='2026-10-29T13:31:00Z',
                old_unit_id='old', new_unit_id='new', evidence_sha256='a'*64)
            after, _ = service.store.append(event, expected_revision=state['revision'])
            target = native_fixture()
            original_target = deepcopy(target)
            proposal = build_frontier_proposal(target=target)
            risk = advance_monthly_exit(state=None, account_id='synthetic-account', decision_date='2026-10-20',
                session_date='2026-10-20', closes={'A':'100','B':'100','C':'50'},
                unit_ids={'A':'old','B':'b','C':'c'}, baseline_targets=proposal['payload']['proposed_target_quantities'])['state']
            result = project_native_split(account_after=after, action_id='action', risk_before=risk,
                                          target=target, expected_proposal_id=proposal['proposal_id'])
            projected = result['payload']['risk_projection']
            self.assertEqual(projected['target_quantities'], {'A':792,'B':99})
            self.assertEqual(result['payload']['projected_original_quantities'], {'A':1592})
            current = advance_monthly_exit(state=projected['risk_state'], account_id='synthetic-account',
                decision_date='2026-10-20', session_date='2026-10-29', closes={'A':'12.5','B':'100','C':'50'},
                unit_ids={'A':'new','B':'b','C':'c'}, baseline_targets=projected['target_quantities'])
            self.assertEqual(current['effective_target_quantities'], {'A':792,'B':99})
            view = service.read()['account']
            self.assertEqual(view['holding_costs'][0]['quantity'], 112)
            self.assertEqual(view['holding_costs'][0]['total_cost'], '1400')
            self.assertEqual(view['holding_costs'][0]['average_cost'], '25/2')
            self.assertEqual(len(view['fills']), 1)
            self.assertFalse(view['cash_confirmation_valid'])
            self.assertEqual(old.path.read_bytes(), original_bytes)
            self.assertEqual(target, original_target)
            with self.assertRaisesRegex(ValueError, 'STALE_PROPOSAL'):
                project_native_split(account_after=after, action_id='action', risk_before=risk,
                                     target=target, expected_proposal_id='stale')
            corrupted = deepcopy(target)
            corrupted['payload']['target_quantities']['A'] += 1
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_NATIVE_ID_CHANGED'):
                project_native_split(account_after=after, action_id='action', risk_before=risk,
                                     target=corrupted, expected_proposal_id=proposal['proposal_id'])
