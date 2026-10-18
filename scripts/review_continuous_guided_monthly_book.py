"""Saved-book independent arithmetic review; never invokes selection or book code."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
RUN='tmp/continuous_guided_monthly_book_20261016_v1'
LEDGER_REVIEW='tmp/monthly_latched_sma20_exit_review_20261016_v1.py'
LEDGER_SHA='ff5a979c688ae7acd49fedc34b8eedc517272639ccb73bde78241d3aafa8ed69'
METHOD='FAIR_K_V2_PLUS_CONTINUOUS32_EXPERIMENT_V1'


def require(ok,reason):
    if not ok:raise ValueError(reason)


def canonical(value,ascii=True):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=ascii,default=str,allow_nan=False).encode()


def positions(shares):return {s:q for s,q in shares.items()if q}


def review_candidates(args,result):
    comparison=result['continuous_comparison'];old=comparison['inherited_saved_result'];generated=comparison['additional_generation']
    require(old['method_version']=='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2' and result['method_version']==METHOD,'METHOD')
    require(comparison['binding']['search_arguments_sha256']==sha256(canonical(args)).hexdigest()
        and comparison['binding']['saved_result_sha256']==sha256(canonical(old)).hexdigest(),'CANDIDATE_BINDING')
    require(old['max_objective_evaluations']==args['max_objective_evaluations']==8192,'ORIGINAL_BUDGET')
    require(result['objective_evaluations']==old['objective_evaluations'],'ORIGINAL_EVALUATION_COUNT')
    require(comparison['inherited_coverage_reverified']is False and result['per_k']==old['per_k'],'COVERAGE_INHERITANCE')
    cash=F(args['entered_cash']);fee=F(args['fee_bps'])/10000;buffer=F(args['minimum_cash_buffer'])
    require(F(old['entered_cash'])==cash and old['decision_date']==args['decision_date'] and old['scenario_dates']==args['scenario_dates'],'OLD_RESULT_CONTEXT')
    prices={s:F(p)for s,p in args['prices'].items()};metadata=args['metadata'];scenarios=args['training_scenarios'];cache={}
    def evaluate(q):
        require(type(q)is dict and set(q)<=set(prices) and all(type(n)is int and n>0 for n in q.values()),'QUANTITIES')
        key=tuple(sorted(q.items()))
        if key in cache:return cache[key]
        require(len({metadata[s]['issuer_id']for s in q})==len(q),'ISSUERS')
        notional=sum((prices[s]*n for s,n in q.items()),F(0));fees=notional*fee;residual=cash-notional-fees
        require(residual>=0 and (not q or residual>=buffer),'BUDGET')
        wealth=[residual+sum((prices[s]*n*F(r[s])for s,n in sorted(q.items())),F(0))for r in scenarios]
        growth=[w/cash for w in wealth];product=math.prod(growth)
        cache[key]=((product,-notional,key),dict(notional=notional,fees=fees,residual_cash=residual,cash_fraction=residual/cash),growth,wealth)
        return cache[key]
    def check(record):
        q=record['quantities'];rank,amounts,growth,_=evaluate(q)
        require(record['actual_k']==len(q),'K')
        for k,v in amounts.items():require(F(record[k])==v,'ACCOUNTING_'+k)
        require({s:F(v)for s,v in record['actual_weights'].items()}=={s:prices[s]*n/cash for s,n in q.items()},'WEIGHTS')
        if record['training_gross_growth_product']is not None:require(F(record['training_gross_growth_product'])==rank[0],'PRODUCT')
        require(record['training_mean_net_log_wealth']==sum(math.log(g.numerator)-math.log(g.denominator)for g in growth)/len(growth),'DISPLAY_SCORE')
        return rank
    frontier={}
    for k,record in old['best_by_k'].items():
        rank=check(record);require(k==str(record['actual_k']),'OLD_K');frontier[k]=(rank,record['quantities'])
    oldrank=check(old['selected']);require(oldrank==max(v[0]for v in frontier.values()),'OLD_WINNER')
    oldcount=len(cache)
    require(generated['iterations_requested']==generated['iterations_completed']==generated['gradient_evaluations']==32
        and len(generated['trace'])==32 and generated['scenario_wealth_evaluations']==32*len(scenarios),'ITERATIONS')
    weights={s:F(0)for s in prices};seen={()};proposals=[{}];budget=max(F(0),cash-buffer)
    groups={}
    for s in sorted(prices):groups.setdefault(metadata[s]['issuer_id'],[]).append(s)
    for i,trace in enumerate(generated['trace']):
        step=F(2,i+2);vertex=trace['vertex']
        require(trace['iteration']==i+1 and F(trace['step'])==step and (vertex is None or vertex in prices),'TRACE')
        # Independent derivative in purchase-cost dollars. Cash is the zero
        # vertex; use the stored path only after checking its exact gradient.
        current_wealth=[]
        for scenario in scenarios:
            cash_left=cash-budget*sum(weights.values(),F(0))
            terminal_stock=sum((budget*weights[s]*prices[s]*F(scenario[s])/(prices[s]*(1+fee))for s in sorted(prices)),F(0))
            current_wealth.append(cash_left+terminal_stock)
        require(all(w>0 for w in current_wealth),'TRACE_NONPOSITIVE_WEALTH')
        derivatives={s:sum((budget*(prices[s]*F(scenario[s])/(prices[s]*(1+fee))-1)/wealth
            for scenario,wealth in zip(scenarios,current_wealth)),F(0))for s in sorted(prices)}
        largest=max(derivatives.values())
        expected_vertex=min(s for s,g in derivatives.items()if g==largest) if largest>0 else None
        require(vertex==expected_vertex,'TRACE_GRADIENT_VERTEX_MISMATCH')
        weights={s:(1-step)*w+(step if s==vertex else 0)for s,w in weights.items()}
        keep={min(ss,key=lambda s:(-weights[s],s))for ss in groups.values()}
        q={s:int(budget*weights[s]//(prices[s]*(1+fee)))for s in sorted(keep)};q={s:n for s,n in q.items()if n}
        signature=tuple(q.items());added=signature not in seen;require(added==trace['candidate_added'],'TRACE_DEDUP')
        if added:seen.add(signature);proposals.append(q)
    require(proposals==[r['quantities']for r in generated['candidates']] and len(proposals)==generated['candidate_count'],'TRACE_PROPOSALS')
    for proposal in generated['candidates']:
        rank,amounts,_,_=evaluate(proposal['quantities']);k=str(len(proposal['quantities']))
        require(proposal['actual_k']==int(k) and all(F(proposal[f])==amounts[f]for f in ('fees','residual_cash')),'PROPOSAL')
        if k not in frontier or rank>frontier[k][0]:frontier[k]=(rank,proposal['quantities'])
    require(set(frontier)==set(comparison['best_by_k']) and result['best_by_k']==comparison['best_by_k'],'MERGED_FRONTIER')
    for k,record in comparison['best_by_k'].items():require((check(record),record['quantities'])==frontier[k],'MERGED_K_WINNER')
    require(result['selected']==comparison['selected'],'AUGMENTED_SELECTED')
    rank=check(result['selected']);require(rank==max(v[0]for v in frontier.values()) and rank>=oldrank,'AUGMENTED_WINNER')
    require(comparison['exact_evaluations']==dict(saved_unique=oldcount,new_unique=len(cache)-oldcount),'EVALUATION_COUNTS')
    # Independently recompute AM-GM bound against the NEW selected wealth.
    _,_,_,wealth=evaluate(result['selected']['quantities'])
    base=sum((cash/w for w in wealth),F(0))
    coeff={s:sum(((F(row[s])-1-fee)/w for row,w in zip(scenarios,wealth)),F(0))/(1+fee)for s in prices}
    maximum=base+max(F(0),cash-buffer)*max(F(0),*coeff.values());bound=result['training_objective_bound']
    require(maximum>=len(scenarios) and bound['objective_value_optimal']==(maximum==len(scenarios)),'NEW_BOUND')
    if bound['maximum_wealth_ratio_sum']is not None:require(F(bound['maximum_wealth_ratio_sum'])==maximum,'NEW_BOUND_SUM')
    if bound['product_ratio_upper_bound']is not None:require(F(bound['product_ratio_upper_bound'])==(maximum/len(scenarios))**len(scenarios),'NEW_BOUND_RATIO')
    return dict(unique_targets=len(cache),strict_improvement=rank[0]>oldrank[0],old_k=len(old['selected']['quantities']),new_k=len(result['selected']['quantities']))


def audit(root=ROOT):
    root=Path(root);run=root/RUN;pins={}
    def read(path):
        raw=(root/path).read_bytes();pins[path]=sha256(raw).hexdigest();return json.loads(raw)
    if not (run/'terminal.json').exists() or not (run/'outcome.json').exists():return dict(status='NOT_READY')
    terminal=read(RUN+'/terminal.json');require(terminal['status']=='COMPLETE' and terminal['source_pins_unchanged'],'RUN_NOT_COMPLETE')
    pre=read(RUN+'/preflight.json');require(pre['initial_cash']=='20000' and pre['fee_bps']==pre['slippage_bps']=='0','ECONOMIC_INPUTS')
    for path,h in pre['source_hashes'].items():
        require(sha256((root/path).read_bytes()).hexdigest()==h,'SOURCE_DRIFT:'+path);pins[path]=h
    require(sha256((root/pre['prepared_path']).read_bytes()).hexdigest()==pre['prepared_sha256'],'PREPARED')
    prepared=read(pre['prepared_path']);out=read(RUN+'/outcome.json')
    require(sha256((root/LEDGER_REVIEW).read_bytes()).hexdigest()==LEDGER_SHA,'LEDGER_REVIEW_CHANGED');pins[LEDGER_REVIEW]=LEDGER_SHA
    limit=sys.get_int_max_str_digits()
    try:
        spec=importlib.util.spec_from_file_location('sealed_independent_ledger',root/LEDGER_REVIEW);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        ledger=module.review_ledger(out,prepared)
    finally:sys.set_int_max_str_digits(limit)
    days=prepared['session_dates'];states={r['date']:r for r in out['daily_ledger']};states[days[0]]=dict(cash='20000',shares={},equity='20000')
    windows={w['decision_date']:w for w in prepared['windows']};audits=[a for a in out['provider_audit']if a.get('selection')]
    selections={a['selection']['decision_date']:a for a in audits};calls=out['selection_account_states']
    require(len(audits)==len(calls)==len(windows)==34 and set(selections)==set(windows)
        and {c['decision_date']for c in calls}==set(windows),'MONTH_COVERAGE')
    rows=[]
    for call in calls:
        day=call['decision_date'];state=call['account_state'];prior=states[day];audit=selections[day];selection=audit['selection'];binding=selection['binding']
        require(F(state['cash'])==F(prior['cash']) and positions(state['shares'])==positions(prior['shares']),'OWN_BRANCH_STATE:'+day)
        require(F(binding['available_cash'])==F(state['cash']) and positions(binding['shares'])==positions(state['shares']),'CAPITAL_STATE_BINDING')
        require(binding['schema']=='CAPITAL_DECISION_CONTINUOUS_GUIDED_EXPERIMENT_V1' and binding['continuous_iterations']==32 and binding['selection_method']==METHOD,'METHOD_BINDING')
        require(sha256(canonical(binding,False)).hexdigest()==selection['decision_id'],'DECISION_HASH')
        require(selection['core_calls']==1 and selection['method']==METHOD,'CORE_CALLS')
        require(F(selection['investable_equity'])==F(prior['equity'])==F(binding['investable_equity']),'ACTUAL_EQUITY')
        args=deepcopy(windows[day]['search_arguments']);args['entered_cash']=selection['investable_equity'];require(args==binding['search_arguments'],'MONTHLY_INPUT_BINDING')
        require(all(pins.get(p)==h for p,h in binding['source_hashes'].items()),'BINDING_SOURCE_PINS')
        require(selection['target_quantities']==selection['search_result']['selected']['quantities']==audit['target_shares'],'MONTHLY_TARGET')
        require(max(args['scenario_dates'])<=day and max(windows[day]['training_dates'])<=day,'CAUSAL_INPUTS')
        checked=review_candidates(args,selection['search_result']);rows.append(dict(decision_date=day,own_equity=selection['investable_equity'],**checked))
    require(len(out['provider_audit'])==len(days)-1,'DAILY_PROVIDER_COUNT')
    assembled=read('tmp/daily_verified_domain_experiment_20261016_v2/assembled.json')
    waits=[];carried={}
    for day,a in zip(days[:-1],out['provider_audit']):
        require('risk_overlay'not in a,'UNDECLARED_OVERLAY')
        adjusted=dict(carried)
        for change in a.get('target_adjustments',[]):
            sid=change['security_id'];matches=[e for e in assembled['provider_actions']if e['date']==day and e['security_id']==sid]
            require(len(matches)==1,'TARGET_ACTION_SOURCE')
            action=matches[0];require(action['type']in('split','split_identity'),'TARGET_ACTION_NEEDS_REVIEW:'+action['type'])
            destination=action.get('new_security_id',sid);q=F(adjusted.pop(sid,0))*F(action['new_shares'])/F(action['old_shares'])
            require(q.denominator==1 and change['target_after']==int(q),'TARGET_ACTION_ARITHMETIC')
            adjusted[destination]=int(q)
        if a.get('selection'):adjusted=dict(a['selection']['target_quantities'])
        require(positions(adjusted)==positions(a['target_shares']),'TARGET_CARRY:'+day)
        carried=adjusted
        if a.get('action')=='WAIT_POST_ACTION_MARK':require(not a['orders'],'WAIT_HAS_ORDERS');waits.append(day);continue
        target=a['target_shares'];held=states[day]['shares'];expected={s:target.get(s,0)-held.get(s,0)for s in set(target)|set(held)}
        orders=a['orders'];actual={o['security_id']:o['quantity']*(1 if o['side']=='BUY'else -1)for o in orders}
        require(len(actual)==len(orders) and actual=={s:q for s,q in expected.items()if q},'DAILY_DIFFERENCE:'+day)
        require(all(o['decision_date']==day and o['active_date']==days[days.index(day)+1]for o in orders),'ORDER_TIMING')
    path='scripts/review_continuous_guided_monthly_book.py';pins[path]=sha256((root/path).read_bytes()).hexdigest()
    return dict(status='PASS_SAVED_CONTINUOUS_GUIDED_REVIEW',outcome_sha256=pins[RUN+'/outcome.json'],source_hashes=pins,
        ledger=ledger,monthly_own_state_checks=len(rows),monthly_rows=rows,wait_post_action_days=waits,
        optimizer_calls=0,generator_calls=0,book_calls=0,fw_gradient_choices_recomputed=True,
        actual_candidate_arithmetic_verified=True,independent_oos=False,point_in_time_certified=False,automatic_promotion=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    try:report=audit()
    except Exception as error:report=dict(status='REVIEW_BLOCKED',reason=str(error),error_type=type(error).__name__)
    if args.write and report['status']!='NOT_READY':
        with (ROOT/RUN/'independent_review_v1.json').open('x',encoding='utf-8')as stream:json.dump(report,stream,indent=2)
    print(json.dumps({k:v for k,v in report.items()if k not in ('source_hashes','monthly_rows')},ensure_ascii=False))
    raise SystemExit(0 if report['status'].startswith('PASS')or report['status']=='NOT_READY'else 2)
