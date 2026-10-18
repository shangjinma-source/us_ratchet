"""Pure saved-path comparison; no account simulation, selection or source reads."""
from copy import deepcopy
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from datetime import date
import math
from backtest import ndx_cash_fork_reference_window_research as window

SCHEMA='FIRST_PERIOD_EIGHT_SAME_FLOW_NAV_REFERENCE_COMPARISON_V1'
REFERENCE_METRICS_SOURCE_SHA256='0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163'
LANES=('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE')
FLAGS=dict.fromkeys(('formal_dual_benchmark_admission','point_in_time_verified','promotion_allowed','orders_executed',
    'economic_winner_selected','cross_window_ranking_performed','win_rate_calculated','account_simulation_called',
    'saved_candidates_reselected','source_bytes_authenticated_by_this_pure_module','full_transitive_source_closure_reverified',
    'historical_price_identity_certified','fx_equivalence_verified','total_return_claimed',
    'candidate_decision_time_executability_verified','decision_information_sets_equivalent',
    'execution_policies_equivalent','executable_strategy_advantage_claimed','nav_publication_time_verified','nav_dataset_currency_binding_certified','subscription_execution_equivalence_verified'),False)
POLICY_ASYMMETRY={
    'candidate_quantity_information':'HISTORICAL_CONDITIONAL_SEARCH_USING_EXECUTION_OPEN_PRICES',
    'incumbent_quantity_information':'PRIOR_DECISION_CLOSE_FROZEN_NO_OPEN_REPLAN',
    'candidate_later_policy':'ONE_OFF_TOPUP_THEN_FIXED_HOLDINGS',
    'incumbent_later_policy':'ORIGINAL_SCHEDULE_REBALANCES_USING_COUNTERFACTUAL_OWN_STATE',
    'scope':'MATCHED_INITIAL_STATE_AND_FLOW_DO_NOT_CERTIFY_MATCHED_INFORMATION_OR_EXECUTABLE_ADVANTAGE'}


def require(ok,message):
    if not ok: raise ValueError(message)


def reference(value):
    require(type(value) is dict and set(value)=={'path','sha256'} and type(value['path']) is str and value['path']
            and type(value['sha256']) is str and len(value['sha256'])==64
            and all(char in '0123456789abcdef' for char in value['sha256']),'Caller-bound path/SHA reference required')
    return value


def pointer(ref,path): return dict(ref,json_pointer=path)


def initial_equal(left,right):
    keys={'session','cash_usd','holdings','close_prices'}
    require(type(left) is dict and type(right) is dict and set(left)==set(right)==keys,'Exact initial state contract')
    require(left['session']==right['session'] and left['holdings']==right['holdings'],'Identical initial session and whole holdings required')
    require(all(type(q) is int and q>=0 for q in left['holdings'].values())
            and all(type(q) is int and q>=0 for q in right['holdings'].values()),'Whole initial shares required')
    require(left['session']=='2023-03-31' and left['holdings']==right['holdings']=={} and left['close_prices']=={} and len(right['close_prices'])==8,'Empty shares; incumbent eight Close marks are plan inputs only')
    require(window.number(left['cash_usd'])==window.number(right['cash_usd'])==25000,'Equal nonnegative initial cash required')
    require(all(window.number(left['close_prices'][sid])==window.number(right['close_prices'][sid])>0
                for sid in left['holdings']),'Equal conditional initial Close values required')



