"""Saved-source next12 NAV reference; no strategy, broker or fund-account runs."""
import hashlib
import json
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

from backtest.ndx_nav_usd_observation_alignment_research import align_nav_usd_observations

ROOT = Path(__file__).resolve().parents[1]


def metrics(values):
    if any(value is None for value in values):
        return None
    values = [Fraction(value) for value in values]
    peak, maximum = values[0], Fraction(0)
    for value in values:
        peak = max(peak, value)
        maximum = max(maximum, 1-value/peak)
    ratio = values[-1]/values[0]
    with localcontext() as context:
        context.prec = 50
        annualized = (Decimal(ratio.numerator)/Decimal(ratio.denominator)) ** (Decimal(252)/(len(values)-1))-1
    return dict(cumulative_return_exact=str(ratio-1), maximum_drawdown_exact=str(maximum),
                annualized_return_decimal=str(annualized),
                annualization=f'252/{len(values)-1} trading intervals;50digit decimal approximation',
                observation_count=len(values), interval_count=len(values)-1,
                normalized_curve=[str(value/values[0]) for value in values])


def main():
    sources = {}

    def read(path):
        raw = path.read_bytes(); sources[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    old_path = ROOT/'data/cache/research/nav_usd_observation_alignment_20261003_v1/alignment.json'
    saved = read(old_path)
    for name, expected in saved['source_hashes'].items():
        path = ROOT/name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Changed saved reference source: '+name)
        sources[str(path)] = actual
    original = saved['alignment']
    registration_path = ROOT/'tmp/next12_monthly_comparison_20261015_v1/registration.json'
    registration = read(registration_path)
    prepared_path = Path(registration['input_path'])
    prepared = read(prepared_path)
    if sources[str(prepared_path)] != registration['input_sha256']:
        raise ValueError('Changed comparison calendar source')
    days = prepared['session_dates']
    if len(days) != 251 or days[0] != '2025-07-31' or days[-1] != '2026-07-30':
        raise ValueError('Unexpected frozen next12 calendar')
    aligned = align_nav_usd_observations(session_dates=days,
        nav_rows=original['nav_rows_preserved'], fx_rows=original['fx_rows_preserved'],
        nav_reference=original['nav_reference'], fx_reference=original['fx_reference'],
        fx_context=original['fx_context_preserved'])
    modes = {}
    for mode in aligned['modes']:
        rows = [dict(session=row['session'], **row['conversions'][mode]) for row in aligned['rows']]
        modes[mode] = dict(rows=rows, missing_sessions=[row['session'] for row in rows if row['nav_usd_exact'] is None],
                           metrics=metrics([row['nav_usd_exact'] for row in rows]))
    nav_lags = [dict(session=row['session'], nav_date=row['nav_observation']['date'],
                     lag_calendar_days=row['nav_observation']['lag_calendar_days'])
                for row in aligned['rows'] if row['nav_observation']['lag_calendar_days']]
    report = dict(status='SAME_CALENDAR_CONDITIONAL_NAV_REFERENCE_NOT_FORMAL_ACCOUNT_COMPARISON',
                  period=[days[0], days[-1]], modes=modes, nav_lags=nav_lags,
                  alignment=aligned, source_hashes=sources,
                  source_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                     [Path(__file__), ROOT/'backtest/ndx_nav_usd_observation_alignment_research.py']},
                  missing_values_filled=False, calendar_compressed=False,
                  historical_available_at_verified=False, fund_subscription_account_modeled=False,
                  benchmark_qualified=False, formal_comparison_passed=False,
                  incumbent_comparison_available=False, percentile_statistics_computed=False,
                  search_calls=0, book_calls=0, network_calls=0,
                  limitations=['CNY NAV currency interval remains conditional; USD conversion uses CNY-per-USD noon observation.',
                               'Backward observations retain actual dates; no future NAV/FX selected.',
                               'Missing strict-mode rates block metrics; backward mode is separately disclosed.',
                               'Fund NAV and stock price-only ledgers have different economic scope.',
                               'No fund dealing costs, redemption timing or account cashflows modeled.',
                               'One historical path is not a distribution or independent future evidence.'])
    output = ROOT/'tmp/next12_nav_reference_20261015_v1.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(dict(output=str(output), modes={mode:dict(missing=len(value['missing_sessions']),
                          metrics=None if value['metrics'] is None else {k:v for k,v in value['metrics'].items() if k!='normalized_curve'})
                          for mode, value in modes.items()}, nav_lag_count=len(nav_lags))))


if __name__ == '__main__':
    main()
