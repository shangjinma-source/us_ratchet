"""Frozen guidance V1 overlay for isolated historical research, never live orders.

Inputs are independently admitted, identity-bound chronological comparisons.
This adapter validates replay timing, not source authenticity or corpus coverage.
session_closes must come from the reviewed exchange calendar including early closes.
Not yet wired into the account engine: that needs a realized sale-cash reservation
and independent order review. state proxies only the base risk, not a checkpoint;
resuming requires full decision replay until a bound news checkpoint is added.
"""
from copy import deepcopy
from datetime import date, datetime


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return parsed


class GuidanceNewsRiskAdapter:
    def __init__(self, base, *, events, session_closes, action_policy='EXIT',
                 release_policy='NONCUT_COMPARISON'):
        if action_policy not in {'EXIT', 'BLOCK_NEW_BUYS'}:
            raise ValueError('UNSUPPORTED_NEWS_ACTION_POLICY')
        self.action_policy = action_policy
        if release_policy not in {'NONCUT_COMPARISON', 'EXPLICIT_REPAIR'}:
            raise ValueError('UNSUPPORTED_NEWS_RELEASE_POLICY')
        self.release_policy = release_policy
        self.base = base
        self.closes = {day: timestamp(value) for day, value in session_closes.items()}
        days = sorted(self.closes)
        if not days or any(self.closes[a] >= self.closes[b] for a, b in zip(days, days[1:])):
            raise ValueError('ORDERED_SESSION_CLOSES_REQUIRED')
        self.events = deepcopy(list(events))
        identities, simultaneous, period_bindings = set(), set(), {}
        for event in self.events:
            if not isinstance(event, dict) or any(not isinstance(event.get(name), str) or not event[name]
                    for name in ('id', 'security_id', 'comparison_key', 'period_end',
                                 'available_at', 'classification', 'review_reference')):
                raise ValueError('TYPED_EVENT_FIELDS_REQUIRED')
            if event['id'] in identities:
                raise ValueError('UNIQUE_EVENT_ID_REQUIRED')
            identities.add(event['id'])
            if (not event.get('review_reference') or not event.get('security_id')
                    or not event.get('comparison_key') or not event.get('source_hashes')):
                raise ValueError('ADMITTED_COMPARISON_BINDING_REQUIRED')
            # comparison_key binds issuer, metric, currency, unit, basis and period.
            if not isinstance(event['comparison_key'], str):
                raise ValueError('COMPARISON_KEY_REQUIRED')
            if date.fromisoformat(event['period_end']).isoformat() != event['period_end']:
                raise ValueError('CANONICAL_PERIOD_END_REQUIRED')
            binding = (event['security_id'], event['comparison_key'])
            if binding in period_bindings and period_bindings[binding] != event['period_end']:
                raise ValueError('CONFLICTING_PERIOD_END')
            period_bindings[binding] = event['period_end']
            available = timestamp(event['available_at'])
            key = (event['security_id'], event['comparison_key'], available)
            if key in simultaneous:
                raise ValueError('SIMULTANEOUS_COMPARISON_CONFLICT')
            simultaneous.add(key)
            allowed = {'CUT', 'RAISE', 'UNCHANGED', 'UNKNOWN'}
            if self.release_policy == 'EXPLICIT_REPAIR':
                allowed.add('REPAIRED')
            if event['classification'] not in allowed:
                raise ValueError('UNSUPPORTED_CLASSIFICATION')
            if event['classification'] == 'REPAIRED' and (
                    not isinstance(event.get('repairs_event_id'), str)
                    or not event['repairs_event_id']):
                raise ValueError('EXPLICIT_REPAIR_EVENT_BINDING_REQUIRED')
        self.events.sort(key=lambda event: (timestamp(event['available_at']), event['id']))
        self.position, self.last_day, self.locks = 0, None, {}

    @property
    def state(self):
        return self.base.state

    def apply(self, *, day, month, target, closes, adjustments=(), shares=None):
        if day not in self.closes or (self.last_day is not None and day <= self.last_day):
            raise ValueError('ADVANCING_REVIEWED_SESSION_REQUIRED')
        # Validate before advancing either the original risk state or news cursor.
        if self.action_policy == 'BLOCK_NEW_BUYS' and (
                not isinstance(shares, dict) or any(
                    not isinstance(sid, str) or type(quantity) is not int or quantity < 0
                    for sid, quantity in shares.items())):
            raise ValueError('CURRENT_NONNEGATIVE_INTEGER_SHARES_REQUIRED')
        # Preserve original risk coordinates and exit state before applying news.
        effective, diagnostics = self.base.apply(day=day, month=month, target=target,
                                                closes=closes, adjustments=adjustments)
        consumed = []
        while self.position < len(self.events):
            event = self.events[self.position]
            if timestamp(event['available_at']) >= self.closes[day]:
                break
            self.position += 1
            consumed.append(event['id'])
            key = (event['security_id'], event['comparison_key'])
            if event['classification'] == 'CUT' and day <= event['period_end']:
                self.locks[key] = deepcopy(event)
            elif (self.release_policy == 'NONCUT_COMPARISON'
                  and event['classification'] in {'RAISE', 'UNCHANGED'}):
                self.locks.pop(key, None)
            elif (self.release_policy == 'EXPLICIT_REPAIR'
                  and event['classification'] == 'REPAIRED'
                  and self.locks.get(key, {}).get('id') == event['repairs_event_id']):
                self.locks.pop(key, None)
        expired = [key for key, event in self.locks.items() if day > event['period_end']]
        for key in expired:
            del self.locks[key]
        blocked = {key[0] for key in self.locks}
        result = {
            sid: (min(quantity, shares.get(sid, 0))
                  if self.action_policy == 'BLOCK_NEW_BUYS' else 0)
            if sid in blocked else quantity
            for sid, quantity in effective.items()}
        diagnostics = deepcopy(diagnostics)
        diagnostics['guidance_news'] = dict(policy='GUIDANCE_TRADE_EXPERIMENT_V1',
            action_policy=self.action_policy,
            release_policy=self.release_policy,
            consumed_event_ids=consumed, blocked_security_ids=sorted(blocked),
            active_event_ids=sorted(event['id'] for event in self.locks.values()),
            expired_comparison_keys=[list(key) for key in sorted(expired)],
            decision_cutoff=self.closes[day].isoformat(), order_execution_confirmed=False,
            execution_integration='REQUIRES_SALE_CASH_RESERVATION_AND_INDEPENDENT_ORDER_REVIEW')
        self.last_day = day
        return result, diagnostics
