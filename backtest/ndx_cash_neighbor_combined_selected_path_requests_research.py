"""Prepare candidate-only requests from saved conditional selections; no execution.

References are caller declarations until a separate source-bound consumer checks
bytes. This module never selects, reevaluates risk, computes returns or runs controls.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re

FLAGS=dict.fromkeys(('source_bytes_authenticated','selection_reexecuted','risk_recomputed','fees_recomputed','account_executed','control_reexecuted','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','economic_winner_selected','nav_fx_equivalence_verified'),False)
CLOCKS=(('2023-04-28','2023-05-01',87),('2023-05-31','2023-06-01',65),('2023-06-30','2023-07-03',44),('2023-07-31','2023-08-01',24),('2023-08-31','2023-09-01',1))
LANES=('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE')


def require(ok,message):
    if not ok:raise ValueError(message)


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def integer(value):require(type(value)is int and 0<=value<=10**12,'Whole nonnegative integer');return value


def number(value):
    require(type(value)in (str,int) and type(value)is not bool,'Saved decimal literal required')
    require(len(str(value))<=80,'Bounded decimal')
    try:d=Decimal(value)
    except Exception as error:raise ValueError('Invalid decimal')from error
    require(d.is_finite() and len(d.as_tuple().digits)<=40 and abs(d.as_tuple().exponent)<=40,'Finite bounded decimal')
    return Fraction(d)


def reference(value):
    require(type(value)is dict and set(value)=={'path','sha256','json_pointer'},'Explicit source pointer')
    require(type(value['path'])is str and value['path'].strip()==value['path'] and value['path'],'Source path')
    require(type(value['sha256'])is str and re.fullmatch('[a-f0-9]{64}',value['sha256']),'Source SHA')
    require(type(value['json_pointer'])is str and value['json_pointer'].startswith('/'),'Source JSON pointer')
    return deepcopy(value)


def prepare_case(case,index):
    p,s,old=case['prepared'],case['selection'],case['old_paired_row'];c=p['contract'];row=c['original_input_row']
    refs={k:reference(case[k])for k in ('selection_reference','selection_audit_reference','old_paired_reference')}
    exact(p['contract_sha256'],digest(c),'Whole contract digest');exact(s['contract_sha256'],p['contract_sha256'],'Selection contract')
    require(c['schema']=='CONDITIONAL_TOPUP_NEIGHBOR_SCENARIO_CONTRACT_V1' and s['schema']=='CASH_NEIGHBOR_COMBINED_STREAM_SCENARIO_SELECTION_V1','Saved contract schemas')
    sid=row['scenario_id'];exact(s['scenario_id'],sid,'Selection scenario');exact(old['scenario_id'],sid,'Old scenario');exact(old['input_row'],row,'Entire old input contract')
    exact(old['input_reference'],c['input_reference'],'Old input source');exact(old['topup_context_reference'],c['previous_result_reference'],'Old context source')
    exact(old['topup_context']['input_row'],row,'Preserved context input');exact(old['topup_context']['domain']['conditional_research_buy_ids'],c['conditional_research_buy_ids'],'Old domain');exact(old['topup_context']['domain']['buy_limits'],c['saved_buy_limits'],'Old caps')
    for obj in (row,s,old):
        for flag in ('orders_executed','point_in_time_verified','promotion_allowed'):require(obj[flag]is False,'Saved authority '+flag)
    ids=c['conditional_research_buy_ids'];require(ids==sorted(set(ids)) and ids,'Canonical full coordinates')
    require(set(ids)==set(c['saved_buy_limits'])==set(row['securities'])==set(row['execution_prices']),'Complete original quote domain, including zeros')
    require(set(row['holdings'])<=set(ids),'Full old holdings')
    for q in row['holdings'].values():integer(q)
    mapping={key:v['ticker']for key,v in row['securities'].items()};require(len(set(mapping.values()))==len(mapping),'No ticker collapsing');exact(old['security_to_ticker'],mapping,'Original SID mapping')
    event=row['cash_event'];clock=(event['decision_date'],event['execution_date']);counts={(a,b):n for a,b,n in CLOCKS}
    require(row['lane']in LANES and clock in counts and event['amount_usd']in ('1000','10000'),'Fixed original scenario coordinate');require(number(row['transaction_cost_bps'])==10,'Original 10bps')
    original_index=integer(c['original_selected_candidate_index']);oldplan=old['selected_plan'];points=c['old_evaluated_points']
    require(original_index<len(points) and oldplan['feasible']is True,'Original selected feasible point')
    exact(old['topup_context']['selected_candidate_index'],original_index,'Original selected context index');integer(oldplan['supplied_plan_index']);exact(oldplan['supplied_plan_index'],original_index,'Old plan index')
    point=points[original_index];exact(point['candidate_index'],original_index,'Original point index');exact(point['buy_shares'],oldplan['buy_shares'],'Original selected vector');require(point['saved_feasible']is True,'Original saved feasible')
    planref=dict(c['previous_result_reference'],json_pointer=c['previous_result_reference']['json_pointer']+'/evaluation/branches/0/evaluated_plans/'+str(original_index));exact(old['selected_plan_reference'],planref,'Original selected pointer');exact(point['reference'],planref,'Contract original point pointer')
    base=refs['old_paired_reference'];require(base['json_pointer']==f'/rows/{index}','Original paired row index')
    oldpath=dict(reference=dict(base,json_pointer=base['json_pointer']+'/paths/candidate'),scenario_id=sid,selected_candidate_index=original_index,buy_shares=oldplan['buy_shares']);exact(s['old_selected_path'],oldpath,'Saved oldbest path')
    template=old['paths']['candidate']['accounting_inputs'];initial=template['initial'];sessions=template['sessions']
    exact(initial['session'],event['decision_date'],'Initial decision Close');exact(initial['cash_usd'],row['starting_cash_usd'],'Initial saved cash');exact(initial['holdings'],row['holdings'],'Initial whole holdings');exact(template['transaction_cost_bps'],row['transaction_cost_bps'],'Fee unchanged')
    exact(old['paths']['same_flow_zero_trade_control']['accounting_inputs']['initial'],initial,'Common old control initial')
    require(set(initial['close_prices'])==set(row['holdings']),'All initial marks')
    days=[d['session']for d in sessions];require(len(days)==counts[clock] and days==sorted(set(days)) and days[0]==event['execution_date'] and days[-1]=='2023-09-01','Complete unchanged path calendar')
    for d in [initial['session']]+days:require(type(d)is str and date.fromisoformat(d).isoformat()==d,'Canonical date')
    for i,session in enumerate(sessions):
        for field in ('open_prices','close_prices'):
            require(set(session[field])==set(ids),'Every quote including zero slots');require(all(number(v)>0 for v in session[field].values()),'Positive saved marks')
        exact(session['buy_shares'],oldplan['buy_shares']if i==0 else {},'Original one trade only');require(number(session['cash_injection_usd'])==(number(event['amount_usd'])if i==0 else 0),'Original one flow')
    for key in ids:require(number(sessions[0]['open_prices'][key])==number(row['execution_prices'][key]),'First Open equals evaluation')
    selected=s['selected'];status=s['status'];request=None;reuse=None
    if selected is None:
        require(status=='NO_FEASIBLE_IN_DECLARED_UNION' and s['reused_path_reference']is None,'Absence is not all cash')
        require(not any(point['saved_feasible']is True for point in points),'No-feasible contradicts known old feasible union')
    else:
        plan=selected['saved_plan'];require(selected['feasible']is True and plan['feasible']is True,'Selected saved feasibility');exact(selected['buy_shares'],plan['buy_shares'],'Selected vector')
        require(set(plan['buy_shares'])==set(ids),'Complete selected buy vector')
        for key,q in plan['buy_shares'].items():require(integer(q)<=integer(c['saved_buy_limits'][key]),'Saved cap')
        exact(plan['proposed_holdings'],{key:row['holdings'].get(key,0)+plan['buy_shares'][key]for key in ids},'Full final holdings')
        if selected['origin']=='NEW':
            task=selected['identity'];identity=task['identity'];require(identity['schema']=='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1','New task schema');exact(identity['rule'],c['rule'],'Same registered neighbor rule');exact(task['task_id'],digest(identity),'New task identity');exact(task['scenario_id'],sid,'Task scenario');exact(identity['scenario_contract_sha256'],p['contract_sha256'],'Task contract');exact(identity['buy_shares'],plan['buy_shares'],'Task vector')
        else:
            require(selected['origin']=='OLD','Known origin');j=integer(selected['identity']['old_candidate_index']);require(j<len(points) and points[j]['saved_feasible']is True,'Old selected feasible point');exact(points[j]['buy_shares'],plan['buy_shares'],'Old point vector')
        same=encoded(plan['buy_shares'])==encoded(oldplan['buy_shares'])
        require(status==('REUSE_EXISTING_PAIRED_PATH'if same else 'NEW_PATH_REQUIRED'),'Correct reuse partition')
        if same:exact(plan,oldplan,'Entire reused saved plan');exact(s['reused_path_reference'],oldpath['reference'],'Exact reused pointer');reuse=deepcopy(oldpath['reference'])
        else:
            require(s['reused_path_reference']is None,'New identity cannot borrow old path');request=deepcopy(template);request['sessions'][0]['buy_shares']=deepcopy(plan['buy_shares'])
    return dict(schema='CASH_NEIGHBOR_SELECTED_PATH_REQUEST_V1',scenario_index=index,scenario_id=sid,status=status,accounting_request=request,reused_candidate_path_reference=reuse,control_path_reference=dict(base,json_pointer=base['json_pointer']+'/paths/same_flow_zero_trade_control'),expected_first_trade=None if selected is None else {k:deepcopy(selected['saved_plan'][k])for k in ('buy_shares','proposed_holdings','gross_buy_usd','fees_usd','cash_after_usd')},selection=deepcopy(s),prepared_contract=deepcopy(p),old_paired_evidence=deepcopy(old),input_references=refs,policy_asymmetry='CANDIDATE_EXECUTION_OPEN_CONDITIONAL_SELECTION_ONE_OFF_BUY_HOLD;INCUMBENT_PRIOR_CLOSE_FREEZE_MONTHLY_REBALANCE',candidate_decision_time_executability_verified=False,nav_reference_diagnostics_allowed=True,**FLAGS)


def prepare_selected_path_requests(*,cases,expected_scenario_ids):
    require(type(cases)is list and len(cases)==40 and type(expected_scenario_ids)is list and len(expected_scenario_ids)==len(set(expected_scenario_ids))==40,'Complete explicit ordered forty')
    rows=[];coordinates=set();counts={k:0 for k in ('REUSE_EXISTING_PAIRED_PATH','NEW_PATH_REQUIRED','NO_FEASIBLE_IN_DECLARED_UNION')}
    for i,case in enumerate(cases):
        result=prepare_case(case,i);exact(result['scenario_id'],expected_scenario_ids[i],'Original scenario order');row=case['prepared']['contract']['original_input_row'];e=row['cash_event'];coordinates.add((row['lane'],e['decision_date'],e['execution_date'],e['amount_usd']));counts[result['status']]+=1;rows.append(result)
    require(coordinates=={(l,d,e,a)for l in LANES for d,e,_ in CLOCKS for a in ('1000','10000')},'All forty unique coordinates')
    return dict(schema='CASH_NEIGHBOR_SELECTED_PATH_REQUESTS_V1',rows=rows,scenario_count=40,status_counts=counts,new_account_request_count=counts['NEW_PATH_REQUIRED'],no_feasible_is_cash_return=False,source_reference_semantics='CALLER_DECLARED_UNTIL_SOURCE_BOUND_BYTES_VERIFIED',**FLAGS)
