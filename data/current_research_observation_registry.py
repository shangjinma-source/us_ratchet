"""Server-owned, read-only admission of completed-session paper observations.

Hash pins authenticate saved bytes, not market truth. Calendar and unit evidence
remain explicit human-reviewed conditional admissions. No network or writes.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from data.current_portfolio_preview import ROOT
from data.current_research_fill_ledger import review_paper_ledger
from data.current_research_plan_observation import review_plan_observations
from data.current_research_saved_quote import read_saved_quote

DEFAULT_REGISTRY = 'data/research_paper/observation_registry.json'
SCHEMA = 'PAPER_OBSERVATION_REGISTRY_V1'
NY = ZoneInfo('America/New_York')


def require(ok, message):
    if not ok:
        raise ValueError(message)


class PlanObservationLoader:
    def __init__(self, *, root=ROOT, registry_path=DEFAULT_REGISTRY):
        self.root = Path(root).resolve()
        self.registry_path = registry_path

    def _path(self, value):
        require(isinstance(value, str) and value, 'OBSERVATION_PATH_REQUIRED')
        p = Path(value)
        require(not p.is_absolute() and not p.drive and '..' not in p.parts and '\\' not in value,
                'OBSERVATION_PATH_OUTSIDE_ROOT')
        resolved = (self.root / p).resolve()
        require(resolved.is_relative_to(self.root), 'OBSERVATION_PATH_OUTSIDE_ROOT')
        return resolved

    def _read(self, path, expected=None):
        p = self._path(path)
        require(p.stat().st_size <= 32*1024*1024, 'OBSERVATION_SOURCE_TOO_LARGE')
        raw = p.read_bytes()
        if expected is not None:
            require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected)
                    and hashlib.sha256(raw).hexdigest() == expected, 'OBSERVATION_HASH_MISMATCH')
        return raw

    def review(self, state, *, now):
        """None only for absent registry/current-plan entry; bad admissions raise.

        No revision binding: explicit fills may advance revision within this plan.
        Historical entries for other known plans are ignored, never substituted.
        """
        try:
            return self._review(state, now=now)
        except (OSError, KeyError, TypeError, AttributeError) as error:
            raise ValueError('OBSERVATION_REGISTRY_INVALID_OR_MISSING_SOURCE') from error

    def _review(self, state, *, now):
        review_paper_ledger(state)
        require(isinstance(now, datetime) and now.tzinfo is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
        registry_path = self._path(self.registry_path)
        if not registry_path.exists():
            return None
        registry = json.loads(self._read(self.registry_path))
        require(registry.get('schema') == SCHEMA and isinstance(registry.get('entries'), list), 'INVALID_OBSERVATION_REGISTRY')
        plan = state['plan']; matches = []
        known_plans = {p['plan_id'] for p in state['plans']}
        for entry in registry['entries']:
            require(isinstance(entry, dict), 'INVALID_OBSERVATION_ENTRY')
            if entry.get('account_id') != state['account_id']:
                continue
            require(entry.get('plan_id') in known_plans, 'OBSERVATION_UNKNOWN_ACCOUNT_PLAN')
            if entry['plan_id'] == plan['plan_id']:
                matches.append(entry)
        if not matches:
            return None
        require(len(matches) == 1, 'AMBIGUOUS_OBSERVATION_ADMISSION')
        entry = matches[0]
        bundle = json.loads(self._read(entry['bundle_path'], entry['sha256']))
        for key, expected in [('account_id',state['account_id']),('plan_id',plan['plan_id']),
                              ('research_id',plan['research_id']),('active_date',plan['active_date'])]:
            require(entry.get(key) == bundle.get(key) == expected, 'OBSERVATION_BINDING_MISMATCH:'+key)
        pins = bundle['source_hashes']
        require(isinstance(pins,dict) and pins, 'OBSERVATION_PINS_REQUIRED')
        for path,digest in pins.items():
            self._read(path,digest)
        def refs(values):
            require(isinstance(values,list) and values and all(v in pins for v in values), 'OBSERVATION_EVIDENCE_UNPINNED')
        admission = bundle['admission']
        require(admission.get('status') == 'ACCEPTED_CONDITIONAL_OBSERVATION'
                and isinstance(admission.get('reviewer'),str) and admission['reviewer'].strip(), 'OBSERVATION_NOT_REVIEWED')
        refs(admission['evidence_references'])
        require(isinstance(admission.get('limitations'),list) and admission['limitations'], 'OBSERVATION_LIMITATIONS_REQUIRED')
        reviewed = datetime.fromisoformat(admission['reviewed_at'])
        require(reviewed.tzinfo is not None and reviewed <= now, 'OBSERVATION_REVIEW_TIME_INVALID')
        calendar_path = bundle['calendar_path']; require(calendar_path in pins, 'OBSERVATION_CALENDAR_UNPINNED')
        calendar = json.loads(self._read(calendar_path,pins[calendar_path]))
        require(calendar.get('status') == 'REVIEWED_OFFICIAL_SESSION_CALENDAR', 'OBSERVATION_CALENDAR_UNREVIEWED')
        refs(calendar['source_references'])
        day = plan['active_date']; session = calendar['sessions'][day]
        market = plan['causal_inputs']['research_snapshot']['market_session']
        close = datetime.fromisoformat(session['close_at']); opening = datetime.fromisoformat(session['open_at'])
        require(session.get('timezone') == market.get('timezone') == 'America/New_York'
                and market.get('date') == day and close.isoformat() == market['close_at']
                and opening.isoformat() == market['open_at'], 'OBSERVATION_CALENDAR_PLAN_MISMATCH')
        require(all(t.tzinfo is not None and t.date().isoformat() == day
                    and t.astimezone(NY).date().isoformat() == day
                    and t.utcoffset() == t.astimezone(NY).utcoffset() for t in [opening,close])
                and opening < close <= reviewed <= now, 'OBSERVATION_SESSION_NOT_COMPLETED')
        require(bundle['observed_through'] == day, 'OBSERVATION_CUTOFF_MISMATCH')
        observations = bundle['observations']; continuity = bundle['unit_continuity']
        require(isinstance(observations,list) and observations, 'OBSERVATIONS_REQUIRED')
        require(set(continuity) == {r['security_id'] for r in observations}, 'OBSERVATION_UNIT_DOMAIN_MISMATCH')
        for row in observations:
            sid = row['security_id']; quote = plan['causal_inputs']['quotes'][sid]; declaration = continuity[sid]
            require(row['observation_date'] == day and row['session_close_at'] == close.isoformat(), 'OBSERVATION_SESSION_MISMATCH')
            self._path(row['relative_directory'])
            require(declaration.get('status') == 'NO_UNPROCESSED_ACTIONS'
                    and declaration.get('from_date') == plan['causal_inputs']['decision_date'] and declaration.get('to_date') == day
                    and declaration.get('price_basis') == quote['price_basis'], 'OBSERVATION_UNIT_CONTINUITY_INVALID')
            refs(declaration['source_references'])
            for suffix,key in [('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')]:
                path = (Path(row['relative_directory'])/(row['ticker']+suffix)).as_posix()
                require(path in pins and pins[path] == row['entry'][key], 'OBSERVATION_SOURCE_NOT_ADMITTED')
            decoded = read_saved_quote(root=self.root,ticker=row['ticker'],expected_security_type=row['expected_security_type'],
                entry=row['entry'],relative_directory=row['relative_directory'],decision_date=day,decision_session_close_at=row['session_close_at'])
            received = datetime.fromisoformat(decoded['received_at'])
            require(received.tzinfo is not None and received <= reviewed <= now, 'OBSERVATION_CAPTURE_AFTER_REVIEW')
            require(not any(plan['causal_inputs']['decision_date'] < event['session'] <= day
                            and event['kind'] != 'dividends' for event in decoded['event_details']),
                    'OBSERVATION_UNPROCESSED_CORPORATE_ACTION')
        result = review_plan_observations(state,root=self.root,observations=observations,
            observed_through=day,now=now,reviewed_observation_pins=pins)
        result['additional_observation_admission_verified_by_helper'] = True
        result['observation_admission'] = dict(bundle_path=entry['bundle_path'],sha256=entry['sha256'],**admission)
        return result


def review_registered_plan_observations(state, *, root=ROOT, now, registry_path=DEFAULT_REGISTRY):
    return PlanObservationLoader(root=root,registry_path=registry_path).review(state,now=now)
