"""Prepare both saved USD target modes; never rank, pool missing windows, or fit."""
from copy import deepcopy
from bisect import bisect_right
from datetime import date
from decimal import Decimal, Context, localcontext
from fractions import Fraction
import hashlib
import json
import math

CUTOFFS = ('2026-03-31', '2026-04-30', '2026-05-29', '2026-06-30', '2026-07-31', '2026-08-31')
MODES = ('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')
CONTRACT = dict(decision_cutoffs=list(CUTOFFS), price_count=505, return_count=504,
                fit_return_count=126, evaluation_return_count=126, step_return_count=21,
                window_count=13, target_modes=list(MODES),
                native_cny_role='SOURCE_CONTEXT_NOT_USD_RANKING_TARGET',
                missing_policy='KEEP_SLOTS_BLOCK_FULL13_NO_PARTIAL_POOL',
                mode_selection_using_results_allowed=False)
ALIGNMENT_FALSE = ('source_bytes_verified', 'historical_nav_currency_verified',
                   'historical_available_at_verified', 'point_in_time_verified',
                   'provider_binding_verified', 'benchmark_qualified',
                   'formal_admission_allowed', 'account_executed', 'returns_computed',
                   'drawdown_computed', 'mode_selected_using_results', 'fit_performed',
                   'execution_authorized', 'fx_is_close_price', 'fx_is_executable_price')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def exact(left, right, message):
    require(digest(left) == digest(right), message)


def positive_ratio(value):
    require(type(value) is str and value and value.strip() == value, 'Exact ratio text')
    result = Fraction(value)
    require(result > 0, 'Positive observation')
    return result


def validate_saved_relations(alignment):
    """Internal saved-row consistency only; does not authenticate any source file."""
    nav_rows, fx_rows = alignment['nav_rows_preserved'], alignment['fx_rows_preserved']
    require(type(nav_rows) is list and type(fx_rows) is list, 'Preserved source arrays')
    def dates(rows):
        values = [r['date'] for r in rows]
        require(all(type(d) is str and date.fromisoformat(d).isoformat() == d for d in values)
                and values == sorted(set(values)), 'Canonical unique observation dates')
        return values
    nav_dates, fx_dates = dates(nav_rows), dates(fx_rows)
    def row_reference(reference, parent, index, kind):
        require(type(reference) is dict, 'Observation source reference')
        keys = {'path', 'sha256'}
        pointer_keys = {'row_index', 'csv_record_number'} if kind == 'NAV' else {'table_row_index', 'html_line'}
        require(set(reference) in (keys, keys | pointer_keys), 'Explicit observation pointer shape')
        exact({key: reference[key] for key in keys}, parent, 'Observation source role')
        if set(reference) != keys:
            ordinal = 'row_index' if kind == 'NAV' else 'table_row_index'
            require(type(reference[ordinal]) is int and reference[ordinal] == index, 'Original source row ordinal')
            location = 'csv_record_number' if kind == 'NAV' else 'html_line'
            require(type(reference[location]) is int and reference[location] > 0, 'Original source location')
            if kind == 'NAV':
                require(reference[location] == index + 2, 'CSV header and row location')
    nav_values = []
    for i, row in enumerate(nav_rows):
        require(row['available_at'] is None, 'Unknown NAV publication preserved')
        row_reference(row['source_reference'], alignment['nav_reference'], i, 'NAV')
        nav_values.append(positive_ratio(row['nav_cny_decimal']))
    fx_values, valid = [], []
    fx_ref = alignment['fx_context_preserved']['source_references']['china_history']['raw']
    for i, row in enumerate(fx_rows):
        require(row['historical_available_at'] is None, 'Unknown FX publication preserved')
        row_reference(row['source_reference'], fx_ref, i, 'FX')
        if row['status'] == 'NOT_AVAILABLE_ND':
            require(row['rate_decimal'] is None and row['rate_literal'] == 'ND', 'Original ND state')
            value = None
        else:
            require(row['status'] == 'REPORTED_RATE', 'Known FX state')
            value = positive_ratio(row['rate_decimal'])
            require(positive_ratio(row['rate_literal']) == value, 'Original FX literal')
            valid.append(i)
        fx_values.append(value)
    valid_dates = [fx_dates[i] for i in valid]
    same_indexes = {d: i for i, d in enumerate(fx_dates)}
    for row in alignment['rows']:
        session = row['session']
        ni = bisect_right(nav_dates, session) - 1
        ni = None if ni < 0 else ni
        nav = row['nav_observation']
        if ni is None:
            require(nav is None, 'No prior NAV observation')
        else:
            exact(nav, dict(date=nav_dates[ni], lag_calendar_days=(date.fromisoformat(session)-date.fromisoformat(nav_dates[ni])).days,
                           original_row_index=ni, original_row=nav_rows[ni], nav_cny_exact=str(nav_values[ni]), available_at=None),
                  'NAV selected row and original pointer')
        vi = bisect_right(valid_dates, session) - 1
        selected = (same_indexes.get(session), valid[vi] if vi >= 0 else None)
        for mode, key, fi in zip(MODES, ('same_date', 'backward_valid'), selected):
            fx = row['session_fx'][key]
            if fi is None:
                require(fx is None, 'No selected FX observation')
            else:
                exact(fx, dict(date=fx_dates[fi], lag_calendar_days=(date.fromisoformat(session)-date.fromisoformat(fx_dates[fi])).days,
                               original_row_index=fi, original_row=fx_rows[fi],
                               rate_exact=None if fx_values[fi] is None else str(fx_values[fi]), historical_available_at=None),
                      'FX mode selected row and original pointer')
            rate = None if fi is None else fx_values[fi]
            reason = ('NO_PRIOR_NAV_OBSERVATION' if ni is None else
                      'NO_SAME_SESSION_FX_ROW' if mode == MODES[0] and fi is None else
                      'SAME_SESSION_FX_ND' if mode == MODES[0] and rate is None else
                      'NO_PRIOR_VALID_FX_OBSERVATION' if rate is None else None)
            value = None if reason else nav_values[ni] / rate
            with localcontext(Context(prec=80)):
                display = None if value is None else str(Decimal(value.numerator) / Decimal(value.denominator))
            exact(row['conversions'][mode], dict(status='MISSING_ALIGNMENT_INPUT' if reason else 'CONDITIONAL_NAV_USD_OBSERVATION',
                  reason=reason, nav_usd_exact=None if value is None else str(value), nav_usd_decimal=display,
                  nav_date=None if ni is None else nav_dates[ni], fx_date=None if fi is None else fx_dates[fi],
                  fx_original_row_index=fi, nav_original_row_index=ni, denominator_basis='SESSION_ALIGNED_FX_NOT_NAV_DATE_FX'),
                  'Conversion consistent with saved observations')


