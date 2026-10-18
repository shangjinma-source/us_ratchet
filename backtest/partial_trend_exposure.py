"""Single predeclared research candidate: SMA20 off-state half monthly ceiling."""
from copy import deepcopy
from backtest.current_quantity_v2_risk_overlays import sma20_target


def partial_sma20_target(**kwargs):
    # Delegate all exact history, completed-clock and common-unit validation.
    result = sma20_target(**kwargs)
    result = deepcopy(result)
    for sid, diagnostic in result['diagnostics'].items():
        ceiling = diagnostic['monthly_ceiling']
        result['target_quantities'][sid] = ceiling if diagnostic['on'] else ceiling // 2
        diagnostic['off_exposure_fraction'] = '1/2'
        diagnostic['rounding'] = 'FLOOR_MONTHLY_TARGET_NOT_CURRENT_HOLDINGS'
    result['policy'] = 'SMA20_HALF_OFF_RESEARCH'
    result['parameter_authority'] = 'RESEARCH_HYPOTHESIS_NOT_USER_HARD_LIMIT_OR_PRODUCTION_POLICY'
    return result
