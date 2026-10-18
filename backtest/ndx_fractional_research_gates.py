"""Common fractional gates; never synthesize a whole-lot aggregate gate."""
import math


def fractional_research_gates(*, metrics, contract, holding_count):
    if type(holding_count) is not int or holding_count < 1:
        raise ValueError('Positive explicit holding count required')

    def number(mapping, key):
        value = mapping[key]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Finite nonboolean gate input required: ' + key)
        return value

    maximum = number(contract, 'max_single_weight')
    top = number(contract, 'top_weight_cap')
    chain = number(contract, 'risk_chain_top1_cap')
    effective = number(contract, 'minimum_effective_n_ratio')
    liquidity = number(contract, 'minimum_median_dollar_volume_usd')
    if not all(0 < value <= 1 for value in (maximum, top, chain, effective)) or liquidity <= 0:
        raise ValueError('Invalid fractional gate contract')
    declared = dict(declared_max_single_weight=maximum,
        declared_security_top3_weight_cap=top, declared_risk_chain_top1_weight_cap=chain,
        declared_minimum_effective_n=holding_count * effective,
        minimum_median_dollar_volume_usd=liquidity)
    present = set(declared) & set(metrics)
    if present and present != set(declared):
        raise ValueError('Incomplete stored fractional thresholds')
    for key in present:
        if not math.isclose(number(metrics, key), declared[key], rel_tol=0, abs_tol=1e-9):
            raise ValueError('Stored threshold differs from contract: ' + key)
    values = {key: number(metrics, key) for key in (
        'issuer_top1', 'weight_top3_max', 'risk_chain_top1', 'effective_n_min',
        'portfolio_min_median_dollar_volume_usd')}
    if (any(not 0 < values[key] <= 1 + 1e-9 for key in ('issuer_top1', 'weight_top3_max', 'risk_chain_top1'))
            or not 1 - 1e-9 <= values['effective_n_min'] <= holding_count + 1e-9
            or values['portfolio_min_median_dollar_volume_usd'] <= 0):
        raise ValueError('Invalid observed fractional risk metrics')
    checks = dict(
        declared_max_single_passed=values['issuer_top1'] <= maximum + 1e-9,
        declared_security_top3_weight_passed=values['weight_top3_max'] <= top + 1e-9,
        declared_risk_chain_top1_weight_passed=values['risk_chain_top1'] <= chain + 1e-9,
        declared_effective_n_passed=values['effective_n_min'] >= holding_count * effective - 1e-9,
        liquidity_constraint_passed=values['portfolio_min_median_dollar_volume_usd'] >= liquidity)
    for key, expected in checks.items():
        if type(metrics[key]) is not bool or metrics[key] != expected:
            raise ValueError('Stored fractional gate disagrees: ' + key)
    return dict(checks=checks,
        fractional_risk_passed=all(value for key, value in checks.items() if key != 'liquidity_constraint_passed'),
        liquidity_passed=checks['liquidity_constraint_passed'],
        historical_minimum_single_weight_verified=False,
        current_whole_lot_execution_verified=False,
        technology_scope_passed=None, promotion_allowed=False)
