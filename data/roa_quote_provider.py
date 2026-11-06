"""Bounded read-only fresh quote adapter. No historical-close fallback or orders."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from threading import Lock

from data.current_research_intraday_execution import fetch_intraday_chart, decode_intraday_reference


def stamp(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('AWARE_SESSION_TIME_REQUIRED')
    return result


class RoaQuoteProvider:
    """Identity/calendar/limit policy are server dependencies, never client claims.

    session_reader(date) returns authoritative open_at and close_at.
    limit_builder(last_price, phase) returns explicit approved buy/sell strings.
    Completed minute freshness means readiness begins no earlier than 09:31 ET;
    an opening price is an observed reference, not a promised opening fill.
    """
    def __init__(self, *, identity_map, session_reader, limit_builder,
                 fetch=fetch_intraday_chart, clock=lambda: datetime.now(timezone.utc)):
        self.identities = dict(identity_map)
        self.session_reader = session_reader
        self.limit_builder = limit_builder
        self.fetch = fetch
        self.clock = clock
        self.cache = {}
        self.lock = Lock()

    def __call__(self, account, required_sids, session, phase, now):
        now = stamp(now)
        bounds = self.session_reader(session)
        opening, closing = stamp(bounds['open_at']), stamp(bounds['close_at'])
        if not opening <= now < closing:
            raise ValueError('WAIT_FRESH_QUOTE')
        sids = sorted(set(required_sids))
        # Ten prior holdings plus ten new targets can be disjoint at rollover.
        # The service derives this union; the server-owned identity map bounds it.
        if not sids or len(sids) > 20 or any(s not in self.identities for s in sids):
            raise ValueError('QUOTE_IDENTITY_DOMAIN_MISMATCH')
        if not self.lock.acquire(blocking=False):
            raise ValueError('WAIT_FRESH_QUOTE')
        try:
            def capture(sid):
                ticker = self.identities[sid]['ticker']
                cached = self.cache.get(sid)
                if cached and 0 <= (now-cached[1]).total_seconds() < 15:
                    return sid, cached
                raw = self.fetch(ticker)
                captured = stamp(self.clock())
                return sid, (raw, captured)
            try:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    captures = dict(executor.map(capture, sids))
            except Exception as error:
                raise ValueError('WAIT_FRESH_QUOTE') from error
            delivered = stamp(self.clock())
            if delivered < now or not opening <= delivered < closing:
                raise ValueError('WAIT_FRESH_QUOTE')
            marks, limits, prices, evidence, deadlines = {}, {}, {}, {}, []
            for sid, (raw, captured) in captures.items():
                try:
                    ref = decode_intraday_reference(raw, ticker=self.identities[sid]['ticker'],
                                                    now=delivered, captured_at=captured)
                    if (ref['session'] != session or stamp(ref['session_open']) != opening
                            or stamp(ref['session_close']) != closing):
                        raise ValueError('SESSION_CALENDAR_MISMATCH')
                    result = json.loads(raw, parse_float=Decimal)['chart']['result'][0]
                    indices = [i for i, t in enumerate(result['timestamp']) if t == int(opening.timestamp())]
                    if len(indices) != 1:
                        raise ValueError('OPENING_PRICES_UNAVAILABLE')
                    value = result['indicators']['quote'][0]['open'][indices[0]]
                    if value is None or isinstance(value, bool):
                        raise ValueError('OPENING_PRICES_UNAVAILABLE')
                    price = Decimal(str(value))
                    if not price.is_finite() or price <= 0:
                        raise ValueError('OPENING_PRICES_UNAVAILABLE')
                    bar = result['indicators']['quote'][0]
                    try:
                        o,h,l,c,v = [Decimal(str(bar[k][indices[0]])) for k in ('open','high','low','close','volume')]
                        valid = all(x.is_finite() for x in (o,h,l,c,v)) and 0 < l <= o <= h and l <= c <= h and v > 0
                        valid = valid and captured.timestamp() >= opening.timestamp()+60
                    except Exception:
                        valid = False
                    if not valid:
                        raise ValueError('OPENING_PRICES_UNAVAILABLE')
                    prices[sid] = str(price)
                    policy = self.limit_builder(ref['last_price'], phase)
                    for side in ('buy', 'sell'):
                        number = Decimal(str(policy[side]))
                        if not number.is_finite() or number <= 0:
                            raise ValueError('INVALID_LIMIT_POLICY')
                    common = dict(security_id=sid, price_basis='current', observed_at=ref['last_at'])
                    marks[sid] = dict(common, price=ref['last_price'], currency='USD')
                    limits[sid] = dict(common, buy=str(policy['buy']), sell=str(policy['sell']))
                    deadlines.append(stamp(ref['refresh_by']))
                    evidence[sid] = dict(ticker=self.identities[sid]['ticker'],
                        source=ref['source'], raw_sha256=sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest(),
                        captured_at=captured.isoformat(), opening_observed_at=opening.isoformat())
                except Exception as error:
                    if str(error) == 'OPENING_PRICES_UNAVAILABLE':
                        raise
                    raise ValueError('WAIT_FRESH_QUOTE') from error
            self.cache.update(captures)
            return dict(marks=marks, limits=limits, opening_prices=prices,
                opening_session=session, quote_valid_until=min(deadlines).isoformat(),
                quote_evidence=evidence, captured_at=delivered.isoformat(),
                opening_price_scope='OBSERVED_OPEN_REFERENCE_NOT_GUARANTEED_FILL')
        finally:
            self.lock.release()