def nav_reference(document,ref):
    require(document['schema']=='RETURN_SIX_PERIOD_REUSED_BENCHMARK_PREFIX_V1','Saved 2023 benchmark schema')
    for flag in ('point_in_time_verified','promotion_allowed','formal_dual_benchmark_admission','execution_rerun'):
        require(document[flag] is False,'Benchmark saved limitations')
    calendar=document['calendar']; nav=document['nav']; rows=nav['rows']
    require(len(calendar)==107 and calendar==sorted(set(calendar)) and calendar[0]=='2023-03-31' and calendar[1]=='2023-04-03' and calendar[-1]=='2023-09-01','Exact first-period calendar')
    for day in calendar:window.day(day)
    require([r['session'] for r in rows]==calendar,'NAV full same calendar')
    require(nav['role']=='012922_NATIVE_CURRENCY_RETROSPECTIVE_NAV','NAV role')
    for flag in ('publication_time_verified','currency_fx_equivalence_verified','subscription_redemption_fee_equivalence_verified'):
        require(nav[flag] is False,'NAV limitations preserved')
    values=[]; dated={}; previous=None; observations=[]
    for i,row in enumerate(rows):
        require(type(row['nav']) is float and math.isfinite(row['nav']) and row['nav']>0,'Saved finite positive float NAV')
        n=window.number(str(row['nav'])); day=window.day(row['nav_date'])
        require(day<=row['session'] and (previous is None or previous<=day),'Backward NAV date only')
        require(day not in dated or dated[day]==n,'One dated NAV value')
        dated[day]=n;previous=day;values.append(n)
        observations.append(dict(reference=pointer(ref,f'/nav/rows/{i}'),source_row=deepcopy(row),decimal_literal=str(row['nav']),encoding='SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE',calendar_day_lag=(date.fromisoformat(row['session'])-date.fromisoformat(day)).days,publication_time=None))
    return dict(calendar=deepcopy(calendar),metrics=window.metrics(calendar,[v/values[0] for v in values]),observations=observations,metadata={k:deepcopy(v) for k,v in nav.items() if k!='rows'},currency_label='CNY_CONDITIONAL_CURRENT_ISSUER_LABEL_NOT_HISTORICAL_CLASS_CERTIFICATION',fx_conversion_performed=False,nav_source_reexecuted=False,formal_admission_allowed=False)


def nav_distances(measured,nav):
    out={}
    for role,m in measured.items():
        out[role]={key:window.ratio(abs(window.from_ratio(m[key])-window.from_ratio(nav[key]))) for key in ('cumulative_return','maximum_drawdown')}
        with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
            out[role]['annualized_return_diagnostic_decimal']=str(abs(Decimal(m['annualized_return_diagnostic_decimal'])-Decimal(nav['annualized_return_diagnostic_decimal'])))
    delta={key:window.ratio(window.from_ratio(out['candidate'][key])-window.from_ratio(out['same_flow_incumbent'][key])) for key in ('cumulative_return','maximum_drawdown')}
    with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
        delta['annualized_return_diagnostic_decimal']=str(Decimal(out['candidate']['annualized_return_diagnostic_decimal'])-Decimal(out['same_flow_incumbent']['annualized_return_diagnostic_decimal']))
    return dict(absolute_distances=out,candidate_minus_incumbent_absolute_distance=delta,negative_difference_means_smaller_distance=True,currency_equivalence_verified=False,scope='EX_POST_NATIVE_NAV_VS_USD_PATH_DIAGNOSTIC_NOT_FX_NEUTRAL_OR_EXECUTABLE_BENCHMARK_GATE')

