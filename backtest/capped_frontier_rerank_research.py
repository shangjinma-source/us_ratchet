"""Rerank only one original call's saved frontier after the fixed 50% overlay.

No generation, search, IO or execution. Exact product ties keep the incumbent.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json

from scripts.audit_capped_training_frontier import capped, evaluate

METHOD = 'SAME_CALL_SAVED_FRONTIER_CAP50_STRICT_RERANK_V1'


def product_hash(value):
    return sha256(f'{value.numerator:x}/{value.denominator:x}'.encode()).hexdigest()


def rerank(raw_selection):
    raw = deepcopy(raw_selection)
    arguments, result = raw['binding']['search_arguments'], raw['search_result']
    if (raw.get('method') != 'FAIR_K_V2_PLUS_CONTINUOUS32_EXPERIMENT_V1'
            or raw['decision_date'] != arguments['decision_date']
            or result['decision_date'] != arguments['decision_date']
            or Fraction(raw['investable_equity']) != Fraction(arguments['entered_cash'])
            or raw['target_quantities'] != result['selected']['quantities']):
        raise ValueError('ORIGINAL_SAME_CALL_SELECTION_BINDING_REQUIRED')
    base = capped(raw['target_quantities'], arguments)
    base_with_zero = {sid: min(quantity, int(Fraction(arguments['entered_cash']) /
                          (2 * Fraction(arguments['prices'][sid]))))
                      for sid, quantity in raw['target_quantities'].items()}
    base_signature = tuple(sorted(base.items()))
    scored = {}
    source_by_signature = {}
    frontier = result['best_by_k']
    original_present = False
    for key, record in sorted(frontier.items(), key=lambda item: int(item[0])):
        quantities = record['quantities']
        if int(key) != len(quantities):
            raise ValueError('FRONTIER_CARDINALITY_MISMATCH')
        original_present |= quantities == raw['target_quantities']
        quantity = capped(quantities, arguments)
        signature = tuple(sorted(quantity.items()))
        if signature not in scored:
            scored[signature] = evaluate(quantity, arguments)
            source_by_signature[signature] = int(key)
    if not original_present or base_signature not in scored:
        raise ValueError('ORIGINAL_BASKET_MUST_BE_IN_FRONTIER')
    base_score = scored[base_signature]
    improved = [signature for signature, score in scored.items()
                if score['product'] > base_score['product']]
    winner = max(improved, key=lambda signature:
                 (scored[signature]['product'], -scored[signature]['notional'], signature)) if improved else base_signature
    chosen = dict(winner) if improved else base_with_zero
    chosen_score = scored[winner]
    selection = dict(method=METHOD, target_quantities=chosen,
                investable_equity=raw['investable_equity'], raw_selection=raw,
                base_capped_target_quantities=base_with_zero, monthly_cap_fraction='1/2',
                cap_is_post_selection_overlay=True, frontier_reranked_after_cap=True,
                capital_source='CURRENT_BRANCH_ACCOUNT_STATE', research_only=True,
                global_optimum_established=False,
                rerank_audit=dict(strict_improvement=bool(improved),
                    unique_capped_baskets=len(scored), additional_scored_baskets=len(scored),
                    source_cardinality=source_by_signature[winner],
                    base_product_sha256=product_hash(base_score['product']),
                    selected_product_sha256=product_hash(chosen_score['product']),
                    base_training_mean_log=base_score['mean_log'],
                    selected_training_mean_log=chosen_score['mean_log'],
                    selected_residual_cash=str(chosen_score['residual_cash']),
                    candidate_generation_calls=0,
                    original_generation_budget=arguments['max_objective_evaluations'],
                    original_continuous_steps=raw['binding']['continuous_iterations'],
                    tie_rule='STRICT_PRODUCT_IMPROVEMENT_OTHERWISE_KEEP_INCUMBENT; '
                             'AMONG_STRICT_WINNERS_PRODUCT_LOWER_NOTIONAL_LEXICOGRAPHIC_QUANTITIES'))
    def canonical_hash(value):
        return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    binding = dict(schema=METHOD, original_decision_id=raw['decision_id'],
                   original_raw_selection_sha256=canonical_hash(raw),
                   target_quantities=chosen, base_capped_target_quantities=base_with_zero,
                   monthly_cap_fraction='1/2', rerank_audit=selection['rerank_audit'])
    selection.update(rerank_binding=binding, rerank_decision_id=canonical_hash(binding))
    return selection
