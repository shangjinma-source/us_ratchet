"""Explicit contiguous-window NAV diagnostics; no alignment or account execution."""
from copy import deepcopy
from fractions import Fraction
import math

from backtest import ndx_same_window_nav_reference_metrics_research as saved_nav
from backtest.ndx_cash_fork_reference_window_research import metrics


def require(value, message):
    if not value:
        raise ValueError(message)


def account_twr_metrics(*, daily, calendar):
    """Use saved binary64 wealth including its existing initial observation."""
    saved_nav.dates(calendar)
    require(type(daily) is list and len(calendar) >= 2, 'Complete account window')
    require([row['session'] for row in daily] == calendar, 'Exact account calendar; no drop or prepend')
    wealth = []
    for row in daily:
        value = row['normalized_twr']
        require(type(value) in (int, float) and math.isfinite(value) and value > 0,
                'Positive finite saved TWR, not equity including flows')
        wealth.append(Fraction(value))
    return dict(metrics=metrics(calendar, wealth),
                arithmetic='EXACT_FRACTIONS_OF_SAVED_BINARY64_TWR_NOT_EXACT_ECONOMIC_VALUES',
                source_bytes_authenticated=False, account_returns_independently_reconciled=False,
                account_executed=False, formal_admission_allowed=False)


def reference_metrics(*, alignment, alignment_reference, reference_calendar):
    """Keep both saved FX modes; any missing point blocks that whole mode."""
    saved_nav.reference(alignment_reference)
    saved_nav.reference(reference_calendar['source_reference'])
    require(alignment['schema'] == 'NAV_USD_OBSERVATION_ALIGNMENT_V1' and
            alignment['status'] == 'CONDITIONAL_HISTORICAL_CONVERSION_ONLY', 'Saved conditional alignment')
    saved_nav.exact(alignment['modes'], list(saved_nav.MODES), 'Both original FX modes')
    require(alignment['conversion_formula'] == 'BACKWARD_NAV_CNY / SESSION_ALIGNED_CNY_PER_USD' and
            alignment['fx_context_preserved']['rate_direction'] == 'CNY_PER_USD', 'Session FX direction')
    for key in ('point_in_time_verified', 'historical_available_at_verified', 'benchmark_qualified',
                'formal_admission_allowed', 'account_executed', 'mode_selected_using_results',
                'fit_performed', 'execution_authorized'):
        require(alignment[key] is False, 'No inherited alignment authority')
    require(alignment['content_sha256'] == saved_nav.digest({k:v for k,v in alignment.items() if k != 'content_sha256'}), 'Alignment digest')
    full = alignment['session_dates']
    calendar = reference_calendar['dates']
    saved_nav.dates(full)
    saved_nav.dates(calendar)
    require(len(calendar) >= 2 and calendar[0] in full and calendar[-1] in full, 'Covered window')
    start, end = full.index(calendar[0]), full.index(calendar[-1])
    require(calendar == full[start:end+1], 'Contiguous source window; no calendar compression')
    require([row['session'] for row in alignment['rows']] == full, 'Complete original alignment rows')
    modes = {}
    for mode in saved_nav.MODES:
        values, observations, missing = [], [], []
        for index in range(start, end+1):
            row = alignment['rows'][index]
            conversion = row['conversions'][mode]
            require(conversion['denominator_basis'] == 'SESSION_ALIGNED_FX_NOT_NAV_DATE_FX' and
                    row['nav_date_fx_used_for_conversion'] is False, 'No NAV-date FX substitution')
            if conversion['status'] == 'MISSING_ALIGNMENT_INPUT':
                require(type(conversion['reason']) is str and conversion['reason'] and
                        conversion['nav_usd_exact'] is None and conversion['nav_usd_decimal'] is None, 'Preserved missing input')
                value = None
                missing.append(row['session'])
            else:
                require(conversion['status'] == 'CONDITIONAL_NAV_USD_OBSERVATION' and conversion['reason'] is None, 'Known conversion status')
                value = saved_nav.fraction(conversion['nav_usd_exact'])
            values.append(value)
            observations.append(dict(original_index=index, original_alignment_row=deepcopy(row),
                                     saved_value_exact=None if value is None else str(value)))
        modes[mode] = dict(mode=mode, missing_sessions=missing, observations=observations,
                           status='BLOCKED_MISSING_REFERENCE_INPUT' if missing else 'HISTORICAL_METRICS_COMPUTED',
                           metrics=None if missing else metrics(calendar, [v/values[0] for v in values]))
    return dict(schema='MULTIDECISION_CONTIGUOUS_NAV_REFERENCE_METRICS_V1',
                reference_calendar=deepcopy(reference_calendar), alignment_reference=deepcopy(alignment_reference),
                modes=modes, original_alignment_limitations=deepcopy(alignment['limitations']),
                original_fx_context=deepcopy(alignment['fx_context_preserved']),
                interpretation='EX_POST_EXTERNAL_NAV_REFERENCE_NOT_SUBSCRIPTION_ACCOUNT_OR_COHORT',
                source_bytes_authenticated=False, alignment_conversion_reaudited=False,
                **saved_nav.FLAGS)
