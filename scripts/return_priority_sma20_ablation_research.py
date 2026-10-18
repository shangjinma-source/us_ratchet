"""One fixed SMA20 ablation of sealed portfolios; no search or parameter sweep."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import types


ROOT = Path(__file__).resolve().parents[1]
BASE = 'tmp/quantity_temporal_conditional_20261014_v1'
OUTPUT = ROOT / 'tmp/sma20_ablation_20261014_v1'
PANEL = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
LEDGER = 'backtest/return_priority_paper_continuous_book_research.py'
DECISIONS = ['2026-05-20', '2026-06-22', '2026-07-22', '2026-08-20', '2026-09-21']
ENDS = DECISIONS[1:]+['2026-10-12']
FIXED_PINS = {PANEL: '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822',
              LEDGER: 'a60eb8602d42ec35b973c0d54097cf47aa186c6f8c56a80b08b3f39ced2184e3'}
PROTECTED = ['data/state.json', 'data/broker_positions.json', 'config/config.yaml',
             'api/server.py', 'web/index.html', 'web/selected_stock_charts.js',
             'data/current_cash_portfolio_research.py']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    with path.open('xb') as stream:
        stream.write(raw)
    return sha(raw)


def guards():
    return {path: sha((ROOT/path).read_bytes()) for path in PROTECTED}


def build_sma20_plans(*, calendar, close_by_security, frozen_weights, decision_date, end_date):
    """Close>SMA20 including today => original weight; otherwise cash.

