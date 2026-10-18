"""Fixed 253-quote126/126 historical counterexample, no fresh OOS or tuning."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math

from backtest.ndx_return_priority_first_candidate_research import Budget,evaluate_allocation,require,run_bounded_search
from backtest import ndx_return_priority_first_candidate_inputs_v2 as fixed

BULK=('data/cache/research/bulk_long_window_channels_20261003_v1/channels.json',
      '0f13e2cca5979608d742bfe1bf7a04c46ee9ca4396e5f45f22741420ee540516',18735229)
PLAN=('research_contracts/return_priority_historical_126_126_plan_20261013_v1.json',
      'f52e015dce99afea1e6a8d0e01d6dfe1d53ca2ff68ed1c53dc8c273bf8e999c8',2722)
RISK_SCOPE='INITIAL_DEPLOYMENT_DAILY_DIAGNOSTICS_ONLY'


def prepare_chronology(*,prepared,bulk,tsm):
    calendar=bulk['calendar253']
    require(len(calendar)==253 and calendar==sorted(set(calendar)),'Exact253 common quote dates')
    require(calendar[0]=='2025-09-18' and calendar[126]=='2026-03-20' and calendar[-1]=='2026-09-21','Fixed historical window')
    require(bulk['training_return_count']==bulk['evaluation_return_count']==126
            and bulk['security_count']==77 and bulk['issuer_count']==76 and bulk['observed_security_count']==101,'Complete original domains')
    require(bulk['point_in_time_verified'] is False and bulk['future_independent_oos'] is False
            and bulk['evaluation_interval_previously_used_for_fitting'] is True,'Previously observed conditional history')
    require(len(bulk['rows'])==77 and bulk['conditional_numeric_channel_count']==77
            and bulk['blocked_price_channel_count']==0,'All77 numerical channels, no missing values filled')
    metadata={row['security_id']:row for row in prepared['securities']}
    channels={};initial={};target={};train={};evaluation={}
    for row in bulk['rows']:
        coordinate,channel=row['coordinate'],row['channel'];sid=coordinate['security_id']
        require(sid in metadata and sid not in channels
                and all(coordinate[key]==metadata[sid][key] for key in ('security_id','issuer_id','ticker','risk_chain')),'Exact original security/risk coordinates')
        require(channel['status']=='CONDITIONAL_NUMERIC_RESULT' and channel['ticker']==coordinate['ticker'],'Complete conditional numeric channel')
        quotes,returns=channel['quote_rows'],channel['return_rows']
        require(len(quotes)==253 and [r['session'] for r in quotes]==calendar
                and len(returns)==252 and [r['session'] for r in returns]==calendar[1:]
                and [r['previous_session'] for r in returns]==calendar[:-1],'No dropped session across fit/evaluation boundary')
        require(channel['training_returns']==returns[:126] and channel['evaluation_returns']==returns[126:],'Saved126/126 split association')
        for quote in quotes:
            require(Fraction(quote['nominal_close'])==Fraction(quote['nominal_close_exact'])
                    and Fraction(quote['nominal_close_exact'])>0,'Canonical positive nominal close reference')
        for value in returns:
            require(value['dividends_included'] is False
                    and type(value['split_only_return_float']) in (int,float)
                    and math.isfinite(value['split_only_return_float']) and value['split_only_return_float']>-1
                    and float(Fraction(value['split_only_return_exact']))==value['split_only_return_float'],'Explicit split-only Fraction/float boundary')
        initial[sid]=float(quotes[0]['nominal_close']);target[sid]=float(quotes[126]['nominal_close'])
        train[sid]=[r['split_only_return_float'] for r in returns[:126]]
        evaluation[sid]=[r['split_only_return_float'] for r in returns[126:]]
        channels[sid]=channel
    require(set(channels)==set(metadata),'No conditional member omitted')
    require([r['session'] for r in tsm['quotes']]==calendar[126:]
            and [r['session'] for r in tsm['returns']]==calendar[127:],'Registered TSM same127quote/126heldoutdates')
    by_ticker={row['ticker']:row['security_id'] for row in prepared['securities']}
    control={}
    for definition in prepared['original8_definition']:
        ticker,sid=definition['ticker'],definition['security_id']
        if ticker=='TSM':
            price=tsm['quotes'][0]['nominal_close'];values=[r['price_return'] for r in tsm['returns']]
        else:
            source_sid=by_ticker[ticker];price=target[source_sid];values=evaluation[source_sid]
        control[sid]=dict(definition=deepcopy(definition),target_price=price,evaluation_returns=list(values))
    require(len(control)==8,'All original eight definitions retained')
    return dict(initial_prices=initial,target_prices=target,train_returns=train,heldout_returns=evaluation,
                train_dates=calendar[1:127],evaluation_dates=calendar[127:],fit_cutoff=calendar[126],
                initial_training_price_date=calendar[0],control=control,
                historical_identity_assumed_window=deepcopy(bulk['original_identity_assumed_window']))


def load_fixed_chronology():
    relative,digest,size=PLAN;path=fixed.ROOT/relative;fixed.regular(path);raw=path.read_bytes()
    require(len(raw)==size and hashlib.sha256(raw).hexdigest()==digest,'Fixed Root126/126 registration unchanged')
    phase_plan=json.loads(raw)
    require(phase_plan['schema']=='ROOT_HISTORICAL_126_126_PLAN_V1','Phase126/126 registration')
    prepared=fixed.load_fixed_inputs();prepared['historical_phase_plan']=phase_plan;documents={}
    for role,reference in [('bulk',BULK),('tsm',fixed.BOUND['tsm_sidecar'])]:
        relative,digest,size=reference;path=fixed.ROOT/relative;fixed.regular(path);raw=path.read_bytes()
        require(len(raw)==size and hashlib.sha256(raw).hexdigest()==digest,'Registered local historical source changed')
        documents[role]=json.loads(raw)
    sliced=prepare_chronology(prepared=prepared,bulk=documents['bulk'],tsm=documents['tsm'])
    return prepared,sliced


def control_evaluation(*,prepared,sliced):
    plan=prepared['plan'];channels=sliced['control'];capacity=(plan['cash_usd']-plan['research_buffer_usd'])/(1+plan['fee_bps']/10000)
    q={sid:math.floor(capacity*row['definition']['target_weight']/row['target_price']) for sid,row in channels.items()}
    budget=Budget(1,0)
    evaluated=evaluate_allocation(quantities={sid:count for sid,count in q.items() if count>0},
        initial_prices={sid:row['target_price'] for sid,row in channels.items()},returns={sid:row['evaluation_returns'] for sid,row in channels.items()},
        metadata={sid:row['definition'] for sid,row in channels.items()},policy=prepared['policy'],cash=plan['cash_usd'],fee_bps=plan['fee_bps'],
        buffer=plan['research_buffer_usd'],budget=budget,enforce_risk=False,risk_scope=RISK_SCOPE)
    require(evaluated is not None,'Original8 same cash/fee/buffer convention')
    evaluated['historical_evaluation_metrics']=evaluated.pop('training_metrics')
    evaluated.update(original8_definition=deepcopy(prepared['original8_definition']),all_eight_target_quantities=q,
        original_weights_unchanged=True,candidate_risk_gate_imposed=False,metric_calls=budget.objective_calls,
        zero_allocated_due_to_whole_share_floor=[row['definition']['ticker'] for sid,row in channels.items() if q[sid]==0])
    return evaluated


def calculate_counterexample(*,prepared,sliced):
    plan=prepared['plan'];limits=plan['finite_budgets']
    selection=run_bounded_search(securities=prepared['securities'],initial_prices=sliced['initial_prices'],target_prices=sliced['target_prices'],
        returns=sliced['train_returns'],return_dates=sliced['train_dates'],cutoff=sliced['fit_cutoff'],policy=prepared['policy'],
        cash=plan['cash_usd'],fee_bps=plan['fee_bps'],buffer=plan['research_buffer_usd'],risk_scope=RISK_SCOPE,
        support_limit=limits['support_proposals_per_k'],per_support_objectives=limits['objective_evaluations_per_support'],
        per_support_integers=limits['integer_deployment_proposals_per_support'],global_objectives=limits['global_objective_evaluations'],
        global_integers=limits['global_integer_deployment_proposals'],seed=20261013)
    selected=deepcopy(selection['co_winners']);candidate_calls=selection['budget']['objective_calls']
    require(type(candidate_calls) is int and 0<=candidate_calls<=311296 and len(selected)<=candidate_calls,'Finite frozen training selection')
    metadata={row['security_id']:row for row in prepared['securities']};evaluations=[];calls=0
    for ordinal,candidate in enumerate(selected):
        budget=Budget(1,0)
        evaluated=evaluate_allocation(quantities=deepcopy(candidate['quantities']),initial_prices=sliced['target_prices'],returns=sliced['heldout_returns'],
            metadata=metadata,policy=prepared['policy'],cash=plan['cash_usd'],fee_bps=plan['fee_bps'],buffer=plan['research_buffer_usd'],
            budget=budget,enforce_risk=True,risk_scope=RISK_SCOPE)
        require(evaluated is not None,'Frozen target same initial risk/cash gate')
        evaluated['historical_evaluation_metrics']=evaluated.pop('training_metrics')
        evaluated.update(training_co_winner_ordinal=ordinal,metric_calls=budget.objective_calls,evaluation_can_reselect_or_rank=False)
        require(len(evaluated['net_wealth_path'])==128,'126evaluation plus initial capital/postfee points')
        evaluations.append(evaluated);calls+=budget.objective_calls
    control=control_evaluation(prepared=prepared,sliced=sliced)
    require(len(control['net_wealth_path'])==128 and control['metric_calls']==1 and calls==len(selected),'One metric per frozen winner plus one original8')
    return dict(schema='RETURN_PRIORITY_126_126_HISTORICAL_COUNTEREXAMPLE_V1',status='HISTORICAL_COUNTEREXAMPLE_NOT_FRESH_FUTURE_OOS',
        selection=selection,frozen_training_co_winners=selected,heldout_evaluations=evaluations,original8_heldout_control=control,
        chronology=dict(training_return_dates=sliced['train_dates'],evaluation_return_dates=sliced['evaluation_dates'],
            initial_training_price_date=sliced['initial_training_price_date'],fit_cutoff=sliced['fit_cutoff'],training_intervals=126,evaluation_intervals=126,
            training_annualization_power=2,evaluation_annualization_power=2,target_quantity_price_date=sliced['fit_cutoff'],future_target_prices_in_selection=False),
        budgets=dict(candidate_training_objective_calls=candidate_calls,candidate_training_limit=311296,integer_proposals=selection['budget']['integer_proposals'],
            integer_limit=622592,winner_evaluation_calls=calls,winner_evaluation_limit=len(selected),original8_evaluation_calls=1,
            original8_training_metric_calls=0,total_objective_calls=candidate_calls+calls+1,validation_io_and_risk_are_outside_objective_budget=True),
        full_conditional_inventory=deepcopy(prepared['securities']),all101_observed_provenance=deepcopy(prepared['observed_provenance']),
        source_bindings=dict(prepared['source_bindings'],bulk=dict(path=str(fixed.ROOT/BULK[0]),sha256=BULK[1],bytes=BULK[2]),
                             phase_plan=dict(path=str(fixed.ROOT/PLAN[0]),sha256=PLAN[1],bytes=PLAN[2])),
        source_checks=deepcopy(prepared['source_checks']),search_seed=20261013,parameters_changed=False,
        reused_prior_result_for_selection=False,heldout_previously_observed=True,fresh_future_oos=False,full_point_in_time_qualification=False,
        historical_identity_assumed_window=sliced['historical_identity_assumed_window'],
        prior_to2026_03_20_historical_identity_verified=False,current_adoption_allowed=False,orders_created=False,
        actual_prior_holdings_plus_new_cash_joint_task_complete=False,six_cutoff_thirteen_cohort_goal_complete=False,
        future_one_year_independent_oos='NOT_CONSUMED_NOT_MATURE',hypothetical_training_backcast_not_broker_fills=True,
        split_only_returns_not_total_return=True,source_io_scope='Eight pinned existing inputs plus fixed phase plan, one bulk and repeat TSM sidecar; no sourceclaim IO')
