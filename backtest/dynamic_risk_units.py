"""Research-only risk migration for reviewed splits and share conversions."""
from copy import deepcopy
from datetime import date
from fractions import Fraction


def reviewed_split_schedule(events):
    schedule = deepcopy(list(events))
    identifiers = set()
    sessions = set()
    for event in schedule:
        if event['type'] not in ('split', 'split_identity', 'ads_conversion'):
            raise ValueError('ONLY_REVIEWED_SHARE_UNIT_CONVERSIONS_SUPPORTED')
        if event['type'] != 'split':
            successor = event.get('new_security_id')
            if not isinstance(successor, str) or not successor or successor == event['security_id']:
                raise ValueError('DISTINCT_SUCCESSOR_SECURITY_REQUIRED')
        date.fromisoformat(event['date'])
        if not event['event_id'] or event['event_id'] in identifiers:
            raise ValueError('UNIQUE_RISK_EVENT_ID_REQUIRED')
        key = (event['security_id'], event['date'])
        if key in sessions or not event['security_id']:
            raise ValueError('OVERLAPPING_RISK_UNIT_EVENTS')
        if Fraction(event['new_shares']) <= 0 or Fraction(event['old_shares']) <= 0:
            raise ValueError('POSITIVE_SPLIT_RATIO_REQUIRED')
        if (not event['old_unit_id'] or not event['new_unit_id']
                or event['old_unit_id'] == event['new_unit_id']
                or not isinstance(event['source_references'], list)
                or not event['source_references'] or not all(event['source_references'])):
            raise ValueError('REVIEWED_RISK_UNITS_AND_EVIDENCE_REQUIRED')
        identifiers.add(event['event_id'])
        sessions.add(key)
    return sorted(schedule, key=lambda event: (event['date'], event['security_id']))


def migrate_risk_splits(state, *, through_date, events):
    if state is None:
        return None, []
    updated = deepcopy(state)
    applied = []
    for event in events:
        if not state['session_date'] < event['date'] <= through_date:
            continue
        sid = event['security_id']
        if sid not in updated['peaks']:
            continue
        if updated['unit_ids'][sid] != event['old_unit_id']:
            raise ValueError('RISK_SPLIT_PRIOR_UNIT_MISMATCH')
        successor = sid if event['type'] == 'split' else event['new_security_id']
        if successor != sid and successor in updated['peaks']:
            raise ValueError('RISK_SUCCESSOR_HISTORY_COLLISION')
        factor = Fraction(event['old_shares']) / Fraction(event['new_shares'])
        for field in ('peaks', 'last_closes'):
            value = updated[field].pop(sid)
            updated[field][successor] = str(Fraction(value) * factor)
        updated['unit_ids'].pop(sid)
        updated['unit_ids'][successor] = event['new_unit_id']
        updated['exited'] = sorted({successor if item == sid else item for item in updated['exited']})
        applied.append(event['event_id'])
    # Epoch, previous session and exit latch deliberately remain unchanged.
    return updated, applied
