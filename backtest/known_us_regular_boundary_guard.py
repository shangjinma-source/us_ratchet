"""Narrow, retrospective US ordinary-trading boundary check; no optimizer/I/O.

Only explicitly reviewed securities are checked. Other members are preserved
and labelled uncovered, never certified by this guard. Source bytes must be
verified by the calling assembly layer before using the registry.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction


def _day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('CANONICAL_ISO_DATE_REQUIRED')
    return value


def review_window(*, decision_date, training_dates, candidates, registry):
    decision = _day(decision_date)
    if registry.get('schema') != 'KNOWN_US_REGULAR_BOUNDARIES_V1':
        raise ValueError('BOUNDARY_REGISTRY_SCHEMA')
    if registry.get('knowledge_basis') != 'RETROSPECTIVELY_REVIEWED_PRIMARY_SOURCES':
        raise ValueError('RETROSPECTIVE_KNOWLEDGE_LABEL_REQUIRED')
    _day(registry['reviewed_on'])
    boundaries = registry['boundaries']
    if len({item['ticker'] for item in boundaries}) != len(boundaries):
        raise ValueError('DUPLICATE_BOUNDARY_TICKER')
    indexed = {item['ticker']: item for item in boundaries}
    dates = [_day(value) for value in training_dates]
    common_reasons = []
    if len(dates) != 253 or dates != sorted(set(dates)):
        common_reasons.append('EXACT_253_ORDERED_UNIQUE_TRAINING_DATES_REQUIRED')
    if not dates or dates[-1] != decision or any(value > decision for value in dates):
        common_reasons.append('TRAINING_MUST_END_AT_DECISION_WITHOUT_FUTURE_DATES')
    identifiers = [item['security_id'] for item in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('DUPLICATE_CANDIDATE_SECURITY')
    rows = []
    for item in candidates:
        ticker, security_id = item['ticker'], item['security_id']
        row = dict(ticker=ticker, security_id=security_id, reasons=list(common_reasons),
                   status='NOT_COVERED_BY_KNOWN_BOUNDARIES', sources=[])
        boundary = indexed.get(ticker)
        if boundary is not None:
            start = _day(boundary['us_regular_start'])
            if boundary.get('market') != 'US' or boundary.get('channel') != 'ORDINARY_REGULAR_WAY':
                raise ValueError('EXPLICIT_US_ORDINARY_BOUNDARY_REQUIRED')
            sources = boundary['sources']
            if not sources or any(not all(source.get(key) for key in ('url', 'path', 'sha256')) for source in sources):
                raise ValueError('PINNED_PRIMARY_BOUNDARY_EVIDENCE_REQUIRED')
            row.update(us_regular_start=start, sources=deepcopy(sources),
                       pre_regular_dates=[day for day in dates if day < start])
            if security_id != boundary['security_id']:
                row['reasons'].append('SECURITY_ID_NOT_BOUND_TO_REVIEWED_BOUNDARY')
            if decision < start:
                row['reasons'].append('NOT_YET_US_ORDINARY_LISTED_AT_DECISION')
            if row['pre_regular_dates']:
                row['reasons'].append('TRAINING_INCLUDES_PRE_US_ORDINARY_CHANNEL')
            closes = item.get('training_closes', [])
            valid = []
            if len(closes) != len(dates):
                row['reasons'].append('CLOSES_MUST_MATCH_TRAINING_DATES')
            for day, close in zip(dates, closes):
                try:
                    positive = not isinstance(close, bool) and Fraction(str(close)) > 0
                except (TypeError, ValueError, ZeroDivisionError):
                    positive = False
                if day >= start and positive:
                    valid.append(day)
            row['valid_us_regular_observations'] = len(valid)
            if len(valid) != 253:
                row['reasons'].append('INSUFFICIENT_253_VALID_US_ORDINARY_CLOSES')
            row['status'] = 'EXCLUDED_KNOWN_US_BOUNDARY' if row['reasons'] else 'PASS_KNOWN_US_BOUNDARY_ONLY'
        elif row['reasons']:
            row['status'] = 'EXCLUDED_INVALID_TRAINING_DATES'
        rows.append(row)
    excluded = [row['security_id'] for row in rows if row['reasons']]
    return dict(schema='KNOWN_US_REGULAR_BOUNDARY_REVIEW_V1', decision_date=decision,
        reviewed_on=registry['reviewed_on'], knowledge_basis=registry['knowledge_basis'],
        original_count=len(rows), retained_count=len(rows) - len(excluded),
        excluded_security_ids=excluded, rows=rows, full_domain_certified=False,
        point_in_time_certified=False, historical_observation_available_at_decision=False,
        optimization_calls=0, execution_calls=0)


def guarded_search_arguments(arguments, review):
    """Return a filtered copy; never silently alter or relabel an old input."""
    if arguments['decision_date'] != review['decision_date']:
        raise ValueError('GUARD_DECISION_MISMATCH')
    domain = set(arguments['metadata'])
    if domain != {row['security_id'] for row in review['rows']}:
        raise ValueError('GUARD_DOMAIN_MISMATCH')
    if set(arguments['prices']) != domain or any(set(row) != domain for row in arguments['training_scenarios']):
        raise ValueError('SEARCH_INPUT_DOMAIN_MISMATCH')
    removed = set(review['excluded_security_ids'])
    result = deepcopy(arguments)
    result['metadata'] = {key: value for key, value in result['metadata'].items() if key not in removed}
    result['prices'] = {key: value for key, value in result['prices'].items() if key not in removed}
    result['training_scenarios'] = [{key: value for key, value in row.items() if key not in removed}
                                    for row in result['training_scenarios']]
    return result
