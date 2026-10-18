"""Reuse the audited original account; extract the exact 107-session benchmarks."""
import csv
from decimal import Context, Decimal, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive

BASE = ROOT / 'data/cache/research'
SOURCE = Path(__file__).resolve()
LOADED = {str(SOURCE): hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          str(archive.SOURCE): archive.drift.file_sha(archive.SOURCE)}
BOUND = {
    'control': ('incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json', '53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'),
    'oracle': ('incumbent_price_source_probe_20260912_v1/nominal_control_accounting_oracle_20260912.json', 'd9615b4fe0405ce71b0902045c25c8a482431e1bc4f8c4fd1a9654d7c51c5bee'),
    'nav': ('dynamic_frozen_v2/preference_retrospective_nav_20260912.json', 'e1bb2b71d777b39cea5526ce4cc39a7b90d281609d3d2b9d8d0a0dbaa8a28b33'),
    'schedule': ('return_lane_targets_20260923_v1/schedule.json', 'f5ee54df3651882791e4e6ecac548d0ec7847c44a9c551938d20c17c2cb23c70'),
    'linkage': ('return_lane_targets_20260923_v1/schedule_independent_linkage.json', 'f1529817338a022bb9831de9e4d08407a7eb7015098e085e43ea37506ac8ed0b'),
}
START, END = '2023-03-31', '2023-09-01'
CLOCK = [('2023-03-31', '2023-04-03'), ('2023-04-28', '2023-05-01'),
         ('2023-05-31', '2023-06-01'), ('2023-06-30', '2023-07-03'),
         ('2023-07-31', '2023-08-01'), ('2023-08-31', '2023-09-01')]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float, str, Decimal), 'Nonboolean numeric value required')
    result = Decimal(str(value))
    require(result.is_finite(), 'Finite value required')
    return result


def metrics(values):
    require(len(values) == 107, 'Exact 107-session metric denominator required')
    with localcontext(Context(prec=60)):
        numbers = [number(value) for value in values]
        require(all(value > 0 for value in numbers), 'Positive equity values required')
        ratio = numbers[-1] / numbers[0]
        peak, drawdown = numbers[0], Decimal(0)
        for value in numbers:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        return dict(path_return=str(ratio - 1), path_max_drawdown=str(drawdown),
            annualized_return_252_over_106=str(ratio ** (Decimal(252) / 106) - 1),
            observation_count=107, return_interval_count=106,
            annualization_is_historical_window_diagnostic=True)


def control_prefix(control, oracle, schedule):
    calendar = [day for day in schedule['calendar'] if START <= day <= END]
    require(len(calendar) == 107 and calendar == sorted(set(calendar))
        and calendar[0] == START and calendar[-1] == END, 'Exact observed 107-session calendar required')
    require(oracle['engine_reexecuted'] is False and oracle['daily_cash_shares_equity_rows_verified'] == 295
        and oracle['oracle_uses_raw_quotes'] is True, 'Full independent original-account oracle required')
    control_path = str(BASE / BOUND['control'][0])
    require(oracle['source_hashes'].get(control_path) == BOUND['control'][1], 'Oracle does not bind the original account')
    fixed, execution = control['original_fixed_schedule'], control['execution']
    require(all(number(fixed[key]) == expected for key, expected in
        dict(initial_cash_usd=25000, minimum_cash_buffer_usd=100, transaction_cost_bps=10).items()),
        'Fixed original capital and fees differ')
    require(execution['risk_is_order_gate'] is False and execution['original_target_weights_modified'] is False,
        'Original control was changed to candidate risk gating')
    require([(row['decision_date'], row['execution_date']) for row in schedule['schedule']] == CLOCK,
        'Candidate decision clock differs')
    selected = {key: [row for row in execution[key] if row[field] <= END]
        for key, field in [('daily', 'session'), ('decisions', 'decision_date'),
                           ('executions', 'session'), ('trades', 'session')]}
    require([row['session'] for row in selected['daily']] == calendar, 'Original account is not the exact calendar prefix')
    require([(row['decision_date'], row['execution_date']) for row in selected['decisions']] == CLOCK
        and [(row['decision_date'], row['session']) for row in selected['executions']] == CLOCK,
        'Same six decision and execution coordinates required')
    require(all(row['session'] in calendar for row in selected['trades']), 'Trade outside prefix')
    return calendar, dict(selected, original_weights=fixed['original_weights'],
        metrics=metrics([row['total_value_usd'] for row in selected['daily']]),
        accounting_basis='UNCHANGED_FULL_295_ROW_INDEPENDENT_ORACLE_REUSED',
        original_ledger_numerical_audit_repeated=False)


