"""Replay the one saved January selection after checking action exposure.

No new search, tuning, live-account write, or automatic retry is permitted.
"""
import argparse
from datetime import datetime, timezone, timedelta
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.historical_dividend_frontier_research import run_frontier_capped_next_open
from backtest.historical_dividend_independent_review import review
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest.capped_frontier_rerank_research import rerank
from backtest.capped_frontier_independent_review import review_selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--action-review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    deadline = datetime(2026, 10, 26, 3, tzinfo=timezone(timedelta(hours=8)))
    if datetime.now(timezone.utc) >= deadline:
        raise ValueError('USER_RESEARCH_DEADLINE_REACHED')
    inputs = json.loads(options.execution.read_text(encoding='utf-8'))
    selection_result = json.loads((options.selection/'result.json').read_text())
    input_sha = hashlib.sha256(options.execution.read_bytes()).hexdigest()
    if selection_result['input_sha256'] != input_sha:
        raise ValueError('EXECUTION_CHANGED_AFTER_SELECTION')
    for path, expected in inputs['source_hashes'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_CHANGED:'+path)
    prefix = json.loads((options.selection/'verified_prefix_candidate.json').read_text())
    if len(prefix) != 1 or prefix[0]['arguments']['account_state']['shares']:
        raise ValueError('ONE_INITIAL_CASH_SELECTION_REQUIRED')
    if hashlib.sha256((options.selection/'raw_selection.json').read_bytes()).hexdigest() != selection_result['raw_selection_sha256']:
        raise ValueError('RAW_SELECTION_CHANGED')
    raw = json.loads((options.selection/'raw_selection.json').read_text())
    if raw != prefix[0]['raw_selection']:
        raise ValueError('PREFIX_RAW_MISMATCH')
    selected = rerank(raw)
    review_selection(selected, rerank_enabled=True)
    if selected['target_quantities'] != selection_result['target_quantities']:
        raise ValueError('TARGET_MISMATCH')
    action_review = json.loads(options.action_review.read_text(encoding='utf-8'))
    if (action_review['status'] != 'CONDITIONAL_EMPTY_DIVIDEND_LIST_FOR_FIXED_EXPOSURE_ONLY'
            or action_review['targets'] != selected['target_quantities']
            or action_review['window'] != ['2022-01-01', '2022-01-31']
            or action_review['dividend_events'] != []
            or action_review['selection_sha256'] != hashlib.sha256((options.selection/'result.json').read_bytes()).hexdigest()):
        raise ValueError('ACTION_REVIEW_EXPOSURE_BINDING_MISMATCH')
    for row in action_review['rows']:
        if hashlib.sha256((ROOT/row['source']).read_bytes()).hexdigest() != row['source_sha256']:
            raise ValueError('ACTION_REVIEW_SOURCE_CHANGED')
    exposed = {sid for sid, quantity in selected['target_quantities'].items() if quantity > 0}
    expected_action_targets = {inputs['assembled']['metadata'][sid]['ticker']: selected['target_quantities'][sid]
                               for sid in exposed}
    if (len(action_review['rows']) != len(expected_action_targets)
            or {row['ticker']: row['target_quantity'] for row in action_review['rows']} != expected_action_targets):
        raise ValueError('INCOMPLETE_EXPOSED_ACTION_REVIEW')
    source_reviews = {row['security_id']: row for row in inputs['source_reviews']}
    unknown = sorted(sid for sid in exposed if not source_reviews[sid]['provider_action_stream_available'])
    events = [event for event in inputs['provider_event_inventory'] if event['security_id'] in exposed]
    if unknown or events:
        raise ValueError('EXPOSED_ACTION_REQUIRES_EXPLICIT_MAPPING:'+json.dumps(dict(unknown=unknown, events=events)))
    assembled = inputs['assembled']
    if len(assembled['monthly_inputs']) != 1:
        raise ValueError('ONE_MONTH_ONLY_EXPOSURE_PROOF')
    options.output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        target = options.output/name
        pending = target.with_suffix('.pending.json')
        pending.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
        pending.replace(target)
    exposure = dict(status='CONDITIONAL_NO_EXPOSED_PROVIDER_EVENTS', selected_securities=sorted(exposed),
                    initial_shares={}, monthly_decisions=1,
                    justification='One fixed target and exit-only risk cannot introduce a different security. All positive targets have saved provider action streams and no January event.',
                    unexposed_events_retained=inputs['provider_event_inventory'],
                    unexposed_missing_action_streams=inputs['action_stream_missing'],
                    action_review_sha256=hashlib.sha256(options.action_review.read_bytes()).hexdigest(),
                    action_review=action_review,
                    official_exhaustive_action_certification=False)
    save('exposure_review.json', exposure)
    result = run_frontier_capped_next_open(assembled=assembled, ohlc=inputs['ohlc'],
        initial_cash='20000', fee_bps='0', slippage_bps='5',
        risk=MonthlyExitCoreResearchAdapter(assembled['actions']),
        verified_prefix=prefix, max_new_searches=0, dividend_events=[])
    save('book.json', result)
    if result['status'] != 'COMPLETE':
        raise ValueError('BOOK_INCOMPLETE:'+str(result.get('reason')))
    actual = {sid for row in result['daily_ledger'] for sid, quantity in row['shares'].items() if quantity > 0}
    if not actual <= exposed:
        raise ValueError('REALIZED_EXPOSURE_EXCEEDED_REVIEW')
    proof = review(result, assembled, inputs['ohlc'], initial_cash='20000', dividend_events=[],
        expected_fee_bps='0', expected_slippage_bps='5', verify_selections=True, verify_risk_provider=True)
    save('independent_review.json', proof)
    summary = dict(status='ONE_REAL_MONTH_CONDITIONALLY_REPLAYED_AND_REVIEWED',
        start=assembled['session_dates'][0], end=assembled['session_dates'][-1],
        sessions=len(result['daily_ledger']), new_searches=result['new_searches'],
        reused_searches=result['reused_searches'], target_quantities=selected['target_quantities'],
        period_return=float(Fraction(result['total_return'])),
        maximum_close_drawdown=float(Fraction(result['drawdown']['maximum_close_drawdown'])),
        final_equity=proof['final_equity'], risk_provider_certified=proof['risk_provider_certified'],
        selection_proofs_checked=proof['selection_proofs_checked'], execution_sha256=input_sha,
        replay_source_hashes={path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in (
            'scripts/run_january2022_book_probe.py',
            'backtest/historical_dividend_frontier_research.py',
            'backtest/historical_dividend_next_open_book_research.py',
            'backtest/historical_dividend_independent_review.py',
            'backtest/monthly_exit_core_research_adapter.py',
            'core/monthly_peak_exit.py')},
        annualized_return=None, full_bull_bear_validation=False, independent_oos=False,
        limitations=['Historical conditional one-month integration, not a complete bull/bear result.',
                     'No zero-dividend assumption made for unreviewed holdings; those securities were never exposed.',
                     'Provider event absence is conditional evidence, not a complete official negative proof.'])
    save('summary.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
