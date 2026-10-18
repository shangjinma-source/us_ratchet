"""Pure historical 127-observation comparison; no engine, fit, or source I/O."""
import bisect
import csv
import io
from datetime import date
from decimal import Decimal, localcontext


def number(value):
    if type(value) not in (str, int, float, Decimal):
        raise ValueError('Finite nonboolean numeric value required')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Finite numeric value required')
    return result


def session(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Canonical observation date required')
    return value


def check_calendar(calendar):
    if type(calendar) is not list or len(calendar) != 127 or calendar != sorted(set(calendar)):
        raise ValueError('127 unique ordered observations required')
    for day in calendar:
        session(day)
    if calendar[0] != '2026-03-18' or calendar[1] != '2026-03-19' or calendar[-1] != '2026-09-17':
        raise ValueError('Historical baseline and forward observation boundary differ')


def metrics(values):
    if len(values) != 127:
        raise ValueError('127 values and 126 return intervals required')
    values = [number(value) for value in values]
    if any(value <= 0 for value in values):
        raise ValueError('Positive account or NAV values required')
    with localcontext() as context:
        context.prec = 50
        ratio = values[-1] / values[0]
        peak = values[0]
        drawdown = Decimal(0)
        for value in values:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        return dict(path_return=str(ratio - 1), annualized_return_252_over_126=str(ratio ** 2 - 1),
                    path_max_drawdown=str(drawdown), observation_count=127, return_interval_count=126,
                    annualization_is_historical_window_diagnostic=True)


def nav_observations(calendar, raw_csv):
    check_calendar(calendar)
    if type(raw_csv) is not str:
        raise ValueError('Original decoded NAV CSV required')
    reader = csv.DictReader(io.StringIO(raw_csv))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not {'Date', 'Close'} <= set(reader.fieldnames):
        raise ValueError('Unique NAV Date and Close fields required')
    records = list(reader)
    dates = [session(row['Date']) for row in records]
    if not dates or dates != sorted(set(dates)):
        raise ValueError('Unique ascending original NAV dates required')
    values = [number(row['Close']) for row in records]
    if any(value <= 0 for value in values):
        raise ValueError('Positive original NAV required')
    mapped = []
    for day in calendar:
        index = bisect.bisect_right(dates, day) - 1
        if index < 0:
            raise ValueError('No prior NAV observation; future fill forbidden')
        mapped.append(dict(session=day, nav_source_date=dates[index], nav=str(values[index]),
                           same_date=dates[index] == day, known_published_by_us_session_cutoff=False))
    return dict(rows=mapped, same_date_missing_count=sum(not row['same_date'] for row in mapped),
                alignment='BACKWARD_OBSERVATION_DATE_ONLY_NOT_PUBLICATION_TIME',
                original_currency_only=True, future_nav_observation_used=False,
                publication_time_verified=False, fx_applied=False, legal_comparison_ready=False)


def compare(*, calendar, candidate_daily, incumbent_daily, nav_csv):
    check_calendar(calendar)
    for daily in (candidate_daily, incumbent_daily):
        if [row['session'] for row in daily] != calendar or number(daily[0]['total_value_usd']) != 25000:
            raise ValueError('Common 127-day account and original 25000 baseline required')
    candidate = metrics([row['total_value_usd'] for row in candidate_daily])
    incumbent = metrics([row['total_value_usd'] for row in incumbent_daily])
    nav = nav_observations(calendar, nav_csv)
    references = dict(original_incumbent=incumbent,
                      nav_012922_native_currency=metrics([row['nav'] for row in nav['rows']]))
    with localcontext() as context:
        context.prec = 50
        differences = {name: {key: str(number(candidate[key]) - number(reference[key]))
                              for key in ('path_return', 'annualized_return_252_over_126', 'path_max_drawdown')}
                       for name, reference in references.items()}
    return dict(schema='PURE_SINGLE_WINDOW_DUAL_REFERENCE_METRICS_V1', calendar=list(calendar),
                candidate=candidate, references=references, nav=nav, candidate_minus_reference=differences,
                difference_semantics='RETURN_POSITIVE_IS_HIGHER_DRAWDOWN_POSITIVE_IS_WORSE',
                source_bytes_authenticated=False, ledger_accounting_verified=False, engine_called=False,
                fitter_called=False, winner_selected=False, formal_dual_benchmark_admission=False,
                currency_fx_equivalence_verified=False, subscription_redemption_fee_equivalence_verified=False,
                dividend_cash_flows_modelled=False, point_in_time_verified=False,
                future_one_year_oos_evaluation_performed=False, promotion_allowed=False)
