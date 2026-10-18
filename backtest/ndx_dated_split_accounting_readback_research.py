"""Independent single-freeze accounting replay; no producer or optimizer imports.

Money uses Fraction of independently supplied nominal quote strings. Original
float risk metrics are arithmetically crosschecked, then their exact saved float
values are tested against the original float thresholds. This does not claim
bitwise reconstruction of unordered set iteration in the historical engine.
"""
from copy import deepcopy
from fractions import Fraction as F
import json
import math


def require(ok,message):
    if not ok:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message='Exact evidence differs'):require(encode(a)==encode(b),message)
def number(v):
    require(type(v) in (int,float,str) and (type(v) is not float or math.isfinite(v)),'Finite nonboolean scalar')
    try:return F(str(v))
    except (ValueError,ZeroDivisionError):raise ValueError('Invalid rational') from None
def near(actual,expected,tolerance=F(1,10**7)):
    require(abs(number(actual)-expected)<=tolerance,'Independent arithmetic differs')
def ratio(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def lots(v):
    require(type(v) is dict and all(type(q) is int and q>0 for q in v.values()),'Positive whole held shares');return v


def verify_risk(saved,shares,marks,chains,parameters):
    if not shares:
        exact(saved,dict(checks={'ALL_CASH':False},all_passed=False));return {'ALL_CASH':False}
    notionals={s:q*marks[s] for s,q in lots(shares).items()};total=sum(notionals.values());weights={s:v/total for s,v in notionals.items()}
    ordered=sorted(weights.values(),reverse=True);groups={}
    for s,w in weights.items():groups[chains[s]]=groups.get(chains[s],F(0))+w
    independent=dict(top1_weight=ordered[0],minimum_single_weight=ordered[-1],top3_weight=sum(ordered[:3]),effective_n=1/sum(w*w for w in ordered),risk_chain_top1_weight=max(groups.values()))
    require(set(saved['actual_weights'])==set(weights),'Risk SID set')
    for s,w in weights.items():near(saved['actual_weights'][s],w,F(1,10**12))
    for k,v in independent.items():
        require(type(saved[k]) is float and math.isfinite(saved[k]),'Saved finite float risk metric')
        near(saved[k],v,F(1,10**11))
    checks=dict(MAX_SINGLE_WEIGHT=saved['top1_weight']<=parameters['max_single_weight']+1e-9,MIN_SINGLE_WEIGHT=saved['minimum_single_weight']>=parameters['min_single_weight']-1e-9,SECURITY_TOP3_WEIGHT=saved['top3_weight']<=parameters['top_weight_cap']+1e-9,MINIMUM_EFFECTIVE_N=saved['effective_n']>=parameters['minimum_effective_n_ratio']*len(shares)-1e-9,RISK_CHAIN_TOP1_WEIGHT=saved['risk_chain_top1_weight']<=parameters['risk_chain_top1_cap']+1e-9)
    exact(saved['checks'],checks);require(saved['all_passed'] is all(checks.values()),'Exact original float gate outcome')
    return checks


def audit_account(*,execution,account_input):
    """Replay one candidate only. Shared control is separately audited by reference."""
    a=account_input;cal=a['matrices']['close']['index'];require(len(cal)==127 and cal==sorted(set(cal)) and cal[0]=='2026-03-20' and cal[1]=='2026-03-23' and cal[-1]=='2026-09-21','Fixed127 calendar')
    require(execution['schema']=='ndx_dynamic_frozen_execution_research_v2' and len(a['schedule'])==len(execution['decisions'])==1,'Single candidate decision')
    require(a['external_cashflows']==[] and a['identity_events']==execution['identity_events']==[] and a['initial_holdings']=={},'No flows/renames/initial stocks')
    require(a['initial_cash_usd']==25000 and a['minimum_cash_buffer_usd']==100 and a['transaction_cost_bps']==10,'Original cash/fee contract')
    require(execution['execution_policy']=='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET','Frozen next Open contract')
    for k in ('auto_replan_enabled','point_in_time_verified','promotion_allowed','dividend_modelled','corporate_action_coverage_verified','source_authenticity_verified'):require(execution[k] is False,'Account research flags')
    schedule=deepcopy(a['schedule'][0]);require(schedule['decision_date']==cal[0] and schedule['execution_date']==cal[1],'Single entry clock')
    targets=schedule['targets'];sids=list(targets);require(sids==sorted(sids) and len({v['issuer_id'] for v in targets.values()})==len(sids),'Canonical unique issuers')
    require(all(type(t['target_weight']) in (float,int) and math.isfinite(t['target_weight']) and t['target_weight']>0 for t in targets.values()),'Only positive engine-compatible input')
    total=sum(float(t['target_weight']) for t in targets.values())
    for t in targets.values():t['target_weight']=float(t['target_weight'])/total
    aliases=a['engine_ticker_by_security'];require(set(aliases)==set(sids) and len(set(aliases.values()))==len(sids),'Distinct SID aliases')
    marks={d:{} for d in cal};conversion_count=0
    for sid in sids:
        rows=a['exact_quote_conversion_evidence'][sid];exact([r['session'] for r in rows],cal)
        for i,row in enumerate(rows):
            marks[cal[i]][sid]={}
            for field in ('open','close'):
                q=row[field];v=number(q['exact']);require(v>0 and type(q['value']) is float and float(v)==q['value'] and q['value'].hex()==q['float_hex'],'Exact to float mark evidence')
                matrix=a['matrices'][field];exact(matrix['index'],cal);require(matrix['data'][i][matrix['columns'].index(aliases[sid])]==q['value'],'Matrix conversion')
                marks[cal[i]][sid][field]=v;conversion_count+=1
    by_event={};seen=set()
    for e in a['corporate_actions']:
        require(set(e)=={'security_id','session','new_shares','old_shares','source_url','evidence_sha256'},'Explicit event keys')
        sid=e['security_id'];d=e['session'];key=(sid,d)
        require(sid in targets and d in cal and key not in seen,'Unique bound split');seen.add(key)
        require(type(e['new_shares']) is type(e['old_shares']) is int and min(e['new_shares'],e['old_shares'])>0 and e['new_shares']!=e['old_shares'],'Nontrivial integer split')
        by_event.setdefault(d,[]).append(e)
    require([r['session'] for r in execution['daily']]==cal,'Full daily denominator')
    action_by={r['session']:r for r in execution['corporate_actions']};require(len(action_by)==len(execution['corporate_actions']) and set(action_by)==set(by_event),'Every split trace exactly once')
    fills={r['session']:r for r in execution['executions']};require(len(fills)==len(execution['executions']) and len(fills)<=1,'At most one original basket attempt')
    decision=execution['decisions'][0];chains=a['risk_chains_by_decision'][cal[0]];params=a['risk_parameters']
    shares={};cash=F(25000);fee=F(1,1000);pending=None;expected_trades=[];values=[];fees=F(0);executions_seen=set();risk_false=0
    def mark(names,d,field):return {s:marks[d][s][field] for s in names}
    def check_marks(saved,expected):
        require(set(saved)==set(expected),'All mark SIDs')
        for s,v in expected.items():near(saved[s],v)
    def project(wanted,prices):
        delta={s:wanted.get(s,0)-shares.get(s,0) for s in sorted(set(wanted)|set(shares))}
        cost=sum(abs(q)*prices[s]*fee for s,q in delta.items());after=cash-sum(q*prices[s] for s,q in delta.items())-cost
        return delta,cost,after
    for i,d in enumerate(cal):
        if d in by_event:
            trace=action_by[d];whole={s:shares.get(s,0) for s in sids};applied=[]
            for e in by_event[d]:
                sid=e['security_id'];entitlement=F(whole[sid]*e['new_shares'],e['old_shares']);require(entitlement.denominator==1,'Unresolved fractional split entitlement')
                adapted={('ticker' if k=='security_id' else k):v for k,v in e.items()}
                applied.append(dict(event=adapted,pre_shares=whole[sid],post_shares=entitlement.numerator));whole[sid]=entitlement.numerator
            exact(trace['shares'],whole);near(trace['cash_usd'],cash);exact(trace['applied_events'],applied);near(trace['split_cash_flow_usd'],F(0));near(trace['split_fees_usd'],F(0))
            for k in ('evidence_authenticated','corporate_action_coverage_verified','broker_order_adjustment_modelled','promotion_allowed'):require(trace[k] is False,'Split scope')
            if pending is not None:
                exact(trace['cancelled_plan'],pending);require(trace['pending_plan'] is None and trace['pending_plan_status']=='CANCELLED_SPLIT_REQUIRES_NEW_SCHEDULED_DECISION','Pending cancelled before Open')
                exact(fills[d],dict(session=d,status='CANCELLED_SPLIT',decision_date=pending['decision_date'],plan=pending));executions_seen.add(d);pending=None
            else:
                require(trace['cancelled_plan'] is None and trace['pending_plan'] is None and trace['pending_plan_status']=='UNCHANGED','No invented pending basket')
            shares={s:q for s,q in whole.items() if q}
        if pending is not None and pending['execution_date']==d:
            fill=fills[d];executions_seen.add(d);wanted=lots(pending['desired_shares']);prices=mark(set(shares)|set(wanted),d,'open');delta,cost,projected=project(wanted,prices)
            eqfields=dict(decision_date=pending['decision_date'],desired_shares=wanted,frozen_delta=delta,shares_before=shares)
            for k,v in eqfields.items():exact(fill[k],v)
            exact(delta,pending['delta']);check_marks(fill['prices'],prices);near(fill['cash_before_usd'],cash);near(fill['projected_cash_usd'],projected);near(fill['projected_fees_usd'],cost)
            checks=verify_risk(fill['risk'],wanted,{s:prices[s] for s in wanted},chains,params);failures=[k for k,v in checks.items() if not v]
            # The stored float cash projection is independently checked above.
            if fill['projected_cash_usd']<a['minimum_cash_buffer_usd']-1e-8:failures.append('CASH_BUFFER')
            exact(fill['failure_reasons'],failures);require(fill['status']==('REJECTED' if failures else 'FILLED'),'Atomic execution status')
            if not failures:
                near(fill['accounting_error_usd'],F(0))
                expected_trades.extend(dict(session=d,security_id=s,ticker=aliases[s],share_delta=q,price_usd=prices[s],transaction_cost_usd=abs(q)*prices[s]*fee) for s,q in delta.items() if q)
                cash=projected;shares=dict(wanted);fees+=cost
            near(fill['cash_after_usd'],cash);exact(fill['shares_after'],shares);pending=None
        if i==0:
            for k in ('decision_date','execution_date','targets'):exact(decision[k],schedule[k])
            exact(decision['shares_before'],shares);near(decision['cash_before_usd'],cash);exact(decision['aliases'],[]);exact(decision['target_k'],len(targets))
            prices=mark(set(shares)|set(targets),d,'close');check_marks(decision['prices'],prices);exact(decision['risk_chains'],{s:chains[s] for s in prices});exact(decision['risk_chain_observation_dates'],dict.fromkeys(prices,d))
            if decision['status']=='FROZEN':
                wanted=lots(decision['desired_shares']);require(set(wanted)==set(targets),'Frozen full support');delta,cost,projected=project(wanted,prices)
                exact(decision['delta'],delta);near(decision['projected_cash_usd'],projected);near(decision['projected_fees_usd'],cost)
                require(decision['projected_cash_usd']>=a['minimum_cash_buffer_usd']-1e-8 and all(verify_risk(decision['decision_risk'],wanted,{s:prices[s] for s in wanted},chains,params).values()),'Frozen plan finance/risk')
                if decision['projection'] is not None:
                    require(decision['projection']['search_complete'] is True and decision['projection']['feasible_projection_found'] is True,'Saved repair completion');exact(decision['projection']['projected_shares'],wanted)
                pending=deepcopy(decision)
            else:
                require(decision['status']=='NO_PLAN' and not ({'desired_shares','delta','decision_risk','projected_cash_usd','projected_fees_usd'}&set(decision)),'Explicit no plan')
                projection=decision['projection'];require(type(projection) is dict and type(projection['search_complete']) is bool and type(projection['feasible_projection_found']) is bool and not (projection['search_complete'] and projection['feasible_projection_found']),'No plan saved search status, not global infeasibility')
        row=execution['daily'][i];cm=mark(shares,d,'close');exact(row['shares'],shares);exact(row['tickers'],{s:aliases[s] for s in shares});exact(row['risk_chains'],{s:chains[s] for s in shares});exact(row['risk_chain_observation_dates'],dict.fromkeys(shares,cal[0]));check_marks(row['prices'],cm)
        risk_false+=not all(verify_risk(row['risk'],shares,cm,chains,params).values());near(row['cash_usd'],cash);value=cash+sum(shares[s]*cm[s] for s in shares);near(row['total_value_usd'],value);values.append(value)
    require(pending is None and executions_seen==set(fills),'No missing or additional original execution')
    require(len(expected_trades)==len(execution['trades']),'Complete trade count')
    for expected,saved in zip(expected_trades,execution['trades']):
        for k,v in expected.items():
            if k in ('price_usd','transaction_cost_usd'):near(saved[k],v)
            else:exact(saved[k],v)
    peak=F(25000);dd=F(0)
    for v in values:peak=max(peak,v);dd=max(dd,1-v/peak)
    summary=execution['summary'];near(summary['terminal_value_usd'],values[-1]);near(summary['path_return_net'],values[-1]/25000-1);near(summary['path_max_drawdown'],dd);exact(summary['session_count'],127);exact(summary['all_cash_session_count'],sum(not r['shares'] for r in execution['daily']));exact(summary['k_path'],[len(targets)])
    return dict(schema='DATED_SPLIT_ACCOUNTING_INDEPENDENT_REPLAY_V1',status='PASS',daily_rows=127,quote_conversion_cells=conversion_count,decision_status=decision['status'],execution_statuses=[r['status'] for r in execution['executions']],trade_count=len(expected_trades),split_session_count=len(by_event),split_event_count=len(seen),terminal_shares=shares,terminal_cash_exact=ratio(cash),fees_exact=ratio(fees),terminal_equity_exact=ratio(values[-1]),return_exact=ratio(values[-1]/25000-1),maximum_drawdown_exact=ratio(dd),daily_risk_false_count=risk_false,monetary_tolerance_usd='1e-7',independent_risk_metric_tolerance='1e-11',risk_gates_replayed_from_saved_float_metrics=True,bitwise_unordered_float_summation_reconstructed=False,integer_search_independently_recomputed=False,engine_called=False,point_in_time_verified=False,promotion_allowed=False)
