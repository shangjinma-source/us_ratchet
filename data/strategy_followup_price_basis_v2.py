"""Check archived normalized closes against raw quotes, without admitting trades."""
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import require


def review_price_basis(inputs, files, *, monthly=False):
    """Caller authenticates the archive. This checks price consistency only.

    Equal adjusted/raw closes and no visible events are bounded checks, not
    independent certification that the provider covered every corporate action.
    """
    reports = {}
    for security_id, history in inputs['histories'].items():
        units = history['units']
        require(units['schema']=='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1' and
                units['currency']=='USD' and units['unit_asof']==inputs['signal_date'],
                'FOLLOWUP_PRICE_UNIT_CONTEXT')
        require(units['review_reference'] in files, 'FOLLOWUP_UNIT_REVIEW_MISSING')
        reference = history['source_reference']
        if monthly and reference.startswith('sha256:'):
            matches = [raw for raw in files.values() if sha256(raw).hexdigest() == reference[7:]]
            require(bool(matches), 'FOLLOWUP_PRICE_SOURCE_MISSING')
            raw_source = matches[0]
        else:
            raw_source = files[reference]
        chart = json.loads(raw_source)['chart']
        require(chart.get('error') is None and len(chart['result'])==1, 'FOLLOWUP_PRICE_SERIES')
        source = chart['result'][0]
        meta = source['meta']
        require(meta['currency']=='USD' and meta['exchangeName']=='NMS' and
                meta['instrumentType']=='EQUITY', 'FOLLOWUP_PRICE_IDENTITY')
        require(not any(source.get('events', {}).values()), 'FOLLOWUP_VISIBLE_CORPORATE_ACTION')
        times = source['timestamp']
        raw = source['indicators']['quote'][0]['close']
        adjusted = source['indicators']['adjclose'][0]['adjclose']
        require(len(times)==len(raw)==len(adjusted), 'FOLLOWUP_PRICE_ARRAYS')
        expected = {row['date']: row['close'] for row in history['closes']}
        require(len(expected)==len(history['closes']) and (len(expected)>0 if monthly else len(expected)==20) and
                max(expected)==inputs['signal_date'], 'FOLLOWUP_NORMALIZED_WINDOW')
        observed = {}
        for stamp, close, adj in zip(times, raw, adjusted):
            day = datetime.fromtimestamp(stamp, timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            if day not in expected:
                continue
            require(day not in observed, 'FOLLOWUP_DUPLICATE_PRICE_DATE')
            require(type(close) in (int,float) and type(adj) in (int,float), 'FOLLOWUP_INVALID_PRICE')
            value = Fraction(str(close))
            require(value>0 and value==Fraction(str(adj)), 'FOLLOWUP_ADJUSTMENT_DIFFERENCE')
            require(value==Fraction(expected[day]), 'FOLLOWUP_NORMALIZATION_DIFFERENCE')
            observed[day] = value
        require(set(observed)==set(expected), 'FOLLOWUP_PRICE_WINDOW_INCOMPLETE')
        reports[security_id] = dict(ticker=meta['symbol'], checked_sessions=len(expected),
            signal_date=inputs['signal_date'], basis_id=units['basis_id'],
            status='ARCHIVED_RAW_AND_NORMALIZED_CLOSES_MATCH',
            source_authenticated=False, coverage_complete=False)
    require(bool(reports), 'FOLLOWUP_EMPTY_PRICE_DOMAIN')
    return dict(securities=reports, capture_admitted=False, performance_computed=False)
