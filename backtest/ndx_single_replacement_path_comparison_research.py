"""Forty newly signed replacement paths and three saved historical references.

No account execution, source authentication, new selection or currency conversion.
NAV is a CNY-labeled reference; normalized differences are not USD equivalence.
"""
from copy import deepcopy
from decimal import Context,Decimal,ROUND_HALF_EVEN,localcontext
from fractions import Fraction
from datetime import date
import hashlib,json,re
from backtest import ndx_cash_fork_reference_window_research as metrics_core

METRICS_SOURCE_SHA256='0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163'
CLOCKS=(('2023-04-28','2023-05-01',87),('2023-05-31','2023-06-01',65),('2023-06-30','2023-07-03',44),('2023-07-31','2023-08-01',24),('2023-08-31','2023-09-01',1))
LANES=('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE')
AVAILABLE=('AVAILABLE_NEW_SIGNED',)
ABSENT=('NO_FEASIBLE','BLOCKED_TEMPLATE_PRICE_GAP','TECHNICAL_FAILURE','UNDISPATCHED','UNRESOLVED_DISPATCH')
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_executed','controls_executed','selection_reexecuted','risk_recomputed','fit_performed','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','formal_dual_benchmark_admission','economic_winner_selected','cross_window_ranking_performed','currency_fx_equivalence_verified','nav_dataset_currency_binding_certified','nav_publication_time_verified','candidate_decision_time_executability_verified'),False)
POLICY_ASYMMETRY='CANDIDATE_SINGLE_REPLACEMENT_SIGNED_OPEN_BASKET_BOTH_SIDE_FEES_THEN_HOLD;INCUMBENT_PRIOR_CLOSE_FREEZE_AND_LATER_MONTHLY_REBALANCE;SAME_FLOW_DOES_NOT_PROVE_SAME_INFORMATION_OR_EXECUTABILITY'


def require(ok,message):
    if not ok:raise ValueError(message)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(enc(a)==enc(b),message)
def fingerprint(v):return hashlib.sha256(enc(v)).hexdigest()
def number(v):return metrics_core.number(v)
def ratio(v):return metrics_core.ratio(v)
def value(v):return metrics_core.from_ratio(v)
def pointer(r,suffix):return dict(r,json_pointer=r['json_pointer']+suffix)


