"""Persist a separate, replay-checked derived risk candidate; no activation.

Inputs are snapshots, not source authority. Production must authenticate them and
recheck live account/target/risk bindings under its eventual activation barrier.
"""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import os
import sqlite3
import tempfile

from core.strategy_account_ledger import canonical, require
from core.monthly_peak_exit import advance_monthly_exit
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_account_split_migration_v1 import checked_path
from data.strategy_split_native_projection_v1 import project_native_split
from data.strategy_split_history_projection_v1 import project_history_units
from core.saved_monthly_frontier_proposal import build_frontier_proposal


def prepare_split_risk(*, destination_path, account_after, action_id, risk_before,
                       target, expected_proposal_id, observations, expected_sessions):
    destination = checked_path(destination_path)
    require(not destination.exists(), 'SPLIT_RISK_DESTINATION_EXISTS')
    require(destination.parent.is_dir(), 'SPLIT_RISK_PARENT_REQUIRED')
    transition = project_native_split(account_after=account_after, action_id=action_id,
        risk_before=risk_before, target=target, expected_proposal_id=expected_proposal_id)
    action = next(row['payload'] for row in account_after['events']
                  if row['payload']['kind'] == 'SPLIT_CONFIRMED' and row['payload']['action_id'] == action_id)
    history = project_history_units(observations=observations, action=action, expected_sessions=expected_sessions)
    quantities = build_frontier_proposal(target=target)['payload']['proposed_target_quantities']
    prefix = [row for row in observations if row['session_date'] <= risk_before['session_date']]
    require(prefix and prefix[-1]['session_date'] == risk_before['session_date'], 'SPLIT_RISK_PREFIX_REQUIRED')
    replayed = None
    for row in prefix:
        replayed = advance_monthly_exit(state=replayed, account_id=account_after['account_id'],
            baseline_targets=quantities, **{key:value for key,value in row.items() if key != 'evidence_sha256'})['state']
    if 'target_month' in risk_before:
        replayed['target_month'] = risk_before['target_month']
    require(replayed == risk_before, 'SPLIT_RISK_PREFIX_STATE_MISMATCH')
    projection = transition['payload']['risk_projection']
    descriptor, name = tempfile.mkstemp(prefix='.split-risk-', suffix='.sqlite3', dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        store = MonthlyPeakExitStore(temporary)
        result = store.advance(account_id=account_after['account_id'], expected_previous_session=None,
            observations=history['payload']['normalized_observations'],
            baseline_targets=projection['target_quantities'], target_month=target['payload']['target_month'])
        envelope = dict(schema='SPLIT_RISK_PREPARATION_V1', transition=transition, history=history,
                        original_risk_state=risk_before, action=action,
                        result=result, production_activated=False, source_authenticated=False)
        raw = canonical(envelope).decode()
        require(len(raw.encode()) <= 32*1024*1024, 'SPLIT_RISK_PREPARATION_BUDGET')
        with closing(sqlite3.connect(temporary)) as connection:
            connection.execute('CREATE TABLE split_preparation (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL, digest TEXT NOT NULL)')
            connection.execute('INSERT INTO split_preparation VALUES(1,?,?)', (raw, sha256(raw.encode()).hexdigest()))
            connection.commit()
        require(MonthlyPeakExitStore(temporary).read(account_after['account_id']) == result['state'],
                'SPLIT_RISK_RESTART_MISMATCH')
        with closing(sqlite3.connect(temporary)) as connection:
            saved, digest = connection.execute('SELECT payload,digest FROM split_preparation').fetchone()
            require(saved == raw and sha256(saved.encode()).hexdigest() == digest, 'SPLIT_RISK_ARCHIVE_MISMATCH')
        with temporary.open('r+b') as stream:
            os.fsync(stream.fileno())
        database_digest = sha256(temporary.read_bytes()).hexdigest()
        checked_path(destination)
        os.link(temporary, destination)
        return dict(status='SPLIT_RISK_PREPARED_NOT_ACTIVATED', destination_sha256=database_digest,
                    transition_id=transition['transition_id'], account_revision=account_after['revision'],
                    final_state=result['state'], requires_live_binding_recheck=True, source_authenticated=False)
    finally:
        temporary.unlink(missing_ok=True)
