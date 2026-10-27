"""Offline, evidence-bound guidance comparison; never a trading signal.

Each record requires issuer_cik, metric, currency, unit_scale, basis,
fiscal_period_start/end, low/high (decimal strings), publication_datetime,
status='FORWARD_GUIDANCE', source_url/source_sha256, quote_start/end, low_span/high_span.
Spans are [start,end) character offsets into the exact registered UTF-8 text.

verified_sources maps content SHA256 to {issuer_cik,url,text,publication_datetime}.
It is an independently reviewed input, NOT a boolean on the extracted record.
This module checks content binding and numeric transcription, not issuer website
ownership, publication timestamp authenticity, or semantic extraction accuracy.
Metric/basis/currency/scale/period annotation still requires original-text review.
No inference of earliest availability, no trading/calendar/economic conclusions.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re


POLICY = 'SAME_BASIS_PERIOD_BOTH_ENDPOINTS_STRICTLY_LOWER_V1'
KEYS = ('issuer_cik', 'metric', 'currency', 'unit_scale', 'basis',
        'fiscal_period_start', 'fiscal_period_end')
NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?\Z')


def _number(value):
    if not isinstance(value, str) or not NUMBER.fullmatch(value):
        raise ValueError('UNSUPPORTED_NUMERIC_FORMAT')
    result = Decimal(value.replace(',', ''))
    if not result.is_finite():
        raise ValueError('NONFINITE_NUMBER')
    return result


def _time(value):
    if not isinstance(value, str) or 'T' not in value:
        raise ValueError('EXACT_PUBLICATION_TIME_REQUIRED')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('PUBLICATION_TIMEZONE_REQUIRED')
    return result


def _span(text, span):
    if (not isinstance(span, (list, tuple)) or len(span) != 2
            or any(type(n) is not int for n in span)
            or not 0 <= span[0] < span[1] <= len(text)):
        raise ValueError('INVALID_TEXT_SPAN')
    return text[span[0]:span[1]]


def validate_numeric_span(text, span, expected):
    token = _span(text, span)
    before = text[span[0] - 1] if span[0] else ''
    after = text[span[1]] if span[1] < len(text) else ''
    # Exponents, Unicode signs, parentheses and percentages are unsupported,
    # rather than silently interpreting a substring as a positive decimal.
    if ((before and (before.isalnum() or before in '.,-+−–—('))
            or (after and (after.isalnum() or after in '.,)%'))):
        raise ValueError('PARTIAL_OR_UNSUPPORTED_NUMERIC_TOKEN')
    if _number(token) != _number(expected):
        raise ValueError('QUOTE_NUMERIC_MISMATCH')


def _validate(record, sources):
    for key in KEYS:
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError('MISSING_' + key.upper())
    if not re.fullmatch(r'[0-9]{1,10}', record['issuer_cik']):
        raise ValueError('INVALID_CIK')
    if record.get('status') != 'FORWARD_GUIDANCE':
        raise ValueError('NOT_FORWARD_GUIDANCE')
    if date.fromisoformat(record['fiscal_period_start']) > date.fromisoformat(record['fiscal_period_end']):
        raise ValueError('INVALID_PERIOD')
    if _number(record['unit_scale']) <= 0:
        raise ValueError('INVALID_SCALE')
    low, high = _number(record['low']), _number(record['high'])
    if low > high:
        raise ValueError('REVERSED_RANGE')
    published = _time(record['publication_datetime'])
    # Conservative UTC-date boundary: period-end-day announcements are not admitted.
    # A timezone-specific end-of-period policy requires separate reviewed inputs.
    if published.astimezone(timezone.utc).date() >= date.fromisoformat(record['fiscal_period_end']):
        raise ValueError('NOT_FORWARD_GUIDANCE')
    digest = record['source_sha256']
    source = sources.get(digest)
    if not isinstance(source, dict):
        raise ValueError('SOURCE_NOT_IN_VERIFIED_REGISTRY')
    text = source['text']
    if not isinstance(text, str) or sha256(text.encode('utf-8')).hexdigest() != digest:
        raise ValueError('SOURCE_HASH_MISMATCH')
    if source['url'] != record['source_url'] or not source['url'].startswith('https://'):
        raise ValueError('SOURCE_URL_MISMATCH')
    if str(source['issuer_cik']).zfill(10) != record['issuer_cik'].zfill(10):
        raise ValueError('SOURCE_ISSUER_MISMATCH')
    if _time(source['publication_datetime']) != published:
        raise ValueError('SOURCE_PUBLICATION_TIME_MISMATCH')
    quote = [record['quote_start'], record['quote_end']]
    _span(text, quote)
    for label, amount in [('low', low), ('high', high)]:
        span = record[label + '_span']
        _span(text, span)
        if not quote[0] <= span[0] < span[1] <= quote[1]:
            raise ValueError('NUMBER_OUTSIDE_QUOTE')
        validate_numeric_span(text, span, record[label])
    return published, low, high


def compare_guidance(previous, current, verified_sources):
    """Return candidate only for two independently bound, comparable ranges."""
    output = {'status': 'UNKNOWN', 'policy': POLICY, 'is_trading_signal': False}
    try:
        if not all(isinstance(item, dict) for item in (previous, current, verified_sources)):
            raise ValueError('MALFORMED_RECORD_OR_REGISTRY')
        old_time, old_low, old_high = _validate(previous, verified_sources)
        new_time, new_low, new_high = _validate(current, verified_sources)
        for key in KEYS:
            old, new = previous[key], current[key]
            if key == 'issuer_cik':
                old, new = old.zfill(10), new.zfill(10)
            if old != new:
                raise ValueError('INCOMPARABLE_' + key.upper())
        if new_time <= old_time:
            raise ValueError('PUBLICATION_ORDER_INVALID')
        if not (new_low < old_low and new_high < old_high):
            reason = ('UNCHANGED' if (new_low, new_high) == (old_low, old_high)
                      else 'RAISE' if new_low > old_low and new_high > old_high
                      else 'OVERLAPPING_MIXED')
            output.update(status='COMPARABLE_NO_STRICT_CUT', reason=reason,
                          source_hashes=[previous['source_sha256'], current['source_sha256']])
            return output
        output.update(status='NUMERIC_GUIDANCE_CUT_CANDIDATE', reason='STRICT_COMPARABLE_RANGE_CUT',
                      source_hashes=[previous['source_sha256'], current['source_sha256']])
    except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation) as error:
        output['reason'] = str(error) if isinstance(error, ValueError) else 'MISSING_OR_MALFORMED_FIELD'
    return output