def reference(r):
    require(type(r)is dict and set(r)=={'path','sha256','json_pointer'},'Explicit saved object reference')
    require(type(r['path'])is str and r['path'] and r['path'].strip()==r['path'],'Source path')
    require(type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Source SHA')
    require(type(r['json_pointer'])is str and r['json_pointer'].startswith('/'),'JSON pointer')
    return deepcopy(r)


def evidence_reference(r):
    if type(r)is dict and set(r)=={'path','sha256','document_scope'}:
        require(r['document_scope']=='WHOLE_MARKDOWN_REPORT' and type(r['path'])is str and r['path'].lower().endswith('.md'),'Real Markdown report scope')
        reference(dict(path=r['path'],sha256=r['sha256'],json_pointer='/'))
        return deepcopy(r)
    return reference(r)


def initial_equal(left,right):
    require(set(left)==set(right)=={'session','cash_usd','holdings','close_prices'},'Explicit initial state')
    exact(left['session'],right['session'],'Common initial date');exact(left['holdings'],right['holdings'],'All original shares including zeros')
    require(all(type(q)is int and q>=0 for q in left['holdings'].values()),'Whole old shares')
    require(set(left['close_prices'])==set(right['close_prices'])==set(left['holdings']),'All initial Close marks')
    require(number(left['cash_usd'])==number(right['cash_usd'])>=0,'Same initial cash')
    for sid in left['holdings']:require(number(left['close_prices'][sid])==number(right['close_prices'][sid])>0,'Same initial mark')


def path_metrics(account,calendar,event,*,signed=False,zero_trade=False,saved_metrics=None):
    require(account['schema']==('SIGNED_FLOW_FROZEN_INCUMBENT_OPEN_ACCOUNT_V1'if signed else 'BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1'),'Saved path schema')
    for flag in ('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled'):require(account[flag]is False,'Preserved account limits')
    daily=account['daily']if signed else account['rows'];require(type(daily)is list and [d['session']for d in daily]==calendar[1:],'Full calendar, no intersection')
    require(account['cash_event_timing']==('AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES'if signed else 'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES'),'Flow timing')
    require(number(account['transaction_cost_bps'])==10 and number(account['total_cash_injection_usd'])==number(event['amount_usd']),'Original fee and flow')
    if signed:require(account['flow_policy']=='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN' and account['risk_is_order_gate']is False,'Original incumbent policy')
    for i,day in enumerate(daily):
        require(number(day['cash_injection_usd'])==(number(event['amount_usd'])if i==0 else 0),'Same once-only cash event')
        if zero_trade:
            exact(day['buy_shares'],{},'Zero-trade control');require(number(day['fees_usd'])==number(day['gross_buy_usd'])==0,'No control fee or trade')
    require(value(account['chained_twr'])==value(daily[-1]['cumulative_twr']),'Saved terminal TWR summary')
    wealth=[Fraction(1)]+[1+value(d['cumulative_twr'])for d in daily]
    return metrics_core.metrics(calendar,wealth)if saved_metrics is None else saved_metric(saved_metrics,calendar,wealth)


def validate_buy_only_inputs(envelope,calendar):
    args=envelope['accounting_inputs'];account=envelope['account'];daily=account['rows']
    require(number(args['transaction_cost_bps'])==number(account['transaction_cost_bps'])==10,'Saved input/account fee')
    require(type(args['sessions'])is list and [r['session']for r in args['sessions']]==calendar[1:],'Input/account complete calendar')
    exact(daily[0]['holdings_before'],args['initial']['holdings'],'Initial shares must match first daily holdings')
    for inputs,row in zip(args['sessions'],daily):
        exact(inputs['buy_shares'],row['buy_shares'],'Saved input/account buys')
        require(number(inputs['cash_injection_usd'])==number(row['cash_injection_usd']),'Saved input/account flow')


SIGNED_TIMING='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_BASKET_AND_BOTH_SIDE_FEES'
INSPECTION_FALSE=('source_bytes_authenticated','producer_called','producer_helpers_called','account_executed','orders_executed','fit_executed','risk_evaluated','action_family_verified','exchange_session_adjacency_verified','broker_settlement_verified','point_in_time_verified','promotion_allowed')


def signed_candidate_metrics(envelope,calendar,event):
    """Check saved signed metadata; compute only the new candidate's TWR metrics.

    The declared independent report is content-linked, not authenticated here.
    This is not a second full cash ledger inspection or a source reader.
    """
    args=envelope['accounting_inputs'];account=envelope['account'];report=envelope['account_inspection']
    reference(envelope['inspection_reference'])
    require(account['schema']=='SIGNED_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1','New signed account schema; buy-only/reused paths are not candidates')
    require(account['cash_event_timing']==SIGNED_TIMING,'Signed basket flow timing')
    require(account['execution_assumption']=='SAME_OPEN_NET_CASH_SETTLEMENT_SELL_PROCEEDS_AVAILABLE_FOR_BUYS','Signed Open settlement assumption')
    for flag in ('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled','broker_settlement_or_intraday_ordering_verified','single_replacement_action_semantics_verified','cash_buffer_and_risk_gates_evaluated'):
        require(account[flag]is False,'Saved signed limitations')
    require(report['schema']=='SIGNED_CASH_FLOW_ACCOUNT_INDEPENDENT_INSPECTION_V1' and report['status']=='PASS','Declared signed accounting inspection')
    require(report['scope']=='EXPLICIT_SIGNED_WHOLE_SHARE_ACCOUNTING_ONLY_NOT_ACTION_POLICY_OR_SOURCE_AUTHENTICATION','Signed inspection scope')
    for key in INSPECTION_FALSE:require(report[key]is False,'Inspection does not grant authority')
    require(report['all_saved_rows_and_fields_checked']is True and report['saved_result_content_sha256']==fingerprint(account),'Inspection binds complete saved result')
    require(type(report['session_count'])is int and report['session_count']==len(calendar)-1 and report['initial_session']==calendar[0] and report['terminal_session']==calendar[-1],'Inspection calendar')
    require(number(args['transaction_cost_bps'])==number(account['transaction_cost_bps'])==10,'Original signed fee')
    sessions=args['sessions'];daily=account['rows']
    require(type(sessions)is list and type(daily)is list and [r['session']for r in sessions]==[r['session']for r in daily]==calendar[1:],'Complete signed input/result calendar')
    exact(daily[0]['holdings_before'],args['initial']['holdings'],'Signed initial shares')
    initial_equity=number(args['initial']['cash_usd'])+sum((q*number(args['initial']['close_prices'][sid])for sid,q in args['initial']['holdings'].items()),Fraction(0))
    require(number(account['initial_equity_usd'])==number(daily[0]['previous_close_equity_usd'])==initial_equity>0,'Signed original initial equity')
    exact(daily[0]['previous_close_session'],calendar[0],'Signed original initial Close date')
    expected_universe=set(args['initial']['holdings'])|set(sessions[0]['trade_shares']);paid=Fraction(0)
    for i,(inputs,row)in enumerate(zip(sessions,daily)):
        require(set(inputs)=={'session','open_prices','close_prices','cash_injection_usd','trade_shares'},'Explicit signed session fields')
        trades=inputs['trade_shares'];require(type(trades)is dict and all(type(q)is int for q in trades.values()),'Signed whole-share trades')
        exact(trades,row['trade_shares'],'Signed input/result trades including negative leg')
        require(set(inputs['open_prices'])==set(inputs['close_prices'])==expected_universe,'Complete original price universe')
        if i==0:
            require(set(trades)==expected_universe,'First signed basket preserves zero keys')
            sells=[sid for sid,q in trades.items()if q<0];buys=[sid for sid,q in trades.items()if q>0]
            require(len(sells)==len(buys)==1 and sells[0]!=buys[0] and trades[sells[0]]==-args['initial']['holdings'][sells[0]] and args['initial']['holdings'].get(buys[0],0)==0,'One complete outgoing holding and one incoming purchase')
        else:exact(trades,{},'No subsequent candidate trades')
        require(number(inputs['cash_injection_usd'])==number(row['cash_injection_usd'])==(number(event['amount_usd'])if i==0 else 0),'Signed once-only matched flow')
        bought=sold=Fraction(0)
        for sid in expected_universe:
            price=number(inputs['open_prices'][sid]);require(price>0 and number(inputs['close_prices'][sid])>0,'Positive saved prices')
            q=trades.get(sid,0)
            if q>0:bought+=q*price
            elif q<0:sold-=q*price
        fee=(bought+sold)*Fraction(10,10000)
        require(number(row['gross_buy_usd'])==bought and number(row['gross_sell_usd'])==sold and number(row['fees_usd'])==fee,'Both signed legs and bilateral fee')
        paid+=fee
    require(number(account['total_fees_usd'])==paid and number(account['total_cash_injection_usd'])==number(event['amount_usd']),'Signed fee/flow totals')
    require(value(account['chained_twr'])==value(daily[-1]['cumulative_twr']),'Signed terminal TWR')
    return metrics_core.metrics(calendar,[Fraction(1)]+[1+value(row['cumulative_twr'])for row in daily])


def saved_metric(envelope,calendar,wealth):
    reference(envelope['reference']);evidence_reference(envelope['evidence_reference']);m=envelope['metrics']
    require(type(m['observation_count'])is int and m['observation_count']==len(calendar) and type(m['interval_count'])is int and m['interval_count']==len(calendar)-1,'Saved reference counts')
    exact(m['wealth'],[dict(session=day,normalized_wealth=ratio(w))for day,w in zip(calendar,wealth)],'Saved reference wealth/source consistency')
    require(all(w>0 for w in wealth) and wealth[0]==1,'Positive reference wealth');exact(m['cumulative_return'],ratio(wealth[-1]-1),'Saved reference terminal return')
    require(0<=value(m['maximum_drawdown'])<1 and m['initial_one_in_drawdown']is True and m['annualized_return_calculated']is True,'Saved metric structure')
    require(type(m['annualized_return_diagnostic_decimal'])is str and Decimal(m['annualized_return_diagnostic_decimal']).is_finite(),'Saved finite annual diagnostic')
    a=m['annualization'];require(type(a['interval_count'])is int and a['interval_count']==len(calendar)-1 and a['annualization_is_historical_diagnostic']is True and a['formal_admission_allowed']is False,'Saved annual diagnostic scope')
    return deepcopy(m)


def differences(left,right):
    with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
        annual=Decimal(left['annualized_return_diagnostic_decimal'])-Decimal(right['annualized_return_diagnostic_decimal'])
    return dict(cumulative_return=ratio(value(left['cumulative_return'])-value(right['cumulative_return'])),maximum_drawdown=ratio(value(left['maximum_drawdown'])-value(right['maximum_drawdown'])),annualized_return_diagnostic_decimal=str(annual),annual_arithmetic='DECIMAL80_DIFFERENCE_OF_SAVED_DIAGNOSTICS',formal_gate=False)


def compare_case(case,index,incumbent_groups):
    row=case['input_row'];event=row['cash_event'];sid=case['scenario_id'];exact(row['scenario_id'],sid,'Original scenario identity');reference(case['input_reference']);reference(case['selection_reference'])
    require(row['lane']in LANES and event['amount_usd']in ('1000','10000'),'Original scenario labels');clock=(event['decision_date'],event['execution_date']);lengths={(a,b):n for a,b,n in CLOCKS};require(clock in lengths,'Original window')
    for flag in ('orders_executed','point_in_time_verified','promotion_allowed'):require(row[flag]is False,'Input limits')
    require(number(row['transaction_cost_bps'])==10,'Original fee')
    zero=case['zero_trade_control'];inc=case['incumbent'];candidate=case['candidate']
    for envelope in (zero,inc):reference(envelope['account_reference']);evidence_reference(envelope['evidence_reference'])
    reference(zero['inputs_reference']);initial=zero['accounting_inputs']['initial'];reference(inc['mapping_reference']);mapping=inc['mapping']
    exact(initial['session'],event['decision_date'],'Initial clock');exact(initial['holdings'],row['holdings'],'Original holdings');require(number(initial['cash_usd'])==number(row['starting_cash_usd']),'Original cash');initial_equal(initial,inc['account']['initial'])
    exact(mapping['scenario_id'],sid,'Incumbent scenario mapping');exact(mapping['original_input_row'],row,'Full original input evidence');exact(mapping['input_reference'],case['input_reference'],'Input source mapping');pathid=event['decision_date']+'|'+event['amount_usd'];exact(mapping['path_id'],pathid,'Same-flow path identity')
    signature=fingerprint(dict(account=inc['account'],reference=inc['account_reference']))
    if pathid in incumbent_groups:exact(incumbent_groups[pathid]['signature'],signature,'Same incumbent path across four lanes')
    else:incumbent_groups[pathid]=dict(signature=signature,lanes=[])
    incumbent_groups[pathid]['lanes'].append(row['lane'])
    days=[d['session']for d in zero['account']['rows']];calendar=[initial['session']]+days
    require(len(days)==lengths[clock] and days[0]==event['execution_date'] and days[-1]=='2023-09-01' and calendar==sorted(set(calendar)),'Exact complete saved horizon')
    exact(case['calendar'],calendar,'Explicit original calendar');reference(case['calendar_reference'])
    for day in calendar:metrics_core.day(day)
    validate_buy_only_inputs(zero,calendar)
    nav=case['nav_rows'];evidence_reference(case['nav_evidence_reference']);require(type(nav)is list and [v['session']for v in nav]==calendar,'Full NAV window, no dropped day')
    raw=[];lags=[];previous=None;dated={}
    for item in nav:
        reference(item['reference']);navdate=metrics_core.day(item['nav_date']);require(navdate<=item['session'] and (previous is None or navdate>=previous),'No future NAV fill or date reversal');n=number(item['value']);require(n>0,'Positive NAV');require(navdate not in dated or dated[navdate]==n,'One NAV observation value per date');dated[navdate]=n;previous=navdate;raw.append(n);lags.append(dict(session=item['session'],nav_date=navdate,calendar_day_lag=(date.fromisoformat(item['session'])-date.fromisoformat(navdate)).days,publication_time=None,publication_time_verified=False,source_reference=deepcopy(item['reference'])))
    saved=case['saved_reference_metrics'];require(set(saved)=={'same_flow_zero_trade_control','same_flow_incumbent','fund_012922_cny_nav_reference'},'Exact three reused reference metrics');measured={'same_flow_zero_trade_control':path_metrics(zero['account'],calendar,event,zero_trade=True,saved_metrics=saved['same_flow_zero_trade_control']),'same_flow_incumbent':path_metrics(inc['account'],calendar,event,signed=True,saved_metrics=saved['same_flow_incumbent']),'fund_012922_cny_nav_reference':saved_metric(saved['fund_012922_cny_nav_reference'],calendar,[v/raw[0]for v in raw])}
    status=candidate['status'];require(status in AVAILABLE+ABSENT,'Explicit candidate state');evidence_reference(candidate['evidence_reference']);absent=status in ABSENT
    if absent:
        require(type(candidate['reason'])is str and candidate['reason'].strip(),'Explicit absence reason')
        for k in ('account','account_reference','accounting_inputs','inputs_reference','account_inspection','inspection_reference'):require(candidate[k]is None,'Missing path is not cash')
        measured['candidate']=None
    else:
        require(candidate['reason']is None,'No hidden absence');reference(candidate['account_reference']);reference(candidate['inputs_reference']);initial_equal(initial,candidate['accounting_inputs']['initial']);require(number(candidate['accounting_inputs']['transaction_cost_bps'])==10,'Candidate fee evidence');require([s['session']for s in candidate['accounting_inputs']['sessions']]==days,'Candidate saved inputs calendar');measured['candidate']=signed_candidate_metrics(candidate,calendar,event)
    for role,result in measured.items():
        if result is not None:result.update(currency_label='CNY'if role=='fund_012922_cny_nav_reference'else 'USD',currency_label_is_saved_conditional_assumption=True,uses_saved_chained_twr=role!='fund_012922_cny_nav_reference',formal_admission_allowed=False)
    navmetrics=measured['fund_012922_cny_nav_reference'];distances={}
    for role in ('candidate','same_flow_incumbent','same_flow_zero_trade_control'):
        metric=measured[role]
        if metric is None:distances[role]=None;continue
        with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
            annual=abs(Decimal(metric['annualized_return_diagnostic_decimal'])-Decimal(navmetrics['annualized_return_diagnostic_decimal']))
        distances[role]=dict(annualized_return_absolute_distance_diagnostic_decimal=str(annual),maximum_drawdown_absolute_distance=ratio(abs(value(metric['maximum_drawdown'])-value(navmetrics['maximum_drawdown']))),currency_scope='NORMALIZED_ORIGINAL_CURRENCY_DIAGNOSTIC_NOT_USD_EQUIVALENT_NAV',formal_gate=False)
    comparisons=None if absent else {role:differences(measured['candidate'],measured[role])for role in ('same_flow_incumbent','same_flow_zero_trade_control','fund_012922_cny_nav_reference')}
    relative=None
    if not absent:
        with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
            delta=Decimal(distances['candidate']['annualized_return_absolute_distance_diagnostic_decimal'])-Decimal(distances['same_flow_incumbent']['annualized_return_absolute_distance_diagnostic_decimal'])
        relative=dict(annualized_absolute_distance_difference_diagnostic_decimal=str(delta),maximum_drawdown_absolute_distance_difference=ratio(value(distances['candidate']['maximum_drawdown_absolute_distance'])-value(distances['same_flow_incumbent']['maximum_drawdown_absolute_distance'])),formal_noninferiority=False)
    return dict(scenario_index=index,scenario_id=sid,candidate_status=status,candidate_absence_reason=candidate['reason'],calendar=calendar,metrics=measured,candidate_minus_references=comparisons,nav_absolute_distance_diagnostics=distances,candidate_minus_incumbent_nav_distance=relative,nav_observation_lags=lags,original_case_evidence=deepcopy(case),policy_asymmetry=POLICY_ASYMMETRY,nav_currency='CNY',saved_reference_metrics_recomputed=False,nav_is_same_flow_executable_account=False,short_and_unequal_windows_not_aggregated=True,**FLAGS)


def compare_selected_single_replacement_paths(*,cases,expected_scenario_ids):
    with localcontext(Context(prec=160,rounding=ROUND_HALF_EVEN)):
        require(type(cases)is list and len(cases)==40 and type(expected_scenario_ids)is list and len(expected_scenario_ids)==len(set(expected_scenario_ids))==40,'Full ordered forty cases')
        rows=[];coordinates=set();groups={};counts={k:0 for k in AVAILABLE+ABSENT}
        for i,case in enumerate(cases):
            exact(case['scenario_id'],expected_scenario_ids[i],'Original scenario order');e=case['input_row']['cash_event'];coordinates.add((case['input_row']['lane'],e['decision_date'],e['execution_date'],e['amount_usd']));result=compare_case(case,i,groups);counts[result['candidate_status']]+=1;rows.append(result)
        require(coordinates=={(lane,d,e,a)for lane in LANES for d,e,_ in CLOCKS for a in ('1000','10000')},'All forty original coordinates')
        require(len(groups)==10 and all(sorted(v['lanes'])==sorted(LANES)for v in groups.values()),'Exactly ten shared incumbent paths across four lanes')
        return dict(schema='SINGLE_REPLACEMENT_SIGNED_REFERENCE_COMPARISON_V1',scenario_count=40,rows=rows,candidate_status_counts=counts,incumbent_path_count=10,reference_metrics_dependency_sha256=METRICS_SOURCE_SHA256,source_scope='CALLER_SUPPLIED_SAVED_PATHS_AND_REFERENCES_NOT_BYTE_AUTHENTICATION',annualization_is_historical_diagnostic=True,policy_asymmetry=POLICY_ASYMMETRY,formal_cohort_statistics_computed=False,technical_statuses_are_caller_declarations=True,actual_failed_source_chain_supported=False,candidate_reuse_supported=False,**FLAGS)
