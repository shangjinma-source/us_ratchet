"""One create-only conditional window from existing frozen plans; no new search.

Preparation/import performs no IO or book calls. Root must review before the
explicit --execute-once invocation. An existing output directory forbids retry.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from backtest.return_priority_paper_continuous_book_research import simulate_paper_book


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = 'tmp/post_selection_conditional_20261014_v1'
CONTRACT = 'research_contracts/post_selection_conditional_20261014_v1.json'
RESULT = 'tmp/joint_family_experiment_20261014_v1/result.json'
FROZEN = 'tmp/joint_family_experiment_20261014_v1/frozen_candidate_snapshots.json'
PANEL = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
LEDGER = 'backtest/return_priority_paper_continuous_book_research.py'
SOURCE_PINS = {
    CONTRACT: '172716c4e3d4a11d833d902e9c42f94bb65a7394ec3605280532c420be796419',
    RESULT: 'd59604d82d4398d9165373f70d6010c87150a387358b04695b4bd2f4a9a872ea',
    FROZEN: '25f18d1f12f8f6e2e1db3bbc0e78cb781c04328f963e6cec21425a2afe46ef19',
    PANEL: '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822',
    LEDGER: 'a60eb8602d42ec35b973c0d54097cf47aa186c6f8c56a80b08b3f39ced2184e3',
}
SCOPE = 'RETROSPECTIVE_POST_SELECTION_WINDOW_NOT_INDEPENDENT_OOS'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_book(book, calendar):
    """Exact net return and signed drawdown including the initial 20000 base."""
    complete = book['status'] == 'COMPLETE_CONDITIONAL_PAPER_BOOK'
    peak, worst = Fraction(20000), Fraction(0)
    for row in book['daily_rows']:
        require(Fraction(row['external_cash_flow']) == 0, 'No external cash flows')
        equity = Fraction(row['close_equity'])
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
    committed = [row for row in book['executions'] if row['status'] == 'COMMITTED_SELLS_THEN_BUYS']
    fees = sum((Fraction(row['buy_fee']) + Fraction(row['sell_fee']) for row in committed), Fraction(0))
    if complete:
        require([row['session'] for row in book['daily_rows']] == calendar, 'Complete exact window required')
    return dict(status=book['status'], reason=book['reason'], full_window_complete=complete,
                final_close_equity=book['daily_rows'][-1]['close_equity'] if complete else None,
                net_return=str(Fraction(book['daily_rows'][-1]['close_equity']) / 20000 - 1) if complete else None,
                max_drawdown=str(worst) if complete else None, realized_fees=str(fees),
                executed_dates=[row['execution_date'] for row in committed],
                execution_statuses=[row['status'] for row in book['executions']],
                last_observed_session=book['daily_rows'][-1]['session'] if book['daily_rows'] else None,
                annualization_performed=False)


def execute_once():
    output = ROOT / OUTPUT
    require(not output.exists(), 'Create-only output already exists; no rerun')
    decoded = {}
    for relative, expected in SOURCE_PINS.items():
        raw = (ROOT / relative).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, f'Source hash mismatch: {relative}')
        if relative.endswith('.json'):
            decoded[relative] = json.loads(raw)
    contract, historical, panel = decoded[CONTRACT], decoded[RESULT], decoded[PANEL]
    require(historical['frozen_candidates_sha256'] == SOURCE_PINS[FROZEN], 'Original result/frozen binding')
    snapshot = decoded[FROZEN][-1]
    require(snapshot['decision_date'] == contract['decision_date'] == '2026-09-21', 'Exact final frozen decision')
    require(Fraction(snapshot['fee_bps']) == 10 and Fraction(snapshot['minimum_cash_buffer']) == 100, 'Historical fee/buffer unchanged')
    rules = [row['rule'] for row in historical['rankings']]
    require(len(rules) == len(set(rules)) == 46 and rules.count('ALL_CASH_REFERENCE') == 1, 'Original 46 unique rules')
    records = {row['method_rule_id']: row for row in snapshot['records']}
    require(set(rules) <= set(records), 'Every original rule must have final frozen record')
    calendar = [day for day in panel['calendar'] if contract['decision_date'] <= day <= contract['last_close']]
    require(len(calendar) == 16 and calendar[0] == '2026-09-21' and calendar[1] == '2026-09-22'
            and calendar[-1] == '2026-10-12', 'Frozen decision/next Open/end window')
    require(panel['fields'] == ['open', 'high', 'low', 'close', 'volume'], 'Actual OHLCV channel ordering')
    stock_channels = {row['ticker']: row for row in panel['stocks']}
    control_channels = {row['ticker']: row for row in panel['controls']}
    require({'QQQ', 'SPY'} <= set(control_channels), 'Explicit saved ETF controls required')
    indices = [panel['calendar'].index(day) for day in calendar]
    risks = {key: float(Fraction(value)) for key, value in snapshot['risk_parameters'].items()}
    runner_sha = fingerprint(Path(__file__))
    output.mkdir(exist_ok=False)

    def save(name, value):
        with (output / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)

    # Persist the exact finite scope before any sizing, outcome calculation or book call.
    save('registration.json', dict(schema='POST_SELECTION_REGISTRATION_V1', contract=contract,
                                  source_pins=SOURCE_PINS, runner_sha256=runner_sha, rules_original_rank_order=rules,
                                  frozen_target_weights={rule: records[rule]['target_weights'] for rule in rules},
                                  calendar=calendar, original_blocks_replayed=0, maximum_book_calls=47,
                                  scope=SCOPE, qualification_certified=False, execution_authorized=False))
    books, summaries, references, calls = {}, [], [], 0

    def evaluate(label, weights, metadata, channels, stock_gate):
        nonlocal calls
        require(weights and set(weights) == set(metadata), 'Complete frozen support and existing metadata')
        require(all(Fraction(weight) > 0 for weight in weights.values()) and
                sum((Fraction(weight) for weight in weights.values()), Fraction(0)) <= 1, 'Positive frozen exposure <=1')
        opened, closed, missing = {day: {} for day in calendar}, {day: {} for day in calendar}, []
        for security, item in metadata.items():
            ticker = item['ticker']
            channel = channels.get(ticker)
            if channel is None or len(channel['values']) != len(panel['calendar']):
                missing.append(dict(ticker=ticker, reason='MISSING_OR_UNALIGNED_CHANNEL'))
                continue
            for day, index in zip(calendar, indices):
                values = channel['values'][index]
                valid = (type(values) is list and len(values) == 5 and
                         all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in values[:4]))
                if valid:
                    op, hi, lo, cl = values[:4]
                    valid = lo <= min(op, cl) <= max(op, cl) <= hi
                if not valid:
                    missing.append(dict(ticker=ticker, session=day, reason='MISSING_OR_INVALID_OHLC'))
                    continue
                opened[day][security], closed[day][security] = op, cl
        if missing:
            return dict(status='BLOCKED_SOURCE_PREFLIGHT', reason='REQUIRED_OHLC_INCOMPLETE', missing=missing,
                        full_window_complete=False, net_return=None, max_drawdown=None,
                        realized_fees='0', executed_dates=[], book_called=False)
        capacity = Fraction(20000) - 100 - 2 * Fraction(10, 10000) * 20000
        quantities = {security: int(capacity * Fraction(weight) // Fraction(str(opened[calendar[1]][security])))
                      for security, weight in weights.items()}
        if any(quantity == 0 for quantity in quantities.values()):
            return dict(status='BLOCKED_ZERO_NEXT_OPEN_MEMBER', reason='ORIGINAL_SUPPORT_CANNOT_BE_PRESERVED',
                        next_open_quantities=quantities, full_window_complete=False, net_return=None,
                        max_drawdown=None, realized_fees='0', executed_dates=[], book_called=False)
        require(calls < 47 and label not in books, 'At most one book per distinct rule/reference, total<=47')
        calls += 1
        book = simulate_paper_book(calendar=calendar, open_prices=opened, close_prices=closed,
                                   metadata=metadata, initial_shares={}, initial_cash=20000, fee_bps=10,
                                   minimum_cash_buffer=100,
                                   decisions=[dict(id=label, decision_date=calendar[0], target_weights=weights)],
                                   cash_events=[], risk_parameters=risks, enforce_initial_target_risk=stock_gate,
                                   declared_price_basis='CONDITIONAL_PROVIDER_OHLC_UNAUTHENTICATED_POST_SELECTION')
        books[label] = book
        summary = summarize_book(book, calendar)
        summary.update(book_called=True, next_open_quantities=quantities, required_ohlc_complete=True,
                       initial_target_stock_risk_gate=stock_gate)
        return summary

    for rank, rule in enumerate(rules, 1):
        candidate = records[rule]
        if rule == 'ALL_CASH_REFERENCE':
            outcome = dict(status='COMPLETE_ALL_CASH_REFERENCE', full_window_complete=True,
                           final_close_equity='20000', net_return='0', max_drawdown='0', realized_fees='0',
                           book_called=False, executed_dates=[], execution_statuses=[], annualization_performed=False)
        else:
            metadata = {security: {key: candidate['metadata'][security][key] for key in ('ticker', 'issuer_id', 'risk_chain')}
                        for security in candidate['target_weights']}
            outcome = evaluate(rule, candidate['target_weights'], metadata, stock_channels, True)
        summaries.append(dict(rule=rule, original_rank=rank, frozen_status=candidate['status'],
                              frozen_target_weights=candidate['target_weights'], **outcome))
    for ticker in contract['reference_tickers']:
        # These labels are explicit reference identifiers, never inferred CIK/SID.
        security = f'REFERENCE_ONLY:{ticker}'
        metadata = {security: dict(ticker=ticker, issuer_id=f'REFERENCE_LABEL:{ticker}', risk_chain='REFERENCE_ETF')}
        outcome = evaluate(f'REFERENCE:{ticker}', {security: '1'}, metadata, control_channels, False)
        references.append(dict(ticker=ticker, role='REFERENCE_ONLY_NOT_IN_46_RULE_RANKING',
                               metadata_role=contract['reference_metadata_role'], **outcome))
    for relative, expected in SOURCE_PINS.items():
        require(fingerprint(ROOT / relative) == expected, f'Source changed during run: {relative}')
    require(fingerprint(Path(__file__)) == runner_sha, 'Runner changed during run')
    save('books.json', books)
    save('result.json', dict(schema='POST_SELECTION_CONDITIONAL_RESULT_V1', scope=SCOPE,
                             status='COMPLETE_FINITE_ATTEMPT_WITH_BLOCKED_OUTCOMES_RETAINED',
                             decision_date=calendar[0], execution_open_date=calendar[1], final_close_date=calendar[-1],
                             observed_rows=len(calendar), observed_intervals=len(calendar)-1,
                             summaries_original_rank_order=summaries, market_references=references,
                             original_top_rule=rules[0], new_winner_selected=False, ranking_changes_applied=False,
                             source_pins=SOURCE_PINS, runner_sha256=runner_sha, books_sha256=fingerprint(output/'books.json'),
                             book_calls=calls, original_four_block_replays=0, candidate_search_calls=0,
                             fee_bps='10', current_zero_commission_comparison=False,
                             qualification_scope=contract['qualification'], qualification_certified=False,
                             point_in_time_certified=False, independent_oos=False,
                             dividend_total_return_certified=False, annualization_performed=False,
                             account_modified=False, orders_created=False))
    print(json.dumps(dict(output=OUTPUT, book_calls=calls, rule_count=len(summaries), reference_count=len(references))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-once', action='store_true', help='Run only after Root review; output must not exist')
    arguments = parser.parse_args()
    require(arguments.execute_once, 'Preparation only; explicit reviewed --execute-once required')
    execute_once()


if __name__ == '__main__':
    main()
