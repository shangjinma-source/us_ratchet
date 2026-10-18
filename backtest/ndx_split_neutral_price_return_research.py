"""Explicit share-ratio price returns; never infer events from a price jump."""
from datetime import date
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASES = {'NOMINAL_CLOSE', 'SPLIT_ONLY_ADJUSTED_CLOSE'}


def verify(sources):
    for path, digest in sources.items():
        if not Path(path).is_absolute() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('Return input source binding differs')


def positive(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError('Finite nonboolean positive number required')
    return value


def calculate_split_neutral_price_returns(payload):
    """Pure numerical kernel; explicit payload cannot certify upstream assertions."""
    if (payload.get('schema') != 'ndx_split_neutral_return_input_v1'
            or payload.get('basis') not in BASES
            or payload.get('event_denominator_scope') != 'EXPLICIT_ALL_SUBMITTED_SECURITY_SESSIONS'
            or payload.get('dividend_adjustment_in_close') is not False):
        raise ValueError('Explicit split-only or nominal basis and event denominator required')
    calendar = payload['calendar']
    if type(calendar) is not list or len(calendar) < 2 or calendar != sorted(set(calendar)):
        raise ValueError('At least two unique sorted calendar sessions required')
    for session in calendar:
        if type(session) is not str or date.fromisoformat(session).isoformat() != session:
            raise ValueError('Exact ISO session required')
    securities = payload['securities']
    if type(securities) is not dict or not securities:
        raise ValueError('Stable securities required')
    issuers = []
    for sid, identity in securities.items():
        if (type(sid) is not str or not sid.startswith('security:')
                or set(identity) != {'issuer_id'} or type(identity['issuer_id']) is not str
                or not identity['issuer_id'].startswith('issuer:')):
            raise ValueError('Explicit stable SID and issuer required')
        issuers.append(identity['issuer_id'])
    # This is a return panel, so same-issuer share classes may coexist.
    denominator = {(sid, session) for sid in securities for session in calendar}
    indexed = {}
    for row in payload['rows']:
        if set(row) != {'security_id', 'issuer_id', 'ticker', 'session', 'close'}:
            raise ValueError('Exact daily price coordinate fields required')
        key = (row['security_id'], row['session'])
        if key not in denominator or key in indexed:
            raise ValueError('Missing/duplicate/extra price coordinate')
        if (row['issuer_id'] != securities[key[0]]['issuer_id'] or type(row['ticker']) is not str
                or not row['ticker'] or row['ticker'] != row['ticker'].strip()):
            raise ValueError('Daily identity mismatch')
        positive(row['close'])
        indexed[key] = row
    ratios = {}
    for row in payload['daily_share_ratios']:
        if set(row) != {'security_id', 'session', 'new_shares', 'old_shares'}:
            raise ValueError('Exact share ratio coordinate fields required')
        key = (row['security_id'], row['session'])
        if key not in denominator or key in ratios:
            raise ValueError('Duplicate/extra event coordinate')
        ratios[key] = Fraction(str(positive(row['new_shares']))) / Fraction(str(positive(row['old_shares'])))
    if set(indexed) != denominator or set(ratios) != denominator:
        raise ValueError('Complete price and event security-session denominator required')
    output = []
    for sid in sorted(securities):
        for previous, session in zip(calendar, calendar[1:]):
            row, prior = indexed[sid, session], indexed[sid, previous]
            event = ratios[sid, session]
            multiplier = event if payload['basis'] == 'NOMINAL_CLOSE' else Fraction(1)
            gross = (Fraction(str(row['close'])) * multiplier) / Fraction(str(prior['close']))
            value = float(gross - 1)
            if not math.isfinite(value):
                raise ValueError('Nonfinite computed return')
            output.append(dict(security_id=sid, issuer_id=row['issuer_id'], ticker=row['ticker'],
                previous_ticker=prior['ticker'], session=session, previous_session=previous,
                close=row['close'], previous_close=prior['close'],
                declared_share_ratio=str(event), applied_share_ratio=str(multiplier), price_return=value))
    return dict(schema='ndx_split_neutral_price_return_research_v1', basis=payload['basis'],
        rows=output, calendar=calendar, security_count=len(securities), input_price_row_count=len(indexed),
        explicit_event_cell_count=len(ratios), output_return_count=len(output),
        first_session_has_no_previous_close_return=True, dividend_cash_flows_included=False,
        event_denominator_scope=payload['event_denominator_scope'],
        source_assertions_authenticated=False, event_completeness_independently_verified=False,
        stable_coordinate_authenticity_verified=False, calendar_exchange_completeness_verified=False,
        old_training_reuse_authorized=False, execution_price_use_authorized=False,
        point_in_time_verified=False, promotion_allowed=False)


def build_split_neutral_price_return_research(*, input_path, expected_sha256):
    path = Path(input_path).resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Input artifact digest differs')
    payload = json.loads(raw)
    sources = dict(payload['source_hashes'])
    if not sources:
        raise ValueError('Explicit input evidence source closure required')
    for name, digest in {str(path): expected_sha256, str(SOURCE): LOADED_SHA}.items():
        if name in sources and sources[name] != digest:
            raise ValueError('Conflicting source closure')
        sources[name] = digest
    verify(sources)
    result = calculate_split_neutral_price_returns(payload)
    verify(sources)
    result.update(source_hashes=sources, input_sha256=expected_sha256,
                  scope='DECLARED_EVENT_SPLIT_NEUTRAL_PRICE_RETURN_NUMERICS_NOT_ADMISSION')
    return result
