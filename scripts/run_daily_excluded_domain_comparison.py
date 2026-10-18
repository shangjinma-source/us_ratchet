"""Independent, explicit excluded-domain daily experiment. No production changes."""
import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data.current_research_capital_decision_v2 import REQUIRED_PINS
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
from backtest.current_quantity_v2_daily_next_open import run_daily_next_open
from backtest.current_quantity_v2_simple253_next_open import run_simple253_next_open
from backtest.current_quantity_v2_simple253 import validate_training, compare_saved_v2_states
from backtest.current_quantity_v2_risk_next_open import run_risk_next_open
from backtest.current_quantity_v2_signal_history import build_signal_history_resolver
from backtest.continuous_calendar_year_metrics import calendar_year_metrics

ARMS = ('B0', 'B1', 'R1', 'R2')
SCOPE = 'CURRENT_OBSERVED_DOMAIN_MINUS_UNVERIFIABLE_TRI_NOT_PIT'
CODE = tuple(REQUIRED_PINS) + (
    'scripts/run_daily_excluded_domain_comparison.py',
    'backtest/current_quantity_v2_daily_next_open.py',
    'backtest/current_quantity_v2_simple253_next_open.py',
    'backtest/current_quantity_v2_simple253.py',
    'backtest/current_quantity_v2_risk_next_open.py',
    'backtest/current_quantity_v2_risk_overlays.py',
    'backtest/current_quantity_v2_signal_history.py',
    'backtest/current_quantity_v2_next_open_book.py',
    'backtest/continuous_calendar_year_metrics.py',
    'backtest/return_priority_monthly_quantity_provider_v4.py',
    'backtest/return_priority_monthly_execution_inputs_v4.py',
)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def simple_training_windows(windows, monthly_inputs):
    """Adapt annual draft labels to the existing simple-rule interface only.

    Eligibility is exactly the already assembled monthly domain; no source,
    coordinate, PIT or execution certification is conferred by the label.
    """
    by_date = {window['decision_cutoff']: window for window in windows}
    if len(by_date) != len(windows) or set(by_date) != {w['decision_date'] for w in monthly_inputs}:
        raise ValueError('TRAINING_MONTH_DOMAIN_MISMATCH')
    result = []
    for monthly in monthly_inputs:
        window = deepcopy(by_date[monthly['decision_date']])
        domain = set(monthly['search_arguments']['prices'])
        rows = [row for row in window['candidates'] if row['security_id'] in domain]
        if len(rows) != len(domain) or {row['security_id'] for row in rows} != domain:
            raise ValueError('EXACT_SIMPLE_TRAINING_DOMAIN_REQUIRED')
        for row in rows:
            if row['status'] == 'DRAFT_CONDITIONAL_INPUT_COMPUTED':
                guard = row['identity_history_guard']
                if (guard['status'] != 'READY_CONDITIONAL_IDENTITY_HISTORY' or
                        guard['window_dates'] != window['training_dates'] or guard['missing_or_invalid_dates'] or
                        guard['security_id'] != row['security_id'] or guard['ticker'] != row['ticker'] or
                        guard['decision_date'] != monthly['decision_date'] or
                        guard['required_closes'] != 253 or guard['valid_regular_closes'] != 253 or
                        guard['pre_regular_dates'] or guard['reasons']):
                    raise ValueError('ANNUAL_TRAINING_IDENTITY_GUARD_REQUIRED')
                row['source_candidate_status'] = row['status']
                row['status'] = 'READY_CONDITIONAL'
            elif row['status'] != 'READY_CONDITIONAL':
                raise ValueError('UNSUPPORTED_SIMPLE_TRAINING_STATUS')
        window['candidates'] = rows
        result.append(window)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared', required=True)
    parser.add_argument('--schedule', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--arm', choices=ARMS + ('all',), default='all')
    parser.add_argument('--fee-bps', required=True)
    parser.add_argument('--slippage-bps', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--baseline-outcome', help='Optional existing COMPLETE B0 from the identical prepared input; never rerun it.')
    args = parser.parse_args()
    out = (ROOT / args.output).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'tmp'):
        raise ValueError('NEW_TMP_OUTPUT_REQUIRED')
    out.mkdir(parents=True)
    write(out / 'started.json', dict(started_at=stamp(), arguments=vars(args)))
    pins = {}

    def read(path, expected=None):
        absolute = (ROOT / path).resolve()
        key = absolute.relative_to(ROOT).as_posix()
        raw = absolute.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and expected != digest:
            raise ValueError('SOURCE_DRIFT:' + key)
        if key in pins and pins[key] != digest:
            raise ValueError('SOURCE_PIN_CONFLICT:' + key)
        pins[key] = digest
        return raw

    def recheck():
        for name, digest in list(pins.items()):
            read(name, digest)

    try:
        fee, slip = Fraction(args.fee_bps), Fraction(args.slippage_bps)
        if fee < 0 or not 0 <= slip < 10000:
            raise ValueError('INVALID_COST_MODEL')
        prepared_raw = read(args.prepared)
        prepared_sha256 = hashlib.sha256(prepared_raw).hexdigest()
        prepared = json.loads(prepared_raw)
        if prepared.get('experiment_scope') != SCOPE or prepared.get('excluded_issuers') != ['issuer:0001075124']:
            raise ValueError('EXPLICIT_AUTHORIZED_EXCLUSION_SCOPE_REQUIRED')
        for name, digest in prepared['source_hashes'].items():
            read(name, digest)
        for name in CODE:
            read(name)
        schedule_key = (ROOT / args.schedule).resolve().relative_to(ROOT).as_posix()
        if schedule_key not in pins:
            raise ValueError('SCHEDULE_NOT_BOUND_BY_PREPARED')
        schedule = json.loads(read(schedule_key, pins[schedule_key]))
        for name, digest in schedule.get('source_hashes', {}).items():
            read(name, digest)
        selected = ARMS if args.arm == 'all' else (args.arm,)
        if args.baseline_outcome and 'B0' in selected:
            raise ValueError('EXISTING_BASELINE_REQUIRES_SINGLE_NON_B0_ARM')
        risk = None
        if any(arm in ('R1', 'R2') for arm in selected):
            manifest_key = prepared['risk_history_manifest']
            snapshot_key = prepared['risk_history_snapshots']
            if manifest_key not in pins or snapshot_key not in pins:
                raise ValueError('RISK_FILES_NOT_BOUND_BY_PREPARED')
            manifest = json.loads(read(manifest_key, pins[manifest_key]))
            for name, digest in manifest['source_hashes'].items():
                read(name, digest)
            raw = read(snapshot_key, manifest['snapshot_sha256'])
            rows = [json.loads(line) for line in gzip.decompress(raw).decode('utf-8').splitlines()]
            snapshots = {row['decision_date']: row['snapshot'] for row in rows}
            if len(snapshots) != len(rows) or len(rows) != manifest['snapshot_count']:
                raise ValueError('DUPLICATE_OR_MISSING_RISK_SNAPSHOTS')
            if list(snapshots) != prepared['session_dates']:
                raise ValueError('RISK_SNAPSHOT_SESSION_MISMATCH')
            risk = snapshots
        # Extend only this in-memory experiment; old artifacts remain unchanged.
        prepared['source_hashes'] = dict(pins)
        assembled = assemble_monthly_execution_inputs_v4(prepared)
        if assembled['session_dates'] != prepared['session_dates']:
            raise ValueError('ASSEMBLER_CALENDAR_CHANGED')
        if not set(assembled['session_dates']) <= set(schedule['session_dates']):
            raise ValueError('EXECUTION_CALENDAR_NOT_COVERED')
        training = prepared['windows']
        if 'B1' in selected:
            training = simple_training_windows(training, assembled['monthly_inputs'])
            by_date = {window['decision_cutoff']: window for window in training}
            if len(by_date) != len(training) or set(by_date) != {w['decision_date'] for w in assembled['monthly_inputs']}:
                raise ValueError('TRAINING_MONTH_DOMAIN_MISMATCH')
            calendar = sorted({day for window in training for day in window['training_dates']})
            for window in assembled['monthly_inputs']:
                validate_training(window=by_date[window['decision_date']],
                                  arguments=window['search_arguments'], calendar=calendar)
        baseline = None
        if args.baseline_outcome:
            baseline_path = Path(args.baseline_outcome)
            baseline = json.loads(read(baseline_path))
            prior = json.loads(read(baseline_path.parent / 'preflight.json'))
            terminal = json.loads(read(baseline_path.parent / 'terminal.json'))
            if baseline['status'] != 'COMPLETE' or terminal.get('status') != 'COMPLETE' or terminal.get('source_pins_unchanged') is not True:
                raise ValueError('COMPLETE_BASELINE_REQUIRED')
            if prior.get('prepared_sha256') != prepared_sha256 or prior.get('policy') != 'DAILY_CLOSE_SIGNAL_NEXT_OPEN_EXECUTION_NOT_PULLBACK':
                raise ValueError('IDENTICAL_INPUT_BASELINE_REQUIRED')
            for key, expected in [('initial_cash', '20000'), ('fee_bps', args.fee_bps), ('slippage_bps', args.slippage_bps)]:
                if Fraction(str(prior[key])) != Fraction(expected):
                    raise ValueError('BASELINE_COST_OR_CAPITAL_MISMATCH')
            if [row['date'] for row in baseline['daily_ledger']] != assembled['session_dates'][1:]:
                raise ValueError('BASELINE_CALENDAR_MISMATCH')
            for name, digest in prior['source_hashes'].items():
                read(name, digest)
        recheck()
        write(out / 'preflight.json', dict(status='PREFLIGHT_PASSED', source_hashes=pins,
            prepared_sha256=prepared_sha256,
            arms=list(selected), initial_cash='20000', fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
            experiment_scope=SCOPE, excluded_issuers=prepared['excluded_issuers'],
            sessions=[assembled['session_dates'][0], assembled['session_dates'][-1]],
            monthly_windows=len(assembled['monthly_inputs']), independent_oos=False,
            simple_training_status_adapter='ASSEMBLED_DOMAIN_ONLY; SOURCE_STATUS_RETAINED; NO_CERTIFICATION',
            production_changed=False, point_in_time_certified=False, ordinary_dividends_included=False,
            action_accounting_fully_certified=False, source_scope='CONDITIONAL_RESEARCH_ONLY; ASSEMBLY_IS_NOT_MARKET_DATA_CERTIFICATION',
            execution_policy='COMPLETED_CLOSE_SIGNAL_NEXT_OPEN_SELL_FIRST_RESEARCH_MODEL'))
        if not args.execute:
            write(out / 'terminal.json', dict(status='PREFLIGHT_ONLY', finished_at=stamp(), book_calls=0))
            return
        summaries = {}
        for arm in selected:
            destination = out / arm
            destination.mkdir()
            write(destination / 'started.json', dict(started_at=stamp(), arm=arm, initial_cash='20000'))
            try:
                recheck()
                def progress(row):
                    with (destination / 'progress.jsonl').open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps(dict(row, observed_at=stamp()), ensure_ascii=False) + '\n')
                common = dict(assembled=deepcopy(assembled), ohlc=deepcopy(prepared['ohlc']),
                              initial_cash='20000', fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
                              progress=progress)
                if arm == 'B0':
                    result = run_daily_next_open(**common)
                elif arm == 'B1':
                    if baseline is not None:
                        comparison = compare_saved_v2_states(outcome=baseline, training_windows=training)
                        if [row['decision_date'] for row in comparison] != [w['decision_date'] for w in assembled['monthly_inputs']]:
                            raise ValueError('BASELINE_COMPARISON_MONTHS_MISMATCH')
                        write(destination / 'same_state_comparison.json', comparison)
                    result = run_simple253_next_open(**common, training_windows=deepcopy(training))
                else:
                    resolver = build_signal_history_resolver(session_dates=schedule['session_dates'],
                        session_close_times=schedule, snapshots=risk)
                    result = run_risk_next_open(**common, policy=arm, history_resolver=resolver)
                write(destination / 'outcome.json', result)
                recheck()
                metrics = dict(status=result['status'], reason=result.get('reason'),
                    total_return=result.get('total_return'), drawdown=result.get('drawdown'),
                    annualized_return=None, calendar_year_returns_not_computed=True,
                    experiment_scope=SCOPE, independent_oos=False, point_in_time_certified=False)
                if result['status'] == 'COMPLETE':
                    years = calendar_year_metrics(opening_date=assembled['session_dates'][0], opening_equity='20000',
                        daily_ledger=result['daily_ledger'], expected_sessions=assembled['session_dates'][1:],
                        report_through=assembled['session_dates'][-1])
                    elapsed = (date.fromisoformat(assembled['session_dates'][-1]) - date.fromisoformat(assembled['session_dates'][0])).days
                    metrics.update(annualized_return=float(1 + Fraction(result['total_return'])) ** (365 / elapsed) - 1,
                                   calendar_year_returns_not_computed=False)
                    write(destination / 'calendar_year_metrics.json', years)
                write(destination / 'metrics.json', metrics)
                summaries[arm] = metrics
                write(destination / 'terminal.json', dict(status=result['status'], finished_at=stamp(), source_pins_unchanged=True))
            except Exception as error:
                summaries[arm] = dict(status='ERROR', error=type(error).__name__ + ':' + str(error))
                write(destination / 'terminal.json', dict(summaries[arm], finished_at=stamp()))
                # Source drift invalidates the common experiment, not just one arm.
                recheck()
        write(out / 'summary.json', summaries)
        overall = 'COMPLETE' if all(row['status'] == 'COMPLETE' for row in summaries.values()) else 'INCOMPLETE'
        write(out / 'terminal.json', dict(status=overall, finished_at=stamp(), arms=list(selected)))
    except Exception as error:
        write(out / 'terminal.json', dict(status='ERROR', finished_at=stamp(), error=type(error).__name__ + ':' + str(error)))
        raise


if __name__ == '__main__':
    main()
