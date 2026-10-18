"""Pure bounded fresh-cash integer search; training price scenarios, no forecast.

No IO or prior holdings. Concentration is unrestricted, including one issuer.
All affordable cardinalities receive an actual evaluated initialization before
local search. Exhausted neighborhoods do not establish a global optimum.
"""
from datetime import date
from fractions import Fraction
import hashlib
import math


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    _require(type(value) in (str, int, float, Fraction), 'Finite nonboolean number required')
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError('Finite rational number required') from error


def search_fresh_cash_quantities(*, prices, metadata, entered_cash, fee_bps,
                                 minimum_cash_buffer, training_scenarios,
                                 scenario_dates, decision_date,
                                 max_objective_evaluations, fixed_seed):
    """Maximize equal-scenario mean log terminal wealth, including residual cash.

Prices and gross relatives must share a caller-validated basis. Fees are charged
on the initial purchase only; no liquidation, dividends or reinvestment implied.
The score is a training scenario score, never a future-return estimate.
"""
    _require(type(prices) is dict and prices and type(metadata) is dict
             and set(prices) == set(metadata), 'Complete common SID domain required')
    _require(all(type(sid) is str and sid for sid in prices), 'Explicit SIDs required')
    marks = {sid: _number(value) for sid, value in prices.items()}
    _require(all(value > 0 for value in marks.values()), 'Positive prices required')
    _require(type(fixed_seed) is str and fixed_seed, 'Explicit deterministic seed required')
    _require(type(max_objective_evaluations) is int and max_objective_evaluations > 0,
             'Positive objective evaluation limit required')
    _require(type(decision_date) is str and date.fromisoformat(decision_date).isoformat() == decision_date,
             'Canonical decision date required')
    _require(type(training_scenarios) is list and training_scenarios
             and type(scenario_dates) is list and len(scenario_dates) == len(training_scenarios),
             'Nonempty common scenario dates required')
    _require(all(type(day) is str and date.fromisoformat(day).isoformat() == day
                 and day <= decision_date for day in scenario_dates)
             and scenario_dates == sorted(set(scenario_dates)), 'Unique mature ordered scenario dates required')
    scenarios = []
    for row in training_scenarios:
        _require(type(row) is dict and set(row) == set(marks), 'Missing scenarios cannot be filled')
        values = {sid: _number(value) for sid, value in row.items()}
        _require(all(value > 0 for value in values.values()), 'Positive gross relatives required')
        scenarios.append(values)
    groups = {}
    for sid, row in metadata.items():
        _require(type(row) is dict and all(type(row.get(key)) is str and row[key]
                                         for key in ('ticker', 'issuer_id')), 'Explicit ticker/issuer required')
        groups.setdefault(row['issuer_id'], []).append(sid)
    _require(len({row['ticker'] for row in metadata.values()}) == len(metadata), 'Unique tickers required')
    cash, fee, buffer = _number(entered_cash), _number(fee_bps) / 10000, _number(minimum_cash_buffer)
    _require(cash > 0 and 0 <= fee < 1 and buffer >= 0, 'Invalid cash, fee or buffer')
    units_cost = {sid: value * (1 + fee) for sid, value in marks.items()}
    order = sorted(marks, key=lambda sid: (hashlib.sha256((fixed_seed+'|'+sid).encode()).hexdigest(), sid))
    cheapest = sorted((min(sids, key=lambda sid: (marks[sid], sid)) for sids in groups.values()),
                      key=lambda sid: (marks[sid], sid))
    per_k, seeds = [], {}
    for k in range(1, len(groups)+1):
        lower = sum((units_cost[sid] for sid in cheapest[:k]), Fraction(0))
        affordable = lower <= cash-buffer
        per_k.append(dict(k=k, minimum_purchase_cost=str(lower),
                          structural_status='AFFORDABLE' if affordable else 'UNAFFORDABLE_CHEAPEST_ISSUER_BOUND',
                          initialized=False, visited_states=0, visited_supports=0,
                          return_rank_seed_status='NOT_ATTEMPTED',
                          search_scope='NOT_SEARCHED' if affordable else 'PROVEN_UNAFFORDABLE',
                          global_optimum_established=False))
        if affordable:
            seeds[k] = {sid: 1 for sid in cheapest[:k]}
    base = dict(research_only=True, objective='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH',
                forecast_return=None, decision_date=decision_date, scenario_dates=list(scenario_dates),
                entered_cash=str(cash), fee_bps=str(fee*10000), minimum_cash_buffer=str(buffer),
                max_objective_evaluations=max_objective_evaluations, per_k=per_k,
                global_optimum_established=False, historical_performance_inherited=False,
                source_authenticated=False, initial_positions={}, orders_created=False,
                remaining_domain='ALL_UNVISITED_INTEGER_STATES_UNKNOWN',
                fee_scope='INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION')
    if max_objective_evaluations < len(seeds)+1:
        return dict(base, status='INSUFFICIENT_BUDGET_FOR_ALL_K_INITIALIZATION',
                    objective_evaluations=0, selected=None)
    visited, supports, best_by_k, best = set(), {k: set() for k in seeds}, {}, None

    def key(q):
        return tuple(sorted((sid, value) for sid, value in q.items() if value))

    def evaluate(q):
        nonlocal best
        q = dict(key(q))
        signature = key(q)
        if signature in visited:
            return None
        if any(type(value) is not int or value <= 0 for value in q.values()):
            return None
        if len({metadata[sid]['issuer_id'] for sid in q}) != len(q):
            return None
        notional = sum((marks[sid]*value for sid, value in q.items()), Fraction(0))
        residual = cash-notional*(1+fee)
        # A below-buffer input may retain all cash, but cannot open a stock basket.
        if q and residual < buffer:
            return None
        if residual < 0:
            return None
        growth = [(residual+sum((marks[sid]*value*scenario[sid] for sid, value in q.items()), Fraction(0)))/cash
                  for scenario in scenarios]
        product = math.prod(growth)
        score = sum(math.log(value.numerator)-math.log(value.denominator) for value in growth)/len(growth)
        record = dict(quantities=q, actual_k=len(q), notional=str(notional), fees=str(notional*fee),
                      residual_cash=str(residual), training_mean_net_log_wealth=score,
                      training_gross_growth_product=(str(product) if max(product.numerator.bit_length(), product.denominator.bit_length()) <= 4096 else None),
                      exact_product_comparison=True,
                      large_exact_product_serialization_omitted=max(product.numerator.bit_length(), product.denominator.bit_length()) > 4096,
                      actual_weights={sid: str(marks[sid]*value/cash) for sid, value in q.items()},
                      cash_fraction=str(residual/cash), issuer_unique=True,
                      budget_conservation_exact=notional+notional*fee+residual == cash)
        ranked = (product, -notional, signature)
        visited.add(signature)
        k = len(q)
        if k:
            row = per_k[k-1]
            row['visited_states'] += 1
            supports[k].add(tuple(q))
            row['visited_supports'] = len(supports[k])
            row['search_scope'] = 'VISITED_STATES_ONLY'
        if k not in best_by_k or ranked > best_by_k[k][0]:
            best_by_k[k] = (ranked, record)
        if best is None or ranked > best[0]:
            best = (ranked, record)
        return record

    def neighbors(q):
        spent = sum((units_cost[sid]*value for sid, value in q.items()), Fraction(0))
        spare = cash-buffer-spent
        for sid in order:
            current = q.get(sid, 0)
            for delta in (1, int(spare//units_cost[sid])):
                if delta > 0:
                    changed = dict(q); changed[sid] = current+delta
                    yield changed
            if current:
                for left in (current-1, 0):
                    changed = dict(q); changed[sid] = left
                    yield changed
        # Partial transfers and full substitutions include same-issuer class swaps.
        for sold in order:
            if sold not in q:
                continue
            for amount in sorted({1, q[sold]}):
                released = spare+amount*units_cost[sold]
                for bought in order:
                    if bought == sold:
                        continue
                    for quantity in sorted({1, int(released//units_cost[bought])}):
                        if quantity > 0:
                            changed = dict(q); changed[sold] -= amount
                            changed[bought] = changed.get(bought, 0)+quantity
                            yield changed

    evaluate({})
    for k, q in seeds.items():
        evaluate(q)
        per_k[k-1]['initialized'] = True
    # A second starting support competes using all mature input scenarios. This
    # ordering is a training heuristic, not a forecast or a hard universe filter.
    asset_growth = {sid: math.prod(scenario[sid] for scenario in scenarios) for sid in marks}
    ranked_members = sorted((max(sids, key=lambda sid: (asset_growth[sid], sid)) for sids in groups.values()),
                            key=lambda sid: (-asset_growth[sid], sid))
    for k in seeds:
        row = per_k[k-1]
        if len(visited) >= max_objective_evaluations:
            row['return_rank_seed_status'] = 'NOT_SEARCHED_BUDGET'
            continue
        support = ranked_members[:k]
        cost = sum((units_cost[sid] for sid in support), Fraction(0))
        if cost > cash-buffer:
            row['return_rank_seed_status'] = 'UNAFFORDABLE_SUPPORT'
            continue
        allocation = (cash-buffer-cost)/k
        q = {sid: 1+int(allocation//units_cost[sid]) for sid in support}
        row['return_rank_seed_status'] = 'EVALUATED' if evaluate(q) is not None else 'ALREADY_VISITED'
    cursors, anchors = {}, {}
    for k in seeds:
        anchors[k] = key(best_by_k[k][1]['quantities'])
        cursors[k] = iter(neighbors(dict(anchors[k])))
    while len(visited) < max_objective_evaluations:
        # Cross-cardinality moves can improve a previously exhausted lane.
        for k in seeds:
            anchor = key(best_by_k[k][1]['quantities'])
            if anchors[k] != anchor:
                anchors[k] = anchor
                cursors[k] = iter(neighbors(dict(anchor)))
        if not cursors:
            break
        for k in list(cursors):
            anchor = key(best_by_k[k][1]['quantities'])
            if anchors[k] != anchor:
                anchors[k] = anchor
                cursors[k] = iter(neighbors(dict(anchor)))
            for proposal in cursors[k]:
                if evaluate(proposal) is not None:
                    break
            else:
                del cursors[k]
            if len(visited) >= max_objective_evaluations:
                break
    return dict(base, status='BUDGET_STOPPED' if len(visited) >= max_objective_evaluations else 'LOCAL_NEIGHBORHOODS_EXHAUSTED',
                objective_evaluations=len(visited), selected=best[1],
                best_by_k={str(k): value[1] for k, value in sorted(best_by_k.items())},
                tie_break='EXACT_GROWTH_PRODUCT_THEN_LOWER_NOTIONAL_THEN_LEXICOGRAPHIC_QUANTITIES',
                all_affordable_k_initialized=True)