def compare_first_period_paths(*,candidate_accounts,incumbent_accounts,benchmark_document,candidate_reference,incumbent_reference,benchmark_reference):
    paired_accounts=candidate_accounts; paired_reference=candidate_reference
    reference(paired_reference); reference(incumbent_reference); reference(benchmark_reference)
    require(paired_accounts['schema']=='FIRST_PERIOD_CASH_FIXED_BUY_HOLD_PRICE_ONLY_TWR_V1'
            and type(paired_accounts['scenario_count']) is int and paired_accounts['scenario_count']==8
            and len(paired_accounts['rows'])==8,'Eight candidate scenarios required')
    require(incumbent_accounts['schema']=='FIRST_PERIOD_INCUMBENT_TWO_PATHS_EIGHT_SCENARIOS_V2'
            and type(incumbent_accounts['path_count']) is int and incumbent_accounts['path_count']==2
            and type(incumbent_accounts['scenario_count']) is int and incumbent_accounts['scenario_count']==8
            and len(incumbent_accounts['paths'])==2 and len(incumbent_accounts['scenario_mappings'])==8,'Two explicit paths/four-lane mapping required')
    nav=nav_reference(benchmark_document,benchmark_reference)
    require(candidate_accounts['observed_calendar']==nav['calendar'],'Exact 107 observed dates, no shorter substitute')
    for document in (paired_accounts,incumbent_accounts):
        for key in ('orders_executed','point_in_time_verified','promotion_allowed'):
            require(document[key] is False,'Input authority cannot upgrade')
    require(incumbent_accounts['flow_policy']=='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN'
            and incumbent_accounts['risk_is_order_gate'] is False,'Actual incumbent flow/order contract required')
    paths={}; mappings={}
    for index,path in enumerate(incumbent_accounts['paths']):
        require(path['path_id'] not in paths,'Duplicate incumbent path')
        paths[path['path_id']]=(index,path)
    for index,mapping in enumerate(incumbent_accounts['scenario_mappings']):
        require(mapping['scenario_id'] not in mappings and mapping['path_id'] in paths,'Unique valid scenario mapping required')
        mappings[mapping['scenario_id']]=(index,mapping)
    candidate_ids=[row['scenario_id'] for row in paired_accounts['rows']]
    require(len(set(candidate_ids))==8 and set(candidate_ids)==set(mappings),'Exact candidate-to-incumbent mapping required')
    groups={key:[] for key in paths}; rows=[]; coordinates=set()
    for candidate_index,paired in enumerate(paired_accounts['rows']):
        scenario=paired['scenario_id']; mapping_index,mapping=mappings[scenario]
        input_row=paired['input_row']; event=input_row['cash_event']
        require(mapping['original_input_row']==input_row and mapping['input_reference']==paired['input_reference']
                and input_row['scenario_id']==scenario,'Full original scenario evidence/reference differs')
        coordinate=(input_row['lane'],event['decision_date'],event['execution_date'],event['amount_usd'])
        require(input_row['lane'] in LANES and event['amount_usd'] in ('1000','10000') and coordinate not in coordinates,'Unique bounded lane/date/amount scenario required')
        coordinates.add(coordinate)
        path_id=mapping['path_id']; require(path_id==event['decision_date']+'|'+event['amount_usd'],'Mapping flow coordinate differs')
        groups[path_id].append(coordinate)
        path_index,incumbent=paths[path_id]; inc=incumbent['account']; candidate=paired
        require(inc['schema']=='SIGNED_FLOW_FROZEN_INCUMBENT_OPEN_ACCOUNT_V1'
                and candidate['account']['schema']=='BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1','Saved account schemas differ')
        require(inc['flow_policy']=='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN' and inc['risk_is_order_gate'] is False,'Incumbent policy differs')
        initial=candidate['accounting_inputs']['initial']; initial_equal(initial,inc['initial'])
        require(window.number(candidate['accounting_inputs']['transaction_cost_bps'])==window.number(inc['transaction_cost_bps'])
                ==window.number(input_row['transaction_cost_bps']),'Same original fee rate required')
        require(initial['session']==event['decision_date'],'Initial clock differs from scenario')
        candidate_daily=candidate['account']['rows']; incumbent_daily=inc['daily']
        days=[item['session'] for item in candidate_daily]; other_days=[item['session'] for item in incumbent_daily]
        require(days==other_days and len(days)==106 and days[-1]=='2023-09-01' and days[0]==event['execution_date'],'Exact daily calendar required, no intersection')
        calendar=[window.day(initial['session'])]+[window.day(day) for day in days]
        require(calendar==nav['calendar'],'Full benchmark calendar must match both paths')
        require(mapping['candidate_account_reference']==pointer(paired_reference,f'/rows/{candidate_index}'),'Exact mapped candidate reference')
        require(all(window.number(v)>0 for v in inc['initial']['close_prices'].values()),'Positive planning marks')
        require(calendar==sorted(set(calendar)),'Strict initial and observed calendar required')
        for index,(left,right) in enumerate(zip(candidate_daily,incumbent_daily)):
            expected=window.number(event['amount_usd']) if index==0 else Fraction(0)
            require(window.number(left['cash_injection_usd'])==window.number(right['cash_injection_usd'])==expected,'Identical once-only injection required')
        require(candidate['account']['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES'
                and inc['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES','Flow boundary differs')
        for account in (candidate['account'],inc):
            for flag in ('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled'):
                require(account[flag] is False,'Saved account authority differs')
            require(window.number(account['total_cash_injection_usd'])==window.number(event['amount_usd']),'Aggregate flow differs')
        require(window.from_ratio(candidate['account']['chained_twr'])==window.from_ratio(candidate_daily[-1]['cumulative_twr'])
                and window.from_ratio(inc['chained_twr'])==window.from_ratio(incumbent_daily[-1]['cumulative_twr']),'Terminal TWR summary differs')
        measured={}; observations={}
        for role,daily,ref,base in [('candidate',candidate_daily,paired_reference,f'/rows/{candidate_index}/account/rows'),
                                  ('same_flow_incumbent',incumbent_daily,incumbent_reference,f'/paths/{path_index}/account/daily')]:
            wealth=[Fraction(1)]+[1+window.from_ratio(item['cumulative_twr']) for item in daily]
            measured[role]=window.metrics(calendar,wealth)
            observations[role]=[{'reference':pointer(ref,f'{base}/{j}'),'source_row':deepcopy(item)} for j,item in enumerate(daily)]
        with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
            annual_difference=Decimal(measured['candidate']['annualized_return_diagnostic_decimal'])-Decimal(measured['same_flow_incumbent']['annualized_return_diagnostic_decimal'])
        rows.append({'scenario_id':scenario,'input_row':deepcopy(input_row),'original_input_reference':deepcopy(paired['input_reference']),
            'candidate_paired_row_reference':pointer(paired_reference,f'/rows/{candidate_index}'),
            'incumbent_path_reference':pointer(incumbent_reference,f'/paths/{path_index}'),
            'incumbent_mapping_reference':pointer(incumbent_reference,f'/scenario_mappings/{mapping_index}'),
            'incumbent_mapping_preserved':deepcopy(mapping),'candidate_selected_plan_reference':deepcopy(paired['selected_plan_reference']),
            'candidate_saved_selection':deepcopy(paired['saved_selection']),
            'candidate_selection_reference':deepcopy(paired['selection_reference']),
            'candidate_initial_state':deepcopy(initial),'incumbent_initial_state':deepcopy(inc['initial']),
            'calendar':calendar,'metrics':measured,'observations':observations,
            'candidate_minus_incumbent':{'cumulative_return':window.ratio(window.from_ratio(measured['candidate']['cumulative_return'])-window.from_ratio(measured['same_flow_incumbent']['cumulative_return'])),
                'maximum_drawdown':window.ratio(window.from_ratio(measured['candidate']['maximum_drawdown'])-window.from_ratio(measured['same_flow_incumbent']['maximum_drawdown'])),
                'annualized_return_diagnostic_decimal':str(annual_difference),'annual_difference_precision':80,
                'annual_difference_rounding':'ROUND_HALF_EVEN','annual_difference_is_historical_diagnostic':True},
            'same_initial_state_verified_within_supplied_documents':True,'initial_state_scope':'EQUAL_EMPTY_HOLDINGS_AND_25000_CASH_INCUMBENT_EIGHT_CLOSE_MARKS_PLAN_ONLY','same_flow_timing_and_amount_verified_within_supplied_documents':True,
            'currency_scope':'USD_CONDITIONAL_SAVED_PATHS_NOT_NEW_PRICE_IDENTITY_OR_FX_CERTIFICATION',
            'policy_asymmetry':deepcopy(POLICY_ASYMMETRY),'fund_nav_reference':pointer(benchmark_reference,'/nav'),
            'nav_distances':nav_distances(measured,nav['metrics']),**FLAGS})
    dates=set()
    for path_id,group in groups.items():
        require(len(group)==4 and {coord[0] for coord in group}==set(LANES)
                and len({coord[1:] for coord in group})==1,'Every incumbent path must cover four exactly matched lanes')
        dates.add(group[0][1:3])
    require(dates=={('2023-03-31','2023-04-03')} and coordinates=={(lane,decision,execution,amount) for lane in LANES for decision,execution in dates for amount in ('1000','10000')},'One full date by two amounts by four lanes required')
    return {'schema':SCHEMA,'rows':rows,'scenario_count':8,'incumbent_path_count':2,
        'input_references':{'candidate_accounts':deepcopy(paired_reference),'incumbent_accounts':deepcopy(incumbent_reference),'benchmark':deepcopy(benchmark_reference)},
        'nav_reference':nav,
        'cohort_statistics_computed':False,'future_return_selection_feedback':False,
        'reference_metrics_dependency_sha256':REFERENCE_METRICS_SOURCE_SHA256,
        'comparison_scope':'SAME_INITIAL_STATE_SAME_FLOW_CONDITIONAL_USD_PATHS_DISTINCT_RESEARCH_POLICIES',
        'annualized_return_calculated':True,'annualization_is_historical_diagnostic':True,
        'short_and_unequal_windows_not_aggregated':True,'wealth_arithmetic':'SAVED_CUMULATIVE_TWR_PLUS_ONE_NOT_ACCOUNT_EQUITY_RATIO',
        'policy_asymmetry':deepcopy(POLICY_ASYMMETRY),**FLAGS}
