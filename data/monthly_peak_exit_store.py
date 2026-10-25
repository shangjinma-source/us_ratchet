"""Transactional risk-only persistence; never writes the trading account.

An evidence adapter must supply authenticated, contiguous completed sessions.
No production mounting occurs on import or store construction.
"""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from fractions import Fraction

from core.monthly_peak_exit import advance_monthly_exit


class MonthlyPeakExitStore:
    def __init__(self, path):
        self.path = Path(path)

    def read(self, account_id):
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='risk_state'").fetchone()
            if not exists:
                return None
            row = connection.execute('SELECT state FROM risk_state WHERE account_id=?', (account_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def recorded_prices(self, account_id, decision_date):
        if not self.path.exists():
            return {}
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='risk_prices'").fetchone()
            if not exists:
                return {}
            rows = connection.execute('SELECT security_id,session_date,close,units FROM risk_prices '
                'WHERE account_id=? AND decision_date=?', (account_id, decision_date)).fetchall()
            result = {}
            for sid, day, close, units in rows:
                result.setdefault(sid, {})[day] = dict(close=close, units=units)
            return result

    def advance(self, *, account_id, expected_previous_session, observations,
                baseline_targets, authorized_monthly_reset=None, target_month=None):
        """Commit all supplied observations or none; reject stale writers.

        Each observation has the core's dates/prices/units and evidence_sha256.
        The digest identifies authenticated input; this class does not validate
        the source bytes or market calendar on behalf of the adapter.
        authorized_monthly_reset is supplied by the server's validated monthly
        release, never by a balance update or a browser field.
        """
        if not observations:
            raise ValueError('RISK_OBSERVATIONS_REQUIRED')
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.execute('PRAGMA synchronous=FULL')
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('CREATE TABLE IF NOT EXISTS risk_state '
                                   '(account_id TEXT PRIMARY KEY, state TEXT NOT NULL)')
                connection.execute('CREATE TABLE IF NOT EXISTS risk_prices '
                    '(account_id TEXT, decision_date TEXT, session_date TEXT, security_id TEXT, '
                    'close TEXT NOT NULL, units TEXT NOT NULL, PRIMARY KEY '
                    '(account_id, decision_date, session_date, security_id))')
                connection.execute('CREATE TABLE IF NOT EXISTS risk_domain_evidence '
                    '(account_id TEXT, decision_date TEXT, session_date TEXT, domain TEXT, '
                    'digest TEXT NOT NULL, PRIMARY KEY '
                    '(account_id, decision_date, session_date, domain))')
                row = connection.execute('SELECT state FROM risk_state WHERE account_id=?',
                                         (account_id,)).fetchone()
                state = json.loads(row[0]) if row else None
                previous = state['session_date'] if state else None
                if previous != expected_previous_session:
                    raise ValueError('RISK_STATE_CHANGED_RELOAD')
                decisions = {item['decision_date'] for item in observations}
                if len(decisions) != 1:
                    raise ValueError('RISK_SINGLE_MONTHLY_EPOCH_REQUIRED')
                decision = next(iter(decisions))
                if state and decision != state['decision_date']:
                    if authorized_monthly_reset != decision:
                        raise ValueError('RISK_MONTHLY_RESET_AUTHORIZATION_REQUIRED')
                original = state
                expanded = bool(state and observations[0]['decision_date'] == state['decision_date']
                    and set(observations[0]['closes']) - set(state['peaks']))
                checked_original = not expanded
                if expanded:
                    if observations[0]['session_date'] != state['decision_date']:
                        raise ValueError('RISK_DOMAIN_EXPANSION_REQUIRES_FULL_HISTORY')
                    # Replay the enlarged domain; verify the old securities at
                    # every recorded date and their exact state before committing.
                    state = None
                result = None
                for observation in observations:
                    observation = dict(observation)
                    digest = observation.pop('evidence_sha256')
                    if not isinstance(digest, str) or len(digest) != 64 or any(
                            char not in '0123456789abcdef' for char in digest):
                        raise ValueError('RISK_EVIDENCE_DIGEST_REQUIRED')
                    key = (account_id, observation['decision_date'], observation['session_date'])
                    domain = json.dumps(sorted(observation['closes']))
                    existing = connection.execute('SELECT digest FROM risk_domain_evidence WHERE '
                        'account_id=? AND decision_date=? AND session_date=? AND domain=?',
                        (*key, domain)).fetchone()
                    if existing and existing[0] != digest:
                        raise ValueError('RISK_EVIDENCE_CHANGED')
                    for sid, close in observation['closes'].items():
                        price = str(Fraction(close))
                        units = observation['unit_ids'][sid]
                        saved = connection.execute('SELECT close,units FROM risk_prices WHERE '
                            'account_id=? AND decision_date=? AND session_date=? AND security_id=?',
                            (*key, sid)).fetchone()
                        if saved and saved != (price, units):
                            raise ValueError('RISK_RECORDED_PRICE_CHANGED')
                        if expanded and sid in original['peaks'] and observation['session_date'] <= previous and not saved:
                            raise ValueError('RISK_OLD_DOMAIN_HISTORY_UNVERIFIED')
                        connection.execute('INSERT OR IGNORE INTO risk_prices VALUES (?,?,?,?,?,?)',
                                           (*key, sid, price, units))
                    if state and observation['session_date'] < state['session_date']:
                        if not existing or observation['decision_date'] != state['decision_date']:
                            raise ValueError('RISK_REPLAY_PREFIX_NOT_VERIFIED')
                        continue
                    result = advance_monthly_exit(state=state, account_id=account_id,
                        baseline_targets=baseline_targets, **observation)
                    state = result['state']
                    if expanded and state['session_date'] == previous:
                        old_domain = set(original['peaks'])
                        for field in ('peaks', 'unit_ids', 'last_closes'):
                            if {sid: state[field].get(sid) for sid in old_domain} != original[field]:
                                raise ValueError('RISK_OLD_DOMAIN_STATE_CHANGED')
                        if set(state['exited']) & old_domain != set(original['exited']):
                            raise ValueError('RISK_OLD_EXIT_STATE_CHANGED')
                        checked_original = True
                    connection.execute('INSERT OR IGNORE INTO risk_domain_evidence VALUES (?,?,?,?,?)',
                                       (*key, domain, digest))
                if result is None:
                    raise ValueError('RISK_CURRENT_OBSERVATION_REQUIRED')
                if not checked_original:
                    raise ValueError('RISK_DOMAIN_REPLAY_MISSING_CURRENT_STATE')
                if target_month is not None:
                    state['target_month'] = target_month
                connection.execute('INSERT INTO risk_state VALUES (?,?) ON CONFLICT(account_id) '
                    'DO UPDATE SET state=excluded.state',
                    (account_id, json.dumps(state, sort_keys=True)))
            # Returning happens only after SQLite successfully commits.
            return result
