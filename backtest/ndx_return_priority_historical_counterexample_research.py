"""One 84/42 chronological historical counterexample, never fresh future OOS.

The original all-training result is not read. Only first84 returns and quote84
enter selection. Last42 returns are consumed after fixed whole targets freeze.
"""
from copy import deepcopy
import hashlib
import json
import math

from backtest.ndx_return_priority_first_candidate_research import (
    Budget, evaluate_allocation, require, run_bounded_search,
)
from backtest import ndx_return_priority_first_candidate_inputs_v2 as fixed

FIT_COUNT = 84
EVALUATION_COUNT = 42
RISK_SCOPE = 'INITIAL_DEPLOYMENT_DAILY_DIAGNOSTICS_ONLY'


def chronology_inputs(*, prepared, panel, tsm_sidecar):
    """Pure chronological slicing. No rank, optimiser, objective or source IO."""
    close = panel['nominal_close']
    require(len(close['index']) == 127 and len(close['data']) == 127, 'Exact127 submitted nominal closes')
    days = [value[:10] for value in close['index']]
    require(days == [prepared['initial_price_date']] + prepared['return_dates'], 'Same127 calendar relation')
    require(days[-1] == prepared['cutoff'] and days == sorted(set(days)), 'Whole historical calendar remains visible')
    columns = {ticker: i for i,ticker in enumerate(close['columns'])}
    require(set(columns) == {row['ticker'] for row in prepared['securities']}, 'Complete submitted conditional pool')
    require(all(len(values) == len(columns) for values in close['data']), 'Whole close-row shape')
    target_prices = {row['security_id']: close['data'][FIT_COUNT][columns[row['ticker']]] for row in prepared['securities']}
    require(all(type(value) in (int,float) and math.isfinite(value) and value > 0 for value in target_prices.values()), 'Positive contemporaneous fit close references')
    train_returns = {sid:list(values[:FIT_COUNT]) for sid,values in prepared['returns'].items()}
    heldout_returns = {sid:list(values[FIT_COUNT:]) for sid,values in prepared['returns'].items()}
    require(all(len(values) == FIT_COUNT for values in train_returns.values())
            and all(len(values) == EVALUATION_COUNT for values in heldout_returns.values()), 'No dropped common return session')
    train_dates = prepared['return_dates'][:FIT_COUNT]
    evaluation_dates = prepared['return_dates'][FIT_COUNT:]
    require(train_dates[-1] == days[FIT_COUNT] and evaluation_dates[0] > train_dates[-1], 'Strict chronological separation')
    tsm_quotes, tsm_returns = tsm_sidecar['quotes'],tsm_sidecar['returns']
    require([row['session'] for row in tsm_quotes] == days
            and [row['session'] for row in tsm_returns] == prepared['return_dates'], 'Full TSM control calendar')
    control = {}
    for item in prepared['original8_definition']:
        sid,ticker = item['security_id'],item['ticker']
        if ticker == 'TSM':
            target = tsm_quotes[FIT_COUNT]['nominal_close']
            values = [row['price_return'] for row in tsm_returns[FIT_COUNT:]]
        else:
            target = close['data'][FIT_COUNT][columns[ticker]]
            source_sid = next(row['security_id'] for row in prepared['securities'] if row['ticker'] == ticker)
            values = heldout_returns[source_sid]
        control[sid] = dict(definition=deepcopy(item),target_price=target,evaluation_returns=list(values))
    require(len(control) == 8 and all(len(row['evaluation_returns']) == 42 for row in control.values()), 'Complete unchanged original8 heldout domain')
    return dict(train_returns=train_returns,heldout_returns=heldout_returns,target_prices=target_prices,
                train_dates=train_dates,evaluation_dates=evaluation_dates,fit_cutoff=days[FIT_COUNT],
                initial_training_price_date=days[0],control=control)


def load_fixed_chronology():
    """Reads registered v2 eight local pins, plus two repeated fixed panel/TSM reads.

    The repeated reads are disclosed IO, not hidden objective work. No raw-source
    replay or discovery of provider/serialized-source-reference paths occurs.
    """
    prepared = fixed.load_fixed_inputs()
    documents = {}
    for role in ('panel','tsm_sidecar'):
        relative,digest,size = fixed.BOUND[role]
        path = fixed.ROOT / relative
        fixed.regular(path)
        raw = path.read_bytes()
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, 'Repeated literal binding unchanged')
        documents[role] = json.loads(raw)
    sliced = chronology_inputs(prepared=prepared,panel=documents['panel']['panel'],tsm_sidecar=documents['tsm_sidecar'])
    return prepared,sliced


def evaluate_control(*, prepared, sliced):
    """One separately counted42-interval evaluation; no training control metric."""
    plan = prepared['plan']
    capacity = (plan['cash_usd']-plan['research_buffer_usd'])/(1+plan['fee_bps']/10000)
    control = sliced['control']
    all_quantities = {sid:math.floor(capacity*row['definition']['target_weight']/row['target_price']) for sid,row in control.items()}
    budget = Budget(1,0)
    result = evaluate_allocation(quantities={sid:q for sid,q in all_quantities.items() if q > 0},
        initial_prices={sid:row['target_price'] for sid,row in control.items()},
        returns={sid:row['evaluation_returns'] for sid,row in control.items()},
        metadata={sid:row['definition'] for sid,row in control.items()},policy=prepared['policy'],
        cash=plan['cash_usd'],fee_bps=plan['fee_bps'],buffer=plan['research_buffer_usd'],budget=budget,
        enforce_risk=False,risk_scope=RISK_SCOPE)
    require(result is not None,'Original8 same cash convention')
    result['historical_evaluation_metrics'] = result.pop('training_metrics')
    result.update(original8_definition=deepcopy(prepared['original8_definition']),all_eight_target_quantities=all_quantities,
                  zero_allocated_due_to_whole_share_floor=[row['definition']['ticker'] for sid,row in control.items() if all_quantities[sid] == 0],
                  target_prices={sid:row['target_price'] for sid,row in control.items()},
                  original_weights_unchanged=True,candidate_risk_gate_imposed=False,metric_calls=budget.objective_calls)
    return result


