"""Read explicit server-owned unit reviews without creating or certifying them.

The registry is deliberately absent until real evidence is reviewed. Local hash
verification is not authentication or proof of complete corporate actions.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from data.current_research_intraday_buy_plan import _require, _time
from data.current_research_intraday_continuation_ledger import review_continuation_ledger

REGISTRY = 'data/research_paper_intraday/continuity_sources.json'


def load_continuation_unit_evidence(*, root, state, event_path, event_sha256, now):
    """Return pinned, exact-observation-bound evidence; never infer missing reviews."""
    state = review_continuation_ledger(state)
    root = Path(root).resolve()
    now = _time(now)

    def read(name, expected=None):
        _require(isinstance(name, str) and bool(name) and '\\' not in name,
                 'CONTINUITY_SOURCE_PATH_INVALID')
        relative = Path(name)
        _require(not relative.is_absolute() and not relative.drive and '..' not in relative.parts,
                 'CONTINUITY_SOURCE_OUTSIDE_ROOT')
        path = (root / relative).resolve()
        _require(path.is_relative_to(root), 'CONTINUITY_SOURCE_OUTSIDE_ROOT')
        _require(path.is_file(), 'CONTINUITY_EVIDENCE_NOT_REGISTERED' if expected is None
                 else 'CONTINUITY_REGISTERED_SOURCE_MISSING')
        _require(path.stat().st_size <= 8 * 1024 * 1024, 'CONTINUITY_EVIDENCE_TOO_LARGE')
        raw = path.read_bytes()
        if expected is not None:
            _require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected)
                     and sha256(raw).hexdigest() == expected, 'CONTINUITY_SOURCE_HASH_MISMATCH')
        return raw

    registry = json.loads(read(REGISTRY))
    _require(registry.get('schema') == 'INTRADAY_UNIT_CONTINUITY_REGISTRY_V1'
             and isinstance(registry.get('entries'), list), 'CONTINUITY_REGISTRY_INVALID')
    _require(isinstance(event_sha256, str) and re.fullmatch('[0-9a-f]{64}', event_sha256),
             'CONTINUITY_EVENT_HASH_INVALID')
    matches = [row for row in registry['entries'] if isinstance(row, dict)
               and row.get('account_id') == state['account_id']
               and row.get('initial_acceptance_id') == state['acceptance_id']
               and row.get('event_path') == event_path and row.get('event_sha256') == event_sha256]
    _require(bool(matches), 'CONTINUITY_REVIEW_NOT_FOUND')
    _require(len(matches) == 1, 'CONTINUITY_REVIEW_AMBIGUOUS')
    entry = matches[0]
    bundle = json.loads(read(entry['bundle_path'], entry['sha256']))
    _require(bundle.get('schema') == 'CONDITIONAL_INTRADAY_UNIT_REVIEW_V1'
             and bundle.get('status') == 'REVIEWED_CONDITIONAL'
             and isinstance(bundle.get('reviewed_by'), str) and bundle['reviewed_by'].strip(),
             'CONTINUITY_EXPLICIT_REVIEW_REQUIRED')
    for key in ('account_id', 'initial_acceptance_id', 'event_path', 'event_sha256'):
        _require(bundle.get(key) == entry[key], 'CONTINUITY_REVIEW_BINDING_MISMATCH')
    pins = bundle.get('source_hashes')
    _require(isinstance(pins, dict) and bool(pins), 'CONTINUITY_SOURCE_PINS_REQUIRED')
    for name, expected in pins.items():
        read(name, expected)

    def references(items):
        _require(isinstance(items, list) and bool(items)
                 and all(isinstance(item, str) and item in pins for item in items),
                 'CONTINUITY_EVIDENCE_UNPINNED')

    unit = bundle['unit_continuity']
    original = state['acceptance']['proposal']['causal_inputs']
    first = _time(state['acceptance']['accepted_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    _require(unit.get('security_id') == original['security']['security_id']
             and unit.get('initial_event_sha256') == original['event_sha256']
             and unit.get('current_event_sha256') == event_sha256
             and unit.get('from_session') == first
             and unit.get('status') == 'NO_UNPROCESSED_ACTIONS'
             and unit.get('price_basis') == 'CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
             'CONTINUITY_UNIT_BINDING_INVALID')
    references(unit.get('source_references'))
    _require(_time(unit['covered_from']) <= _time(original['observation']['checked_at'])
             <= _time(unit['covered_through']) <= _time(unit['reviewed_asof']) <= now,
             'CONTINUITY_REVIEW_TIME_INVALID')
    if unit.get('to_session') != first:
        action = unit.get('action_review', {})
        _require(action.get('covered_from') == first
                 and action.get('covered_through') == unit.get('to_session')
                 and action.get('status') == 'NO_UNPROCESSED_ACTIONS',
                 'CONTINUITY_ACTION_REVIEW_REQUIRED')
        references(action.get('source_references'))
        _require(_time(action['reviewed_asof']) <= now, 'CONTINUITY_ACTION_REVIEW_IN_FUTURE')
    pins = deepcopy(pins)
    _require(entry['bundle_path'] not in pins, 'CONTINUITY_BUNDLE_SELF_PIN_UNSUPPORTED')
    pins[entry['bundle_path']] = entry['sha256']
    return dict(unit_continuity=deepcopy(unit), source_hashes=pins,
                source_bytes_verified=True, source_authenticated=False)