def prepare_target_scoring_inputs(*, alignment, alignment_reference,
                                  reference_calendar, contract):
    """Validate saved alignment claims and derive adjacent returns, not source authority."""
    exact(contract, CONTRACT, 'Explicit six505/two-mode preparation contract')
    require(type(alignment_reference) is dict and set(alignment_reference) == {'path', 'sha256'},
            'Exact alignment reference')
    path, sha = alignment_reference['path'], alignment_reference['sha256']
    require(type(path) is str and path and path.strip() == path and type(sha) is str
            and len(sha) == 64 and set(sha) <= set('0123456789abcdef'), 'Alignment path/SHA')
    require(alignment['schema'] == 'NAV_USD_OBSERVATION_ALIGNMENT_V1'
            and alignment['status'] == 'CONDITIONAL_HISTORICAL_CONVERSION_ONLY', 'Alignment schema/status')
    for flag in ALIGNMENT_FALSE:
        require(alignment[flag] is False, 'Alignment authority: ' + flag)
    require(alignment['source_claims_not_full_transitive_verification'] is True, 'Source scope')
    exact(alignment['modes'], list(MODES), 'Both original modes required')
    exact(alignment['conversion_formula'], 'BACKWARD_NAV_CNY / SESSION_ALIGNED_CNY_PER_USD', 'Original conversion')
    unsigned = deepcopy(alignment)
    checksum = unsigned.pop('content_sha256')
    require(digest(unsigned) == checksum, 'Alignment content checksum')
    calendar = reference_calendar
    require(type(calendar) is list and 505 <= len(calendar) <= 10000
            and calendar == sorted(set(calendar)), 'Complete ordered reference calendar')
    require(all(type(day) is str and date.fromisoformat(day).isoformat() == day
                and date.fromisoformat(day).weekday() < 5 for day in calendar), 'Canonical sessions')
    require(all(day in calendar and calendar.index(day) >= 504 for day in CUTOFFS), 'Full505 predecessors')
    first = calendar.index(CUTOFFS[0]) - 504
    sessions = calendar[first:calendar.index(CUTOFFS[-1]) + 1]
    exact(alignment['session_dates'], sessions, 'Exact union; no truncation or future suffix')
    exact([row['session'] for row in alignment['rows']], sessions, 'Original aligned slots')
    validate_saved_relations(alignment)
    modes = []
    for mode in MODES:
        values, slots = [], []
        for row in alignment['rows']:
            require(row['nav_date_fx_used_for_conversion'] is False, 'Session FX required')
            conversion = row['conversions'][mode]
            require(conversion['denominator_basis'] == 'SESSION_ALIGNED_FX_NOT_NAV_DATE_FX', 'FX basis')
            literal = conversion['nav_usd_exact']
            if literal is None:
                require(conversion['status'] == 'MISSING_ALIGNMENT_INPUT'
                        and type(conversion['reason']) is str and conversion['reason'], 'Explicit missing reason')
                value = None
            else:
                require(conversion['status'] == 'CONDITIONAL_NAV_USD_OBSERVATION'
                        and conversion['reason'] is None, 'Numeric alignment status')
                value = positive_ratio(literal)
                require(type(conversion['nav_date']) is str and conversion['nav_date'] <= row['session']
                        and type(conversion['fx_date']) is str and conversion['fx_date'] <= row['session'], 'No forward observation')
                if mode == MODES[0]:
                    require(conversion['fx_date'] == row['session'], 'Strict same-session FX')
            values.append(value)
            slots.append(dict(session=row['session'], conversion_preserved=deepcopy(conversion)))
        returns = []
        for index in range(1, len(sessions)):
            previous, current = values[index - 1:index + 1]
            value = None if previous is None or current is None else current / previous - 1
            floating = None if value is None else float(value)
            require(floating is None or math.isfinite(floating) and floating > -1, 'Fitter float boundary')
            returns.append(dict(previous_session=sessions[index - 1], session=sessions[index],
                                return_exact=None if value is None else str(value), return_float=floating,
                                status='BLOCKED_RETURN_SLOT' if value is None else 'CONDITIONAL_NUMERIC_RETURN'))
        decisions = []
        for cutoff in CUTOFFS:
            end = sessions.index(cutoff)
            start = end - 504
            windows = []
            for ordinal in range(13):
                left = start + ordinal * 21
                missing = [sessions[i] for i in range(left, left + 253) if values[i] is None]
                windows.append(dict(window_index=ordinal, training_price_predecessor=sessions[left],
                                    training_freeze_close=sessions[left + 126],
                                    evaluation_first_return_end=sessions[left + 127],
                                    evaluation_last_return_end=sessions[left + 252],
                                    training_return_index_start=left, training_return_index_stop=left + 126,
                                    evaluation_return_index_start=left + 126, evaluation_return_index_stop=left + 252,
                                    missing_price_sessions=missing,
                                    status='BLOCKED_WINDOW' if missing else 'CONDITIONAL_NUMERIC_WINDOW'))
            complete = all(not window['missing_price_sessions'] for window in windows)
            decisions.append(dict(cutoff=cutoff, required_price_dates=sessions[start:end + 1],
                                  required_return_count=504, windows=windows, window_count=13,
                                  complete_thirteen_window_numeric_supply=complete,
                                  status='CONDITIONAL_ALL13_TARGET_SUPPLY' if complete else 'BLOCKED_FULL13_TARGET_SUPPLY',
                                  scoring_allowed=False, partial_window_pooling_allowed=False))
        modes.append(dict(mode=mode, price_slots=slots, return_slots=returns, decisions=decisions))
    result = dict(schema='MULTIDECISION_TARGET_SCORING_INPUTS_V1',
                  status='CONDITIONAL_INPUT_PREPARATION_NOT_SCORING', contract=deepcopy(contract),
                  alignment_reference=deepcopy(alignment_reference), alignment_preserved=deepcopy(alignment),
                  reference_calendar_preserved=deepcopy(calendar), session_dates=sessions, modes=modes,
                  source_bytes_authenticated=False, independent_alignment_verified=False,
                  point_in_time_verified=False, benchmark_qualified=False, score_computed=False,
                  fit_performed=False, account_executed=False, promotion_allowed=False,
                  mode_selected_using_results=False, partial_window_pooling_allowed=False,
                  missing_values_filled=False, returns_computed=True, historical_retrospective_only=True)
    result['content_sha256'] = digest(result)
    return result