def nav_prefix(report, raw_csv, calendar):
    nav = report['nav']
    require(nav['publication_time_verified'] is False and nav['fx_modelled'] is False
        and nav['subscription_redemption_fees_modelled'] is False, 'NAV scope was upgraded')
    rows = [row for row in nav['rows'] if row['session'] <= END]
    require([row['session'] for row in rows] == calendar, 'NAV calendar differs')
    records = list(csv.DictReader(io.StringIO(raw_csv.decode('utf-8-sig'))))
    dates = [row['Date'] for row in records]
    require(dates == sorted(set(dates)), 'Duplicate or unordered NAV dates')
    mapping = {row['Date']: number(row['Close']) for row in records}
    with localcontext(Context(prec=60)):
        for row in rows:
            eligible = [day for day in dates if day <= row['session']]
            require(bool(eligible), 'No backward NAV observation')
            day = eligible[-1]
            require(day == row['nav_date'] and mapping[day] > 0
                and abs(number(row['nav']) - mapping[day]) <= Decimal('1e-10'), 'Backward NAV source mismatch')
            require(abs(number(row['equity_index']) - mapping[day] / number(rows[0]['nav'])) <= Decimal('1e-10'),
                'NAV equity normalization differs')
    return dict(role='012922_NATIVE_CURRENCY_RETROSPECTIVE_NAV', rows=rows,
        metrics=metrics([row['nav'] for row in rows]), publication_time_verified=False,
        currency_fx_equivalence_verified=False, subscription_redemption_fee_equivalence_verified=False)


def build():
    sources = dict(LOADED)

    def read(path, checksum):
        raw = Path(path).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == checksum, 'Bound source bytes differ')
        archive.merge(sources, {str(Path(path).resolve()): checksum})
        return raw

    documents = {key: json.loads(read(BASE / path, checksum)) for key, (path, checksum) in BOUND.items()}
    for document in documents.values():
        for key in ('source_hashes', 'historical_expected_source_hashes'):
            if key in document:
                archive.merge(sources, document[key])
    require(documents['linkage']['exact_schedule_reconstruction'] is True
        and documents['linkage']['schedule_reference'] == dict(path=str(BASE / BOUND['schedule'][0]), sha256=BOUND['schedule'][1]),
        'Independent schedule linkage differs')
    contract = archive.load_contract()
    archive.verify_expected_sources(sources, contract)
    calendar, control = control_prefix(documents['control'], documents['oracle'], documents['schedule'])
    paths = [path for path in documents['nav']['source_hashes'] if path.endswith('012922.csv')]
    require(len(paths) == 1, 'Unique immutable NAV CSV required')
    nav = nav_prefix(documents['nav'], read(paths[0], documents['nav']['source_hashes'][paths[0]]), calendar)
    return dict(schema='RETURN_SIX_PERIOD_REUSED_BENCHMARK_PREFIX_V1', calendar=calendar,
        decision_clock=CLOCK, incumbent=control, nav=nav, source_references={
            key: dict(path=str(BASE / path), sha256=checksum) for key, (path, checksum) in BOUND.items()},
        historical_expected_source_hashes=sources, archive_resolution=archive.verify_expected_sources(sources, contract),
        execution_rerun=False, fitter_called=False, old_control_accounting_repeated=False,
        risk_projection_recomputed=False, cash_dividends_modelled=False,
        historical_full_source_closure_verified=False, point_in_time_verified=False,
        formal_dual_benchmark_admission=False, promotion_allowed=False)


if __name__ == '__main__':
    value = build()
    output = BASE / 'return_six_period_benchmarks_20260923_v1/benchmarks.json'
    contract = archive.load_contract()
    require(archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) == value['archive_resolution'],
        'Sources changed before publication')
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    require(archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) == value['archive_resolution']
        and output.read_bytes() == raw, 'Published bytes or sources changed')
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(raw).hexdigest())))
