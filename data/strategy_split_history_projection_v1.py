"""Derived constant-unit history; original observations/evidence remain immutable.

Calendar continuity and issuer action authority must be authenticated by caller.
No source bytes are reclassified as originally published in the new share unit.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, require
from core.strategy_account_split_v1 import moment


def project_history_units(*, observations, action, expected_sessions):
    require(action.get('kind') == 'SPLIT_CONFIRMED', 'SPLIT_ACTION_REQUIRED')
    sid, ratio = action['security_id'], action['ratio']
    require(type(ratio) is int and ratio > 1, 'INTEGER_FORWARD_SPLIT_REQUIRED')
    require(action['old_unit_id'] != action['new_unit_id'], 'SPLIT_UNIT_CHANGE_REQUIRED')
    effective_day = moment(action['effective_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(type(expected_sessions) is list and bool(expected_sessions)
            and expected_sessions == sorted(set(expected_sessions)), 'SPLIT_EXPECTED_SESSIONS_REQUIRED')
    require([row['session_date'] for row in observations] == expected_sessions, 'SPLIT_FULL_HISTORY_REQUIRED')
    decisions = {row['decision_date'] for row in observations}
    require(len(decisions) == 1 and next(iter(decisions)) == expected_sessions[0]
            and expected_sessions[0] < effective_day, 'SPLIT_HISTORY_EPOCH_REQUIRED')
    normalized = []
    for original in observations:
        require(set(original) == {'decision_date','session_date','closes','unit_ids','evidence_sha256'},
                'SPLIT_HISTORY_ROW_FIELDS')
        digest = original['evidence_sha256']
        require(type(digest) is str and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                'SPLIT_HISTORY_EVIDENCE_REQUIRED')
        require(set(original['closes']) == set(original['unit_ids']) and sid in original['closes'],
                'SPLIT_HISTORY_DOMAIN_REQUIRED')
        row = deepcopy(original)
        before = row['session_date'] < effective_day
        require(row['unit_ids'][sid] == (action['old_unit_id'] if before else action['new_unit_id']),
                'SPLIT_HISTORY_UNIT_MISMATCH')
        require(all(Fraction(value) > 0 for value in row['closes'].values()), 'SPLIT_HISTORY_PRICE_INVALID')
        if before:
            row['closes'][sid] = str(Fraction(row['closes'][sid]) / ratio)
            row['unit_ids'][sid] = action['new_unit_id']
        content = {key:value for key,value in row.items() if key != 'evidence_sha256'}
        # Matches monthly_exit_observations' content ID, not a source receipt.
        row['evidence_sha256'] = sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        normalized.append(row)
    payload = dict(schema='DERIVED_SPLIT_HISTORY_V1', action_sha256=sha256(canonical(action)).hexdigest(),
                   original_observations=deepcopy(observations), normalized_observations=normalized,
                   source_authenticated=False, orders_created=False)
    return dict(history_projection_sha256=sha256(canonical(payload)).hexdigest(), payload=payload)
