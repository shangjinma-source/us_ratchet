"""V2 search binding through the unchanged account validation mechanism; no IO."""
from copy import deepcopy
import hashlib
import json

from backtest.return_priority_fresh_cash_quantity_search_v2 import search_fresh_cash_quantities
from data.current_research_capital_decision import decide_quantity_for_account

VERSION = 'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2'
REQUIRED_PINS = (
    'data/current_research_capital_decision_v2.py',
    'data/current_research_capital_decision.py',
    'backtest/return_priority_fresh_cash_quantity_search_v2.py',
    'backtest/affordable_support_seeds.py',
    'backtest/log_concave_integer_search.py',
    'backtest/quantity_training_upper_bound.py',
)


def decide_quantity_v2_for_account(**arguments):
    """Preserve V2 terminal semantics while reusing exact capital validation.

    Pins are caller-authenticated; this pure function does not read source files.
    The legacy core is pinned for the imported validator, never executed here.
    """
    if 'search' in arguments:
        raise ValueError('V2 search cannot be replaced')
    if any(path not in arguments['source_hashes'] for path in REQUIRED_PINS):
        raise ValueError('V2_METHOD_SOURCE_PINS_REQUIRED')
    observed = []

    def compatibility(**kwargs):
        result = search_fresh_cash_quantities(**kwargs)
        if result.get('method_version') != VERSION:
            raise ValueError('V2_METHOD_VERSION_MISMATCH')
        statuses = {
            'INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE': 'INSUFFICIENT_BUDGET_FOR_ALL_K_INITIALIZATION',
            'PER_K_SEARCH_STOPPED_WITH_UNUSED_BUDGET': 'LOCAL_NEIGHBORHOODS_EXHAUSTED',
            'BUDGET_STOPPED': 'BUDGET_STOPPED',
        }
        if result.get('status') not in statuses:
            raise ValueError('UNKNOWN_V2_TERMINAL_STATUS')
        observed.append(deepcopy(result))
        return dict(result, status=statuses[result['status']])

    result = decide_quantity_for_account(**arguments, search=compatibility)
    result['search_result'] = observed[0]  # Never publish the internal status translation.
    result['method'] = VERSION
    result['binding']['schema'] = 'CAPITAL_DECISION_MECHANIC_V2'
    result['binding']['selection_method'] = VERSION
    identifier = hashlib.sha256(json.dumps(result['binding'], sort_keys=True,
        separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    result.update(decision_id=identifier, research_id=identifier[:24])
    result['limitations'].append('V2 bounded search; unused lane budget is not proof of global optimality. No production adoption.')
    return result
