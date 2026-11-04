from contextlib import closing
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import create_account
from core.strategy_account_split_v1 import apply_event
from core.monthly_peak_exit import advance_monthly_exit
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_split_risk_preparation_v1 import prepare_split_risk
from test_saved_monthly_frontier_proposal import native_fixture


class SplitRiskPreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.destination = Path(self.directory.name)/'prepared.sqlite3'
        target = native_fixture(); proposal = build_frontier_proposal(target=target)
        state = create_account('synthetic-account')
        action = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='action', security_id='A', ratio=8,
            effective_at='2026-10-29T13:30:00Z', broker_confirmed_at='2026-10-29T13:31:00Z',
            old_unit_id='old', new_unit_id='new', evidence_sha256='a'*64)
        account, _ = apply_event(state, action, expected_revision=state['revision'])
        rows = [dict(decision_date='2026-10-20', session_date=day, closes={'A':price,'B':'100'},
                     unit_ids={'A':unit,'B':'b'}, evidence_sha256='b'*64)
                for day,price,unit in [('2026-10-20','100','old'),('2026-10-29','12.5','new')]]
        risk = advance_monthly_exit(state=None, account_id=state['account_id'],
            baseline_targets=proposal['payload']['proposed_target_quantities'],
            **{k:v for k,v in rows[0].items() if k != 'evidence_sha256'})['state']
        risk['target_month'] = '2026-10'
        self.arguments = dict(destination_path=self.destination, account_after=account, action_id='action',
            risk_before=risk, target=target, expected_proposal_id=proposal['proposal_id'],
            observations=rows, expected_sessions=[r['session_date'] for r in rows])

    def test_persist_restart_preserve_raw_and_idempotent_history_replay(self):
        originals = deepcopy(self.arguments)
        result = prepare_split_risk(**self.arguments)
        self.assertEqual(self.arguments, originals)
        self.assertEqual(result['final_state']['peaks']['A'], '25/2')
        self.assertEqual(result['final_state']['exited'], [])
        with closing(sqlite3.connect(self.destination)) as connection:
            saved = json.loads(connection.execute('SELECT payload FROM split_preparation').fetchone()[0])
        self.assertEqual(saved['history']['payload']['original_observations'], self.arguments['observations'])
        store = MonthlyPeakExitStore(self.destination)
        replayed = store.advance(account_id='synthetic-account', expected_previous_session='2026-10-29',
            observations=saved['history']['payload']['normalized_observations'],
            baseline_targets=saved['transition']['payload']['risk_projection']['target_quantities'], target_month='2026-10')
        self.assertEqual(replayed['state'], result['final_state'])

    def test_mismatched_original_peak_is_rejected(self):
        self.arguments['risk_before']['peaks']['A'] = '101'
        with self.assertRaisesRegex(ValueError, 'PREFIX_STATE_MISMATCH'): prepare_split_risk(**self.arguments)
        self.assertFalse(self.destination.exists())

    def test_old_month_risk_cannot_be_bound_to_new_month_target(self):
        self.arguments['risk_before']['target_month'] = '2026-09'
        with self.assertRaisesRegex(ValueError, 'RISK_TARGET_MONTH_MISMATCH'):
            prepare_split_risk(**self.arguments)
        self.assertFalse(self.destination.exists())

    def test_failed_build_never_publishes_partial_database(self):
        with patch.object(MonthlyPeakExitStore, 'advance', side_effect=ValueError('injected')):
            with self.assertRaisesRegex(ValueError, 'injected'): prepare_split_risk(**self.arguments)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.destination.parent.glob('.split-risk-*')), [])
