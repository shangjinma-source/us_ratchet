"""Unactivated account/router integration using immutable server timing bundles.

Preserves the split journal API, write reconciliation and V30 snapshot binding.
Timing content checks do not authenticate broker evidence or activate production.
"""
from copy import deepcopy
from types import FunctionType

from core.strategy_account_ledger import require
from core.strategy_account_split_v1 import moment
from docs.candidates import strategy_account_split_cost_projection as account_api
from docs.candidates.split_three_clock_coordinates_20261105 import review_timing
from data.strategy_unified_server_preparation_v30 import attach_bound_snapshot as original_attach


class StrategyAccountService(account_api.StrategyAccountService):
    def __init__(self, *, timing_bundles, **arguments):
        bundles = deepcopy(timing_bundles)
        provider = arguments.get('valuation_provider')
        super().__init__(**arguments)
        if provider is not None:
            def checked_provider(state):
                marks = provider(deepcopy(state))
                now = self.clock()
                actions = {row['payload']['security_id']: row['payload']
                           for row in state['events']
                           if row['payload']['kind'] == 'SPLIT_CONFIRMED'}
                for sid, action in actions.items():
                    if not state['shares'].get(sid):
                        continue
                    require(action['action_id'] in bundles, 'VALUATION_SPLIT_TIMING_REQUIRED')
                    clocks = review_timing(action=action, timing=bundles[action['action_id']], now=now.isoformat())
                    require(sid in marks and marks[sid].get('unit_id') == action['new_unit_id']
                            and moment(marks[sid]['observed_at']) >= moment(clocks['quote_unit_effective_at']),
                            'VALUATION_PRE_QUOTE_UNIT')
                return marks
            self.valuation_provider = checked_provider


def private_binding(function, **replacements):
    namespace = dict(function.__globals__, **replacements)
    bound = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = function.__kwdefaults__
    return bound


def create_router(*, timing_bundles, **arguments):
    bundles = deepcopy(timing_bundles)
    def service_factory(**values):
        return StrategyAccountService(timing_bundles=bundles, **values)
    return private_binding(account_api.create_router,
                           StrategyAccountService=service_factory)(**arguments)


def attach_bound_snapshot(*, prepared, validate_sources):
    # Exact new service type, same route identity and database-path checks.
    # The full builder must create news with this same observed object first.
    return private_binding(original_attach, StrategyAccountService=StrategyAccountService)(
        prepared=prepared, validate_sources=validate_sources)
