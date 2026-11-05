"""One real January account preflight; isolated state, 600 seconds, no parameter grid."""
import argparse
import gzip
import importlib.util
import json
import time
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.research import run_momentum_account_20261105 as base
from docs.candidates.downside_cap20_selection_20261105 import decide_observed_for_account, apply_downside_selection
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from scripts.run_old_continuous_probe_v1 import validate_selection_binding

ROOT = base.ROOT
NEW_SOURCES = [
    'scripts/research/run_downside_cap20_preflight_20261105.py',
    'docs/candidates/downside_cap20_selection_20261105.py',
    'backtest/downside_cap20_observer_20261105.py',
    'backtest/concentration_cap20_research_20261105.py',
]


def run(output):
    started = time.monotonic()
    def guard():
        base.need(time.monotonic() - started < 600, 'PREFLIGHT_600_SECOND_LIMIT')
    out = (ROOT / output).resolve()
    base.need(out.is_relative_to(ROOT / 'tmp'), 'ISOLATED_OUTPUT_REQUIRED')
    out.mkdir(parents=True, exist_ok=False)
    pins = {}
    try:
        freeze = base.read('research_contracts/momentum_account_execution_20261105/freeze.json')
        downside_freeze = base.read('research_contracts/downside_max10_20261105/freeze.json')
        pins.update(freeze['source_hashes'])
        pins.update(downside_freeze['source_hashes'])
        base.check(pins)
        base.inventory.PINS.clear()
        document, prices, review, legacy, proof = base.inventory.inputs('2024_2026', base.read(freeze['inventory_base_freeze']))
        pins.update(base.inventory.PINS)
        document, review = base.prepare_actions(window='2024_2026', document=document, prices=prices, review=review, pins=pins, freeze=freeze)
        training_path = 'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json'
        training = base.read(training_path)
        base.check(training['source_hashes'])
        pins.update(training['source_hashes'])
        windows = {}
        for outer in training['windows']:
            item = outer.get('window', outer)
            windows[item.get('decision_cutoff', item.get('decision_date'))] = item
        qprices = {}
        quote_paths = ['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin', 'data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']
        for name in quote_paths:
            raw = (ROOT / name).read_bytes()
            data = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)['chart']['result'][0]
            for stamp, close in zip(data['timestamp'], data['indicators']['quote'][0]['close']):
                if close is None:
                    continue
                day = datetime.fromtimestamp(stamp, tz=timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                value = F(str(close))
                base.need(day not in qprices or qprices[day] == value, 'QQQ_OVERLAP_CHANGED')
                qprices[day] = value
        manifest = base.read('research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json')['base_file_dependencies']
        for name in [training_path, *quote_paths]:
            base.need(base.digest(name) == manifest[name], 'FROZEN_TRAINING_CHANGED:' + name)
        for name in [*NEW_SOURCES, training_path, *quote_paths]:
            pins[name] = base.digest(name)
        assembled = deepcopy(document['assembled'])
        assembled['session_dates'] = [day for day in assembled['session_dates'] if day <= '2024-01-31']
        assembled['monthly_inputs'] = [item for item in assembled['monthly_inputs'] if item['decision_date'] == '2023-12-29']
        base.need(len(assembled['monthly_inputs']) == 1 and assembled['session_dates'][0] == '2023-12-29', 'FIXED_FIRST_MONTH')
        document = deepcopy(document)
        document['assembled'] = assembled
        # Select by ex-date only: later payment remains an outstanding receivable.
        all_dividends = document['dividend_events']
        document['dividend_events'] = [
            event for event in all_dividends
            if assembled['session_dates'][0] < event['ex_date'] <= assembled['session_dates'][-1]
        ]
        base.save(out / 'dividend_window_filter.json', dict(
            start_exclusive=assembled['session_dates'][0], end_inclusive=assembled['session_dates'][-1],
            original_count=len(all_dividends), retained_count=len(document['dividend_events']),
            payment_dates_unchanged=True))
        base.save(out / 'contract.json', dict(scope='ONE_MONTH_TECHNICAL_PREFLIGHT_NOT_FULL_ECONOMIC_RESULT', source_hashes=pins, max_seconds=600, cap='1/5', max_holdings=10, initial_cash='20000'))
        base.save(out / 'execution_inputs.json', dict(document=document, review=review))
        spec = importlib.util.spec_from_file_location('cap20_private_preflight_kernel', ROOT / 'docs/candidates/qqq_risk_budget_account_runner.py')
        kernel = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kernel)
        contexts = {}
        def select(**arguments):
            guard()
            day = arguments['decision_date']
            base.need(day == '2023-12-29' and not contexts, 'ONE_SELECTION_ONLY')
            item = windows[day]
            dates = item['training_dates']
            base.need(len(dates) == 253 and dates[-1] == day, 'TRAINING_DATES')
            candidates = {candidate['security_id']: candidate for candidate in item['candidates'] if candidate.get('security_id')}
            returns = {}
            for sid in arguments['search_arguments']['prices']:
                values = list(map(F, candidates[sid]['training_close']))
                base.need(len(values) == 253 and all(value > 0 for value in values), 'TRAINING_CLOSES')
                returns[sid] = dict(zip(dates[1:], [b / a - 1 for a, b in zip(values, values[1:])]))
            reference = dict(zip(dates[1:], [qprices[b] / qprices[a] - 1 for a, b in zip(dates, dates[1:])]))
            raw, sidecar = decide_observed_for_account(stock_returns=returns, qqq_reference=reference, research_source_hashes=pins, max_holdings=10, guard=guard, **arguments)
            validate_selection_binding(raw, arguments)
            contexts[day] = (deepcopy(arguments), returns, reference, sidecar)
            base.save(out / 'selection.json', dict(arguments=arguments, raw_selection=raw, sidecar=sidecar))
            return raw
        def rerank(raw):
            guard()
            arguments, returns, reference, sidecar = contexts[raw['decision_date']]
            selected = apply_downside_selection(raw=raw, sidecar=sidecar, stock_returns=returns, qqq_reference=reference, research_source_hashes=pins)
            gate = base.action_gate(window='2024_2026', arguments=arguments, selected=selected, until='2024-01-31', active='2024-01-02', document=document, prices=prices, review=review, legacy=legacy, proof=proof)
            base.save(out / 'decision.json', dict(selected=selected, gate=gate))
            base.need(gate['admitted'], 'ACTUAL_FIRST_MONTH_ACTION_GATE')
            return selected
        kernel.decide_continuous_guided_for_account = select
        kernel.rerank = rerank
        book = kernel.run_frontier_capped_next_open(assembled=assembled, ohlc=document['ohlc'], initial_cash='20000', fee_bps='0', slippage_bps='5', risk=MonthlyExitCoreResearchAdapter(assembled['actions']), max_new_searches=1, dividend_events=document['dividend_events'])
        base.save(out / 'book.json', book)
        guard()
        base.check(pins)
        base.need(book['status'] == 'COMPLETE', 'ACCOUNT_PREFLIGHT_INCOMPLETE')
        result = dict(status='PREFLIGHT_COMPLETE', sessions=len(book['daily_ledger']), selections=len(contexts), elapsed_seconds=time.monotonic()-started, economic_full_window_complete=False)
    except Exception as error:
        result = dict(status='PREFLIGHT_FAILED', error=type(error).__name__ + ':' + str(error), elapsed_seconds=time.monotonic()-started, economic_full_window_complete=False)
        base.save(out / 'summary.json', result)
        print(json.dumps(result))
        raise
    base.save(out / 'summary.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    run(parser.parse_args().output)