Only changed ON sets trigger next-Open plans. Equality is OFF. No normalizing
or daily rebalancing. The final Close signal is recorded but never submitted.
"""
    require(calendar == sorted(set(calendar)), 'Unique sorted observation calendar required')
    first, last = calendar.index(decision_date), calendar.index(end_date)
    require(first >= 19 and last > first, 'Complete 20-close warmup and outcome required')
    require(set(frozen_weights) <= set(close_by_security), 'Missing security close channel')
    weights = {sid: Fraction(str(value)) for sid, value in frozen_weights.items()}
    require(all(value > 0 for value in weights.values()) and sum(weights.values()) <= 1, 'Positive original weights with sum<=1')
    signals, plans, previous = [], [], None
    for index in range(first, last+1):
        statistics, active = {}, []
        for sid in sorted(weights):
            # Do not scan an entire channel or validate future values.
            raw = close_by_security[sid][index-19:index+1]
            require(len(raw)==20 and all(type(value) in (int, float, str) for value in raw), 'Missing 20-close history')
            try:
                values = [Fraction(str(value)) for value in raw]
            except (ValueError, ZeroDivisionError) as error:
                raise ValueError('Invalid observed close') from error
            require(all(value > 0 for value in values), 'Positive observed close required')
            average = sum(values)/20
            on = values[-1] > average
            statistics[sid] = dict(close=str(values[-1]), sma20=str(average), on=on)
            if on:
                active.append(sid)
        state = tuple(active)
        subset = {sid: str(weights[sid]) for sid in active}
        changed = previous is None or state != previous
        submitted = changed and index < last
        if submitted:
            plan = dict(id='sma20:'+calendar[index], decision_date=calendar[index])
            plan.update({'target_weights': subset} if subset else {'target_shares': {}})
            plans.append(plan)
        signals.append(dict(session=calendar[index], securities=statistics, active_security_ids=active,
                            target_weight_subset=subset, target_cash_fraction=str(1-sum(weights[sid] for sid in active)),
                            changed=changed, plan_submitted=submitted, terminal_signal_only=index==last))
        previous = state
    return dict(signals=signals, plans=plans, parameter_authority='ROOT_RESEARCH_FIXED_20_NOT_USER_RISK_PREFERENCE',
                no_parameter_search=True, signal_rule='CLOSE_STRICTLY_ABOVE_INCLUSIVE_SMA20',
                execution='NEXT_OBSERVED_OPEN', subset_renormalized=False,
                no_daily_rebalance=True)


def book_metrics(book):
    require(book['status']=='COMPLETE_CONDITIONAL_PAPER_BOOK', 'Only complete books have comparable returns')
    values = [Fraction(20000)]+[Fraction(row['close_equity']) for row in book['daily_rows']]
    peak, drawdown = values[0], Fraction(0)
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1-value/peak)
    executions = [row for row in book['executions'] if row['status']=='COMMITTED_SELLS_THEN_BUYS']
    return dict(net_return=str(values[-1]/20000-1), drawdown=str(drawdown), final_equity=str(values[-1]),
                fully_cash_close_days=sum(not row['shares'] for row in book['daily_rows']),
                close_days=len(book['daily_rows']),
                trade_sessions=sum(bool(row['buys'] or row['sells']) for row in executions),
                individual_buy_sell_legs=sum(len(row['buys'])+len(row['sells']) for row in executions),
                executed_plan_count=len(executions))


def prepare():
    require(not OUTPUT.exists(), 'Create-only output already exists')
    paths = list(FIXED_PINS)
    for decision in DECISIONS:
        paths += [f'{BASE}/{decision}/{name}.json' for name in ('inputs', 'frozen_execution_target', 'strategy_book')]
    pins = {path: sha((ROOT/path).read_bytes()) for path in paths}
    require(all(pins[path]==digest for path, digest in FIXED_PINS.items()), 'Pinned panel/ledger differs')
    registration = dict(schema='FIXED_SMA20_ABLATION_REGISTRATION_V1', source_pins=pins,
                        runner_sha256=sha(Path(__file__).read_bytes()), decisions=DECISIONS, ends=ENDS,
                        maximum_book_calls=5, search_calls=0, parameter_sweep=False,
                        entered_cash=20000, fee_bps=0, minimum_cash_buffer=0,
                        sma_sessions=20, parameter_authority='ROOT_RESEARCH_NOT_USER_PREFERENCE',
                        independent_oos=False, current_metadata_retrospective_not_pit=True,
                        price_returns_not_total_returns=True, dividends_included=False,
                        other_charges_included=False, protected_before=guards(),
                        source_baseline_frozen=True, winner_promotion=False, service_changed=False)
    OUTPUT.mkdir()
    digest = save(OUTPUT/'registration.json', registration)
    print(json.dumps(dict(registration=str(OUTPUT/'registration.json'), sha256=digest)))


def run(registration_sha):
    raw = (OUTPUT/'registration.json').read_bytes()
    require(sha(raw)==registration_sha, 'Registration SHA mismatch')
    registration = json.loads(raw)
    require(registration['runner_sha256']==sha(Path(__file__).read_bytes()), 'Runner changed')
    require({path.name for path in OUTPUT.iterdir()}=={'registration.json'}, 'Already started: inspect artifacts, do not blindly rerun')
    require(guards()==registration['protected_before'], 'Protected files changed')
    sources = {}
    for path, digest in registration['source_pins'].items():
        raw = (ROOT/path).read_bytes()
        require(sha(raw)==digest, 'Input source changed: '+path)
        sources[path] = raw
    require(all(registration['source_pins'].get(path)==digest for path, digest in FIXED_PINS.items()), 'Fixed source pins changed')
    ledger = types.ModuleType('pinned_sma20_ledger')
    exec(compile(sources[LEDGER], LEDGER, 'exec'), ledger.__dict__)
    panel = json.loads(sources[PANEL])
    calendar = panel['calendar']
    channels = {row['ticker']: row['values'] for row in panel['stocks']}
    summary = []
    save(OUTPUT/'started.json', dict(registration_sha256=registration_sha, maximum_book_calls=5))
    try:
        for decision, end in zip(DECISIONS, ENDS):
            directory = OUTPUT/decision
            directory.mkdir()
            prefix = f'{BASE}/{decision}/'
            inputs = json.loads(sources[prefix+'inputs.json'])
            frozen = json.loads(sources[prefix+'frozen_execution_target.json'])
            baseline = json.loads(sources[prefix+'strategy_book.json'])
            weights = frozen['target_weights']
            metadata = {sid: inputs['ledger_metadata'][sid] for sid in weights}
            require(metadata, 'This registered baseline requires a stock support')
            first, last = calendar.index(decision), calendar.index(end)
            # Copy only observations available through this outcome endpoint.
            closes = {sid: [values[3] for values in channels[row['ticker']][:last+1]] for sid, row in metadata.items()}
            plan = build_sma20_plans(calendar=calendar, close_by_security=closes, frozen_weights=weights,
                                     decision_date=decision, end_date=end)
            save(directory/'signals_and_plans.json', plan)
            dates = calendar[first:last+1]
            opens = {day: {sid: channels[row['ticker']][first+i][0] for sid, row in metadata.items()} for i, day in enumerate(dates)}
            marks = {day: {sid: closes[sid][first+i] for sid in metadata} for i, day in enumerate(dates)}
            require([row['session'] for row in baseline['daily_rows']]==dates, 'Baseline/outcome windows differ')
            save(directory/'book_intent.json', dict(maximum_calls=1, decision=decision, end=end))
            book = ledger.simulate_paper_book(calendar=dates, open_prices=opens, close_prices=marks,
                metadata=metadata, initial_shares={}, initial_cash=20000, fee_bps=0, minimum_cash_buffer=0,
                decisions=plan['plans'], cash_events=[], enforce_initial_target_risk=False,
                risk_parameters=dict(min_single_weight=0, max_single_weight=1, top_three_cap=1, min_neff_ratio=0, chain_cap=1),
                declared_price_basis='CONDITIONAL_PROVIDER_PRICE_RETURN_FIXED_SMA20_ABLATION')
            save(directory/'book.json', book)
            result = dict(decision=decision, end=end, status=book['status'], reason=book['reason'],
                          baseline=book_metrics(baseline), ablation=None, differences=None)
            if book['status']=='COMPLETE_CONDITIONAL_PAPER_BOOK':
                require(all(row['daily_risk']['all_passed'] is True or row['daily_risk']['status']=='NO_STOCK_HOLDINGS'
                            for row in book['daily_rows']), 'Uncapped-domain risk or issuer check failed')
                result['ablation'] = book_metrics(book)
                result['differences'] = {key: str(Fraction(result['ablation'][key])-Fraction(result['baseline'][key]))
                                         for key in ('net_return', 'drawdown', 'fully_cash_close_days', 'trade_sessions')}
            save(directory/'outcome.json', result)
            summary.append(result)
        save(OUTPUT/'result.json', dict(status='COMPLETE_FIXED_SMA20_ABLATION_EVALUATION', windows=summary,
             ledger_calls=len(summary), search_calls=0, no_winner_selected=True, parameter_search=False,
             continuous_nav=False, cagr=None, independent_oos=False, price_returns_not_total_returns=True,
             source_pins=registration['source_pins'], current_service_changed=False))
    except Exception as error:
        save(OUTPUT/'failure.json', dict(type=type(error).__name__, message=str(error), automatic_retry_allowed=False))
        raise
    finally:
        after = guards()
        save(OUTPUT/'protected_after.json', dict(hashes=after, unchanged=after==registration['protected_before']))
        require(after==registration['protected_before'], 'Protected files changed during evaluation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--registration-sha')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        require(args.registration_sha is not None, 'Explicit reviewed registration SHA required')
        run(args.registration_sha)
