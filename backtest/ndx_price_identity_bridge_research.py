"""Explicit, file-bound SID price coordinates; never authenticates evidence.

Evidence JSON is caller-provided research evidence, not a verified external fact.
Every SID must have complete coverage of the caller's required session calendar.
No forward fill, ticker inference, corporate-action adjustment, or execution.
"""
import hashlib
import json
import math
from pathlib import Path
import re

import pandas as pd

_SOURCE = Path(__file__).resolve()
_LOADED_SHA = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
_IDENTITY = ('security_id', 'issuer_id', 'cik', 'cusip')


def _date(value):
    if type(value) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is None:
        raise ValueError('Canonical session date required')
    parsed = pd.Timestamp(value)
    if pd.isna(parsed) or parsed.date().isoformat() != value:
        raise ValueError('Invalid session date')
    return value


def _text(value):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError('Canonical nonempty identity required')
    return value


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('Exact identity artifact schema required')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def build_price_identity_bridge(*, calendar, securities):
    """Return Open/Close DataFrames keyed by stable generated internal columns.

    Interval references have path/sha256 pairs; artifacts use the explicit JSON
    schemas exercised in the tests. Required calendar is supplied, not inferred.
    Evidence must be available by first use; this necessary cutoff guard does
    not upgrade the always-False PIT/authenticity assertions.
    """
    sources = {str(_SOURCE): _LOADED_SHA}
    documents = {}

    def verify():
        for path, digest in sources.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                raise ValueError('Price identity source drift: ' + path)

    def read(reference):
        _exact(reference, ('path', 'sha256'))
        path = Path(reference['path'])
        digest = reference['sha256']
        if not path.is_absolute() or type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None:
            raise ValueError('Absolute artifact path and canonical SHA required')
        key = str(path.resolve())
        if key in sources and sources[key] != digest:
            raise ValueError('Conflicting artifact source bindings')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Artifact SHA differs')
        sources[key] = digest
        if key not in documents:
            documents[key] = json.loads(raw, object_pairs_hook=_pairs,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        return documents[key], key

    verify()
    if type(calendar) is not list or not calendar:
        raise ValueError('Explicit nonempty calendar required')
    sessions = [_date(value) for value in calendar]
    if sessions != sorted(set(sessions)):
        raise ValueError('Unique ascending calendar required')
    if type(securities) is not dict or not securities:
        raise ValueError('Explicit SID map required')
    opens, closes, labels, audit, event_audit, columns = {}, {}, {day: {} for day in sessions}, [], [], {}
    security_pairs, cik_issuers, issuer_ciks = set(), {}, {}
    provider_security_by_session = {day: {} for day in sessions}
    for sid in sorted(securities):
        _text(sid)
        spec = securities[sid]
        _exact(spec, ('issuer_id', 'cik', 'cusip', 'intervals', 'rename_events'))
        identity = dict(security_id=sid, **{key: _text(spec[key]) for key in _IDENTITY[1:]})
        if (re.fullmatch(r'\d{10}', identity['cik']) is None or int(identity['cik']) == 0
                or re.fullmatch('[A-Z0-9]{9}', identity['cusip']) is None):
            raise ValueError('Canonical CIK/CUSIP required')
        pair = (identity['cik'], identity['cusip'])
        if (pair in security_pairs or cik_issuers.get(identity['cik'], identity['issuer_id']) != identity['issuer_id']
                or issuer_ciks.get(identity['issuer_id'], identity['cik']) != identity['cik']):
            raise ValueError('Conflicting SID/CIK/CUSIP/issuer identity mapping')
        security_pairs.add(pair)
        cik_issuers[identity['cik']] = identity['issuer_id']
        issuer_ciks[identity['issuer_id']] = identity['cik']
        if type(spec['intervals']) is not list or not spec['intervals'] or type(spec['rename_events']) is not list:
            raise ValueError('Explicit intervals and rename event lists required')
        intervals, marks = [], {}
        for interval in spec['intervals']:
            _exact(interval, ('first_session', 'last_session', 'observed_ticker', 'open_column', 'close_column',
                              'provider_instrument_id', 'price_artifact', 'identity_evidence'))
            first, last = _date(interval['first_session']), _date(interval['last_session'])
            if first not in sessions or last not in sessions or first > last:
                raise ValueError('Interval endpoints outside required calendar')
            ticker = _text(interval['observed_ticker'])
            if re.fullmatch('[A-Z0-9][A-Z0-9.-]*', ticker) is None:
                raise ValueError('Canonical observed ticker required')
            provider = _text(interval['provider_instrument_id'])
            open_column, close_column = _text(interval['open_column']), _text(interval['close_column'])
            if len({open_column, close_column, 'session'}) != 3:
                raise ValueError('Separate price columns required')
            evidence, evidence_path = read(interval['identity_evidence'])
            evidence_keys = (*_IDENTITY, 'schema', 'observed_ticker', 'provider_instrument_id',
                             'first_session', 'last_session', 'evidence_available_session')
            _exact(evidence, evidence_keys)
            expected = dict(identity, schema='ndx_price_identity_evidence_v1', observed_ticker=ticker,
                            provider_instrument_id=provider)
            if any(evidence[key] != value for key, value in expected.items()):
                raise ValueError('Identity evidence content differs from declared price identity')
            if _date(evidence['first_session']) > first or _date(evidence['last_session']) < last:
                raise ValueError('Identity evidence does not cover interval')
            if _date(evidence['evidence_available_session']) > first:
                raise ValueError('Identity evidence unavailable at first required session')
            prices, price_path = read(interval['price_artifact'])
            _exact(prices, (*_IDENTITY, 'schema', 'observed_ticker', 'provider_instrument_id',
                            'open_column', 'close_column', 'currency', 'price_basis', 'rows'))
            expected.update(schema='ndx_identity_price_artifact_v1', open_column=open_column,
                            close_column=close_column, currency='USD', price_basis='UNADJUSTED')
            if any(prices[key] != value for key, value in expected.items()):
                raise ValueError('Price artifact identity/channel/basis differs')
            if type(prices['rows']) is not list or not prices['rows']:
                raise ValueError('Nonempty explicit price rows required')
            rows = {}
            previous_day = None
            for row in prices['rows']:
                _exact(row, ('session', open_column, close_column))
                day = _date(row['session'])
                if previous_day is not None and day <= previous_day:
                    raise ValueError('Unique ascending price rows required')
                previous_day = day
                # Reject backfilled future ticker channels even outside our slice.
                if not evidence['first_session'] <= day <= evidence['last_session']:
                    raise ValueError('Price row outside proven ticker identity interval')
                values = [row[open_column], row[close_column]]
                if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in values):
                    raise ValueError('Positive finite nonboolean prices required')
                rows[day] = values
            for day in sessions:
                if first <= day <= last:
                    if day in marks or day not in rows:
                        raise ValueError('Overlapping interval or missing historical price')
                    marks[day] = rows[day]
                    owner = provider_security_by_session[day].get(provider)
                    if owner is not None and owner != sid:
                        raise ValueError('Concurrent SIDs share provider instrument on ' + day)
                    provider_security_by_session[day][provider] = sid
                    labels[day][sid] = ticker
                    audit.append(dict(session=day, security_id=sid, ticker=ticker,
                        provider_instrument_id=provider, open_column=open_column, close_column=close_column,
                        open_usd=rows[day][0], close_usd=rows[day][1], price_artifact_path=price_path,
                        price_artifact_sha256=sources[price_path], identity_evidence_path=evidence_path,
                        identity_evidence_sha256=sources[evidence_path],
                        evidence_available_session=evidence['evidence_available_session'],
                        evidence_available_by_price_session=True))
            intervals.append(interval)
        if set(marks) != set(sessions) or intervals != sorted(intervals, key=lambda row: row['first_session']):
            raise ValueError('Unsorted or incomplete SID price intervals')
        events = {}
        for event in spec['rename_events']:
            _exact(event, ('event_id', 'effective_session', 'from_ticker', 'to_ticker', 'evidence'))
            day = _date(event['effective_session'])
            evidence, path = read(event['evidence'])
            _exact(evidence, (*_IDENTITY, 'schema', 'event_id', 'event_type', 'effective_session',
                             'from_ticker', 'to_ticker', 'evidence_available_session'))
            expected = dict(identity, schema='ndx_same_security_rename_evidence_v1',
                            event_type='SAME_SECURITY_SYMBOL_CHANGE',
                            **{key: _text(event[key]) for key in ('event_id', 'effective_session', 'from_ticker', 'to_ticker')})
            if any(evidence[key] != value for key, value in expected.items()) or day in events:
                raise ValueError('Conflicting or duplicate rename evidence')
            if _date(evidence['evidence_available_session']) > day:
                raise ValueError('Rename evidence unavailable at effective session')
            events[day] = event
            event_audit.append(dict(evidence, evidence_path=path, evidence_sha256=sources[path]))
        required = {}
        for old, new in zip(intervals, intervals[1:]):
            if sessions.index(new['first_session']) != sessions.index(old['last_session']) + 1:
                raise ValueError('Nonadjacent SID intervals')
            if old['observed_ticker'] != new['observed_ticker']:
                required[new['first_session']] = (old['observed_ticker'], new['observed_ticker'])
        if set(events) != set(required) or any((events[day]['from_ticker'], events[day]['to_ticker']) != pair
                                               for day, pair in required.items()):
            raise ValueError('Missing, unexpected, or mistimed same-security rename evidence')
        column = 'SID' + hashlib.sha256(sid.encode()).hexdigest().upper()
        if column in columns.values():
            raise ValueError('Internal SID coordinate collision')
        columns[sid] = column
        opens[column] = [marks[day][0] for day in sessions]
        closes[column] = [marks[day][1] for day in sessions]
    for day, tickers in labels.items():
        if len(set(tickers.values())) != len(tickers):
            raise ValueError('Concurrent SIDs share ticker on ' + day)
    verify()
    return dict(schema='ndx_price_identity_bridge_research_v1',
        opens=pd.DataFrame(opens, index=pd.DatetimeIndex(sessions)),
        closes=pd.DataFrame(closes, index=pd.DatetimeIndex(sessions)),
        internal_columns_by_security=columns, tickers_by_session=labels,
        price_audit=audit, rename_event_audit=event_audit, source_hashes=sources,
        source_authenticity_verified=False, point_in_time_verified=False,
        corporate_action_coverage_verified=False, price_adjustment_performed=False,
        evidence_timing_policy='AVAILABLE_BY_FIRST_PRICE_USE_AND_RENAME_EFFECTIVE_SESSION',
        execution_performed=False, promotion_allowed=False)
