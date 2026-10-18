"""Original V2 target search over a bound real strategy capital snapshot.

No empty-account adapter, broker IO, account write or policy promotion. The V2
objective scores whole target portfolios; its initial-buy fee model is not the
actual turnover cost of moving the current account to that target.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from core.strategy_account_ledger import canonical
from backtest.return_priority_fresh_cash_quantity_search_v2 import search_fresh_cash_quantities
from data.current_research_capital_decision_v2 import VERSION, REQUIRED_PINS
from data.strategy_account_target_inputs import build_target_inputs, require
from data.strategy_account_preview import preview_scoped_account


ROOT=Path(__file__).resolve().parents[1]


def validate_result(result,args):
    require(result.get('method_version')==VERSION,'TARGET_METHOD_MISMATCH')
    for key in ('decision_date','scenario_dates','max_objective_evaluations'):
        require(result.get(key)==args[key],'TARGET_RESULT_INPUT_MISMATCH')
    for key in ('entered_cash','fee_bps','minimum_cash_buffer'):
        require(Fraction(result[key])==Fraction(args[key]),'TARGET_RESULT_INPUT_MISMATCH')
    require(result.get('status') in {'BUDGET_STOPPED','PER_K_SEARCH_STOPPED_WITH_UNUSED_BUDGET','INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE'},'TARGET_STATUS_INVALID')
    selected=result.get('selected')
    if selected is None:
        require(result['status']=='INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE','TARGET_SELECTION_MISSING')
        return None
    require(result['status']!='INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE','TARGET_INCOMPLETE_SELECTION')
    quantities=selected['quantities']
    require(isinstance(quantities,dict) and set(quantities)<=set(args['prices']) and all(type(q)is int and q>0 for q in quantities.values()),'TARGET_QUANTITIES_INVALID')
    issuers=[args['metadata'][sid]['issuer_id'] for sid in quantities]
    require(len(issuers)==len(set(issuers)),'TARGET_DUPLICATE_ISSUER')
    cash=Fraction(args['entered_cash'])
    notional=sum((Fraction(args['prices'][sid])*q for sid,q in quantities.items()),Fraction(0))
    fee=notional*Fraction(args['fee_bps'])/10000;residual=cash-notional-fee
    require(residual>=0 and (not quantities or residual>=Fraction(args['minimum_cash_buffer'])),'TARGET_OVER_BUDGET')
    for key,value in [('notional',notional),('fees',fee),('residual_cash',residual)]:
        require(Fraction(selected[key])==value,'TARGET_ACCOUNTING_MISMATCH')
    require(type(selected['actual_k'])is int and selected['actual_k']==len(quantities),'TARGET_K_MISMATCH')
    weights=selected['actual_weights']
    require(set(weights)==set(quantities) and all(Fraction(weights[sid])==Fraction(args['prices'][sid])*q/cash for sid,q in quantities.items()),'TARGET_WEIGHT_MISMATCH')
    return deepcopy(quantities)


def decide_target(**input_arguments):
    inputs=build_target_inputs(**input_arguments)
    binding=inputs['binding'];pins=binding['source_hashes']
    for path in REQUIRED_PINS:
        require(path in pins and sha256((ROOT/path).read_bytes()).hexdigest()==pins[path],'V2_RUNTIME_SOURCE_CHANGED')
    result=search_fresh_cash_quantities(**deepcopy(binding['search_arguments']))
    target=validate_result(result,binding['search_arguments'])
    payload=dict(schema='REAL_STRATEGY_TARGET_DECISION_V1',input_id=inputs['input_id'],
        input_binding=binding,search_result=result,target_quantities=target)
    return dict(status='TARGET_READY' if target is not None else 'SEARCH_INCOMPLETE',
        decision_id=sha256(canonical(payload)).hexdigest(),payload=payload,core_calls=1,
        orders_created=False,execution_blocked=True,account_mutated=False,
        limitations=['V2 scores a whole target portfolio, not a claim that actual positions are empty.',
                    'Training purchase fees are not actual account rebalance fees.',
                    'Fresh execution limits, unchanged account revision and cash confirmation remain required.',
                    'No continuous-guided or half-exposure policy is activated.'])


def preview_target(*,decision,state,limits,now,maximum_mark_age_seconds,execution_fee_bps,legacy_shares):
    """For server-retained decisions only; hashes are integrity, not client authority."""
    payload=decision['payload'];binding=payload['input_binding']
    require(sha256(canonical(payload)).hexdigest()==decision['decision_id'],'TARGET_DECISION_CHANGED')
    require(sha256(canonical(binding)).hexdigest()==payload['input_id'],'TARGET_INPUT_CHANGED')
    require(decision['status']=='TARGET_READY','TARGET_NOT_READY')
    target=validate_result(payload['search_result'],binding['search_arguments'])
    require(target==payload['target_quantities'],'TARGET_QUANTITIES_CHANGED')
    require(state['account_id']==binding['account_id'] and state['revision']==binding['account_revision'],'STALE_ACCOUNT_TARGET')
    needed={sid for sid,q in state['shares'].items() if q}|set(target)|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
    require(set(limits)==needed,'EXECUTION_LIMIT_DOMAIN_MISMATCH')
    return preview_scoped_account(state=state,legacy_shares=legacy_shares,
        marks={sid:deepcopy(binding['marks'][sid]) for sid in needed},limits=limits,
        target_quantities=target,now=now,maximum_mark_age_seconds=maximum_mark_age_seconds,
        fee_bps=execution_fee_bps)
