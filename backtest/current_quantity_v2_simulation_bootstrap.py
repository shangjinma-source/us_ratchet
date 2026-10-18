"""Explicit pure-cash isolated simulation bootstrap, without fetch or scheduler."""
from copy import deepcopy
from datetime import datetime, timezone

from data.current_quantity_v2_difference_plan import require, number
from data.current_quantity_v2_paper_ledger import accept_proposal
from data.current_quantity_v2_paper_chain import create_chain
from backtest.current_quantity_v2_simulated_settlement import create_simulation, register_valuation
from backtest.current_quantity_v2_simulation_store import SimulationStore


def bootstrap(*, store, simulation_id, proposal, account_state, initial_cash,
              model, calendar, source_admission_guard,
              clock=lambda:datetime.now(timezone.utc)):
    require(isinstance(store,SimulationStore), 'ISOLATED_SIMULATION_STORE_REQUIRED')
    require(type(simulation_id) is str and simulation_id.strip(), 'SIMULATION_ID_REQUIRED')
    require(callable(source_admission_guard) and callable(clock), 'EXPLICIT_SOURCE_GUARD_REQUIRED')
    # Reject duplicate IDs before consulting a new clock. Never overwrite or
    # reinterpret a previous bootstrap as a new acceptance.
    if store.path.exists():
        try: store.read(simulation_id)
        except ValueError as error:
            if str(error) != 'SIMULATION_NOT_FOUND': raise
        else: raise ValueError('BOOTSTRAP_ALREADY_EXISTS')
    proposal, account_state = deepcopy(proposal), deepcopy(account_state)
    require(proposal.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION'
            and proposal.get('real_account') is False, 'CURRENT_CASH_SIMULATION_PROPOSAL_REQUIRED')
    cash=number(initial_cash)
    require(cash>0 and number(account_state['cash'])==cash
            and number(proposal['actual_cash'])==cash
            and not any(account_state['shares'].values())
            and number(account_state.get('reserved_cash','0'))==0,
            'EXPLICIT_PURE_CASH_GENESIS_REQUIRED')
    pins=proposal['causal_inputs']['frozen_execution_package']['source_hashes']
    require(type(pins) is dict and pins, 'FROZEN_SOURCE_PINS_REQUIRED')
    require(source_admission_guard(deepcopy(pins)) is not False, 'SOURCE_ADMISSION_REJECTED')
    accepted=clock()
    require(isinstance(accepted,datetime) and accepted.utcoffset() is not None, 'ACTUAL_AWARE_CLOCK_REQUIRED')
    accepted_at=accepted.astimezone(timezone.utc).isoformat()
    ledger=accept_proposal(proposal,account_state=account_state,now=accepted_at)
    simulation=create_simulation(chain=create_chain(ledger),simulation_id=simulation_id,model=model)
    simulation=register_valuation(simulation=simulation,calendar=deepcopy(calendar),
                                  initial_marks={},registered_at=accepted_at)
    # All rejection paths above are in memory; persistence begins only here.
    return store.create(simulation)
