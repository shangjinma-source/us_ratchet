"""Pure, zero-search feasibility audit; never an execution or economic result."""
from fractions import Fraction as F
from math import prod

from backtest.capped_frontier_rerank_research import rerank, product_hash
from backtest.capped_frontier_independent_review import review_selection
from scripts.audit_capped_training_frontier import capped, evaluate

METHOD = 'SAME_CALL_CAP50_TWELVE_SCENARIO_FLOOR_080_AUDIT_V1'
FLOOR = F(4, 5)


def audit(raw_selection):
    """Accept a saved raw selection; validate its original frontier before gating.

    The incumbent is the existing V27 cap50 reranked winner, not the uncapped
    generator winner. Initial-buy costs and residual cash match its scorer.
    No branch cash path, future returns, or production decision is produced.
    """
    incumbent = rerank(raw_selection)
    review_selection(incumbent, rerank_enabled=True)
    arguments = incumbent['raw_selection']['binding']['search_arguments']
    scenarios = arguments['training_scenarios']
    if len(scenarios) != 12:
        raise ValueError('EXACTLY_TWELVE_SAVED_SCENARIOS_REQUIRED')
    capital = F(arguments['entered_cash'])
    scored = {}
    for record in raw_selection['search_result']['best_by_k'].values():
        quantities = capped(record['quantities'], arguments)
        signature = tuple(sorted(quantities.items()))
        if signature in scored:
            continue
        score = evaluate(quantities, arguments)
        growth = [(score['residual_cash'] + sum((quantity * F(arguments['prices'][sid])
                   * F(scenario[sid]) for sid, quantity in quantities.items()), F(0))) / capital
                  for scenario in scenarios]
        if prod(growth) != score['product']:
            raise ValueError('SCORER_WEALTH_RECONCILIATION')
        scored[signature] = dict(score, growth=growth, passes=min(growth) >= FLOOR)
    original = tuple(sorted((sid, q) for sid, q in incumbent['target_quantities'].items() if q))
    eligible = [signature for signature, score in scored.items() if signature and score['passes']]
    if scored[original]['passes']:
        winner, reason = original, 'INCUMBENT_PASSES_KEEP_UNCHANGED'
        chosen = dict(incumbent['target_quantities'])
    elif eligible:
        # Preserve saved k=0 as a ranking candidate; eligible stocks need not
        # beat its growth product. Cash fallback is not a generated basket.
        rankable = eligible + ([()] if () in scored and scored[()]['passes'] else [])
        winner = max(rankable, key=lambda signature:
                     (scored[signature]['product'], -scored[signature]['notional'], signature))
        chosen = dict(winner)
        reason = 'INCUMBENT_FAILS_SELECT_SAVED_ELIGIBLE' if winner else 'SAVED_CASH_OUTRANKS_ELIGIBLE_STOCKS'
    else:
        winner, chosen, reason = (), {}, 'NO_ELIGIBLE_STOCK_BASKET_CASH'
    if winner not in scored:
        # Explicit fallback cash is allowed even if the saved frontier omitted k=0.
        scored[winner] = dict(evaluate({}, arguments), growth=[F(1)] * 12, passes=True)

    def evidence(signature):
        score = scored[signature]
        return dict(quantities=dict(signature), worst_wealth_multiple=str(min(score['growth'])),
                    scenario_wealth_multiples=[str(value) for value in score['growth']],
                    passes=score['passes'], residual_cash=str(score['residual_cash']),
                    training_mean_log=score['mean_log'], product_sha256=product_hash(score['product']))

    return dict(method=METHOD, threshold='4/5', scenario_count=12,
                target_quantities=chosen, incumbent_quantities=incumbent['target_quantities'],
                changed=winner != original, changed_reason=reason,
                original_raw_selection_sha256=incumbent['rerank_binding']['original_raw_selection_sha256'],
                eligible_stock_baskets=len(eligible), incumbent=evidence(original), selected=evidence(winner),
                candidate_evidence=[evidence(signature) for signature in sorted(scored)],
                new_search_calls=0, execution_simulations=0, economic_superiority_established=False,
                research_only=True, fee_scope='INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION',
                limitation='Saved training terminal wealth floor, not a drawdown guarantee or branch backtest.')