def calculate_counterexample(*, prepared, sliced):
    """No evaluation columns/dates/control metrics passed to selection engine."""
    plan = prepared['plan'];limits=plan['finite_budgets']
    selection = run_bounded_search(securities=prepared['securities'],initial_prices=prepared['initial_prices'],
        target_prices=sliced['target_prices'],returns=sliced['train_returns'],return_dates=sliced['train_dates'],
        cutoff=sliced['fit_cutoff'],policy=prepared['policy'],cash=plan['cash_usd'],fee_bps=plan['fee_bps'],
        buffer=plan['research_buffer_usd'],risk_scope=RISK_SCOPE,support_limit=limits['support_proposals_per_k'],
        per_support_objectives=limits['objective_evaluations_per_support'],per_support_integers=limits['integer_deployment_proposals_per_support'],
        global_objectives=limits['global_objective_evaluations'],global_integers=limits['global_integer_deployment_proposals'],seed=20261013)
    # Freeze complete training selection before inspecting any heldout objective.
    selected = deepcopy(selection['co_winners'])
    require(type(selection['budget']['objective_calls']) is int and 0 <= selection['budget']['objective_calls'] <= 311296
            and len(selected) <= selection['budget']['objective_calls'], 'Finite selected-winner count bounded by actual training objective calls')
    metadata = {row['security_id']:row for row in prepared['securities']}
    evaluations=[];evaluation_calls=0
    for ordinal,candidate in enumerate(selected):
        budget=Budget(1,0)
        result=evaluate_allocation(quantities=deepcopy(candidate['quantities']),initial_prices=sliced['target_prices'],
            returns=sliced['heldout_returns'],metadata=metadata,policy=prepared['policy'],cash=plan['cash_usd'],
            fee_bps=plan['fee_bps'],buffer=plan['research_buffer_usd'],budget=budget,enforce_risk=True,risk_scope=RISK_SCOPE)
        require(result is not None,'Frozen winner same initial target remains admissible')
        result['historical_evaluation_metrics']=result.pop('training_metrics')
        result.update(training_co_winner_ordinal=ordinal,metric_calls=budget.objective_calls,
                      evaluation_can_reselect_or_rank=False)
        evaluations.append(result);evaluation_calls+=budget.objective_calls
    control=evaluate_control(prepared=prepared,sliced=sliced)
    candidate_calls=selection['budget']['objective_calls']
    require(candidate_calls <= 311296 and evaluation_calls <= len(selected) and control['metric_calls'] == 1,'Explicit separate budgets')
    return dict(schema='RETURN_PRIORITY_84_42_HISTORICAL_COUNTEREXAMPLE_V1',
        status='HISTORICAL_COUNTEREXAMPLE_RESEARCH_NOT_FRESH_OOS',selection=selection,
        frozen_training_co_winners=selected,heldout_evaluations=evaluations,original8_heldout_control=control,
        chronology=dict(training_return_dates=sliced['train_dates'],evaluation_return_dates=sliced['evaluation_dates'],
            fit_cutoff=sliced['fit_cutoff'],initial_training_price_date=sliced['initial_training_price_date'],
            evaluation_final_date=sliced['evaluation_dates'][-1],training_intervals=84,evaluation_intervals=42,
            training_annualization_power=3,evaluation_annualization_power=6,
            target_quantity_price_date=sliced['fit_cutoff'],future_target_prices_in_selection=False),
        budgets=dict(candidate_training_objective_calls=candidate_calls,candidate_training_limit=311296,
            integer_proposals=selection['budget']['integer_proposals'],integer_limit=622592,
            winner_evaluation_calls=evaluation_calls,winner_evaluation_limit=len(selected),original8_evaluation_calls=1,
            original8_training_metric_calls=0,total_objective_calls=candidate_calls+evaluation_calls+1,
            validation_io_and_risk_are_separately_reported=True),
        full_conditional_inventory=prepared['securities'],all101_observed_provenance=prepared['observed_provenance'],
        source_bindings=prepared['source_bindings'],source_checks=prepared['source_checks'],search_seed=20261013,
        reused_all_training_selected_result=False,heldout_previously_observed=True,fresh_future_oos=False,
        full_point_in_time_qualification=False,actual_prior_holdings_plus_new_cash_joint_task_complete=False,
        future_one_year_independent_oos='NOT_CONSUMED_NOT_MATURE',current_adoption_allowed=False,orders_created=False,
        hypothetical_training_backcast_not_broker_fills=True,split_only_returns_not_total_return=True,
        source_io_scope='Eight literal pinned files plus repeat panel/TSM reads; no transitive claims IO',
        six_cutoff_thirteen_cohort_goal_complete=False)
