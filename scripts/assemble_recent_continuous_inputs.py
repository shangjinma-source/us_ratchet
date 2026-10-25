"""Assemble 36 fixed real windows; unresolved economic actions forbid execution."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.continuous_guided_account_decision import REQUIRED_PINS
from backtest.return_priority_monthly_execution_inputs import BASIS
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4


def assemble(training_path, execution_path):
    snapshots = {}
    def read(path):
        path = path.resolve(strict=True)
        if path not in snapshots:
            snapshots[path] = path.read_bytes()
        return snapshots[path]
    def digest(content):
        return sha256(content).hexdigest()
    training = json.loads(read(training_path))
    execution = json.loads(read(execution_path))
    if execution['training_snapshot_sha256'] != digest(read(training_path)):
        raise ValueError('TRAINING_EXECUTION_SNAPSHOT_MISMATCH')
    windows = training['windows']
    if len(windows) != 36 or any(w['status'] != 'READY_CONDITIONAL' or not w['compiled_search_arguments'] for w in windows):
        raise ValueError('ALL_36_WINDOWS_MUST_BE_READY')
    sessions = execution['session_dates']
    if sessions[0] != '2020-12-31' or sessions[-1] != '2023-12-29':
        raise ValueError('FIXED_CONTINUOUS_BOUNDARIES_REQUIRED')
    pins = {}
    for source in (training['source_hashes'], execution['source_hashes']):
        for filename, expected in source.items():
            if filename in pins and pins[filename] != expected:
                raise ValueError('CONFLICTING_SOURCE_HASH:' + filename)
            if digest(read(ROOT / filename)) != expected:
                raise ValueError('SOURCE_CHANGED:' + filename)
            pins[filename] = expected
    metadata, provenance, ohlc, tickers_by_sid = {}, {}, {}, {}
    needed = {sid for w in windows for sid in w['compiled_search_arguments']['metadata']}
    by_ticker = execution['ohlc_by_ticker']
    for source in training['fixed_sources']:
        sid, ticker = source['security_id'], source['ticker']
        meta = dict(ticker='META' if ticker in ('FB','META') else ticker, issuer_id=source['issuer_id'])
        bars = deepcopy(by_ticker[ticker])
        if source['calibration'] is None:
            if ticker != 'GEHC' or sid in needed:
                raise ValueError('UNCALIBRATED_REQUIRED_SECURITY:' + ticker)
            bars = {}  # Excluded in every compiled window; no invented calibration.
        if sid in metadata:
            if set(tickers_by_sid[sid] + [ticker]) != {'FB','META'} or meta != metadata[sid] or bars != ohlc[sid]:
                raise ValueError('UNREVIEWED_OR_INEXACT_IDENTITY_COLLISION:' + sid)
            if source['source'] != provenance[sid]['whole_source']:
                raise ValueError('ALIAS_SOURCE_MISMATCH')
            tickers_by_sid[sid].append(ticker)
            continue
        metadata[sid] = meta
        tickers_by_sid[sid] = [ticker]
        ohlc[sid] = bars
        provenance[sid] = dict(price_basis=BASIS, whole_source=source['source'])
    unexpected = [x for x in execution['anomalies'] if not (x.get('ticker') == 'GEHC' and x.get('kind') == 'CALIBRATION_MISSING')]
    if unexpected:
        raise ValueError('UNRESOLVED_PRICE_ANOMALIES:' + json.dumps(unexpected))
    compiled = []
    for window in windows:
        args = deepcopy(window['compiled_search_arguments'])
        original_domain = set(args['metadata'])
        for sid, meta in args['metadata'].items():
            if meta['ticker'] in ('FB','META'):
                meta['ticker'] = 'META'
            if meta != metadata[sid]:
                raise ValueError('WINDOW_IDENTITY_MISMATCH:' + sid)
        if original_domain != set(args['metadata']):
            raise ValueError('CANDIDATE_DOMAIN_CHANGED')
        day = window['decision_cutoff']
        compiled.append(dict(decision_date=day, active_date=sessions[sessions.index(day)+1], search_arguments=args))
    for filename in ('backtest/return_priority_fresh_cash_quantity_search.py',
            'backtest/return_priority_monthly_execution_inputs.py', 'backtest/return_priority_monthly_execution_inputs_v4.py',
            'backtest/historical_dividend_frontier_research.py', 'backtest/historical_dividend_next_open_book_research.py',
            'backtest/capped_frontier_rerank_research.py', 'scripts/audit_capped_training_frontier.py',
            'scripts/assemble_recent_continuous_inputs.py', *REQUIRED_PINS):
        pins[filename] = digest(read(ROOT / filename))
    for path in (training_path, execution_path):
        pins[path.resolve().relative_to(ROOT).as_posix()] = digest(read(path))
    prepared = dict(session_dates=sessions, source_hashes=pins, metadata=metadata, source_provenance=provenance,
        ohlc=ohlc, windows=compiled, split_events_reference_only=[], identity_migrations=[],
        cash_stock_merger_events=[], fractional_settlements={}, distribution_events=[],
        distribution_fractional_cash_values={}, supported_conversions=[], unsupported_conversions=[])
    result = assemble_monthly_execution_inputs_v4(prepared)
    aliases = [dict(security_id=sid, canonical_ticker='META', before='FB', after='META', effective_date='2022-06-09',
        exact_ohlc_equal=True, source_references=[r for s in training['fixed_sources'] if s['ticker']=='META' for r in s['identity_references']])
        for sid, names in tickers_by_sid.items() if set(names)=={'FB','META'}]
    for path, content in snapshots.items():
        if path.read_bytes() != content:
            raise ValueError('INPUT_CHANGED_DURING_ASSEMBLY:' + str(path))
    return dict(status='CONTINUOUS_SCHEMA_ASSEMBLED_ECONOMIC_EXECUTION_NOT_AUTHORIZED', prepared=prepared,
        assembled=result, ohlc=ohlc, dated_ticker_aliases=aliases, source_hashes=pins,
        execution_prices_sha256=digest(read(execution_path)),
        input_snapshot_hashes={str(p):digest(b) for p,b in snapshots.items()},
        training_exclusions=[dict(decision_date=w['decision_cutoff'], exclusions=w['training_exclusions']) for w in windows],
        provider_event_inventory=execution['provider_event_inventory'], action_stream_missing=execution['action_stream_missing'],
        execution_blockers=['SPLIT_MERGER_DIVIDEND_DISTRIBUTION_EVENTS_NOT_MAPPED_OR_EXPOSURE_REVIEWED'],
        runner_execution_authorized=False, dividend_events=None, search_calls=0, economic_run_completed=False,
        terminal_creates_new_decision=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training', type=Path, default=ROOT/'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json')
    parser.add_argument('--execution', type=Path, default=ROOT/'tmp/recent_execution_prices_20261026/execution_prices_v1.json')
    parser.add_argument('--output', type=Path, default=ROOT/'tmp/recent_execution_prices_20261026/continuous_assembled_v1.json')
    args = parser.parse_args()
    result = assemble(args.training, args.execution)
    pending = args.output.with_suffix('.pending.json')
    pending.write_text(json.dumps(result, indent=2), encoding='utf-8')
    pending.replace(args.output)
    print(json.dumps(dict(status=result['status'], windows=len(result['assembled']['monthly_inputs']),
        securities=len(result['ohlc']), sessions=len(result['assembled']['session_dates']))))


if __name__ == '__main__':
    main()
