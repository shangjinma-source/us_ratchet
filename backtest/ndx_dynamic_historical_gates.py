"""Recompute saved historical risk/liquidity gates, not current eligibility."""
import math


def historical_gates(*, result, contract, holding_count):
    if type(holding_count) is not int or holding_count < 1:
        raise ValueError('Explicit holding count required')
    def number(mapping, key):
        value = mapping[key]
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError('Finite nonboolean gate value required: '+key)
        return value
    thresholds = {
        'declared_max_single_weight': number(contract,'max_single_weight'),
        'declared_security_top3_weight_cap': number(contract,'top_weight_cap'),
        'declared_risk_chain_top1_weight_cap': number(contract,'risk_chain_top1_cap'),
        'declared_minimum_effective_n': holding_count*number(contract,'minimum_effective_n_ratio'),
        'minimum_median_dollar_volume_usd': number(contract,'minimum_median_dollar_volume_usd')}
    for key, value in thresholds.items():
        if not math.isclose(number(result,key),value,rel_tol=0,abs_tol=1e-9):
            raise ValueError('Result threshold differs from bound contract: '+key)
    checks = {
        'declared_max_single_passed': number(result,'issuer_top1') <= thresholds['declared_max_single_weight']+1e-9,
        'declared_security_top3_weight_passed': number(result,'weight_top3_max') <= thresholds['declared_security_top3_weight_cap']+1e-9,
        'declared_risk_chain_top1_weight_passed': number(result,'risk_chain_top1') <= thresholds['declared_risk_chain_top1_weight_cap']+1e-9,
        'declared_effective_n_passed': number(result,'effective_n_min') >= thresholds['declared_minimum_effective_n']-1e-9,
        'liquidity_constraint_passed': number(result,'portfolio_min_median_dollar_volume_usd') >= thresholds['minimum_median_dollar_volume_usd']}
    for key, value in checks.items():
        if type(result[key]) is not bool or result[key] != value:
            raise ValueError('Saved gate disagrees with numeric evidence: '+key)
    for key in ('whole_lot_executable_all_windows','declared_constraints_passed'):
        if type(result[key]) is not bool:
            raise ValueError('Saved aggregate gate must be boolean')
    if result['declared_constraints_passed'] != (all(checks.values()) and result['whole_lot_executable_all_windows']):
        raise ValueError('Historical combined gate differs')
    return dict(checks=checks,
        fractional_risk_passed=all(value for key,value in checks.items() if key!='liquidity_constraint_passed'),
        liquidity_passed=checks['liquidity_constraint_passed'],
        historical_minimum_single_weight_verified=False,
        current_whole_lot_execution_verified=False,
        historical_whole_lot_passed=result['whole_lot_executable_all_windows'],
        technology_scope_passed=None, promotion_allowed=False)
