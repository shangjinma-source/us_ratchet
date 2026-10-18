"""Independent saved comparison arithmetic inspection; no producer imports or IO.

Input case references must be externally authenticated by a future source reader.
Reference metrics are copied, not recomputed; candidate annualization has an
independent Decimal110 ln/exp check against the saved Decimal80 diagnostic.
"""
import json, hashlib
from copy import deepcopy
from datetime import date
from decimal import Decimal, Context, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

ROLES=('same_flow_zero_trade_control','same_flow_incumbent','fund_012922_cny_nav_reference')
STATUSES=('AVAILABLE_NEW_SIGNED','NO_FEASIBLE','BLOCKED_TEMPLATE_PRICE_GAP','TECHNICAL_FAILURE','UNDISPATCHED','UNRESOLVED_DISPATCH')
CLOCKS=(('2023-04-28','2023-05-01',87),('2023-05-31','2023-06-01',65),('2023-06-30','2023-07-03',44),('2023-07-31','2023-08-01',24),('2023-08-31','2023-09-01',1))
LANES=('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE')
FLAGS=('source_bytes_authenticated','account_executed','controls_executed','selection_reexecuted','risk_recomputed','fit_performed','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','formal_dual_benchmark_admission','economic_winner_selected','cross_window_ranking_performed','currency_fx_equivalence_verified','nav_dataset_currency_binding_certified','nav_publication_time_verified','candidate_decision_time_executability_verified')
ASYMMETRY='CANDIDATE_DOUBLE_REPLACEMENT_SIGNED_OPEN_BASKET_BOTH_SIDE_FEES_THEN_HOLD;INCUMBENT_PRIOR_CLOSE_FREEZE_AND_LATER_MONTHLY_REBALANCE;SAME_FLOW_DOES_NOT_PROVE_SAME_INFORMATION_OR_EXECUTABILITY'

def require(ok,msg):
 if not ok:raise ValueError(msg)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):require(encode(a)==encode(b),'Exact saved field/type mismatch')
def integer(v,n):require(type(v)is int and v==n,'Exact integer')
def decimal(v):
 require(type(v)in (str,int,Decimal),'No float/bool number');d=Decimal(v);require(d.is_finite(),'Finite value');return d
def number(v):return Fraction(decimal(v))
def frac(v):
 require(type(v)is dict and set(v)=={'numerator','denominator'}and all(type(x)is str for x in v.values()),'Exact fraction object')
 require(int(v['denominator'])>0,'Positive denominator');return Fraction(int(v['numerator']),int(v['denominator']))
def ratio(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def flags(v):
 for k in FLAGS:require(v[k]is False,'Authority '+k)
def ref(v,evidence=False):
 require(type(v)is dict,'Reference object');require(type(v['path'])is str and v['path']and v['path'].strip()==v['path'],'Reference path');h=v['sha256'];require(type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'Reference SHA')
 if evidence and set(v)=={'path','sha256','document_scope'}:require(v['path'].lower().endswith('.md')and v['document_scope']=='WHOLE_MARKDOWN_REPORT','Explicit Markdown evidence')
 else:require(set(v)=={'path','sha256','json_pointer'}and type(v['json_pointer'])is str and v['json_pointer'].startswith('/'),'Object pointer')
def enriched(v,role):
 out=deepcopy(v);out.update(currency_label='CNY'if role==ROLES[2]else 'USD',currency_label_is_saved_conditional_assumption=True,uses_saved_chained_twr=role!=ROLES[2],formal_admission_allowed=False);return out
def metrics_shape(m,calendar,wealth):
 integer(m['observation_count'],len(calendar));integer(m['interval_count'],len(calendar)-1)
 exact(m['wealth'],[dict(session=d,normalized_wealth=ratio(v))for d,v in zip(calendar,wealth)])
 require(all(v>0 for v in wealth),'Positive saved wealth');exact(m['cumulative_return'],ratio(wealth[-1]-1));require(m['initial_one_in_drawdown']is True and m['annualized_return_calculated']is True,'Initial/annual flags')
 require(0<=frac(m['maximum_drawdown'])<1,'Saved DD');decimal(m['annualized_return_diagnostic_decimal'])
 integer(m['annualization']['interval_count'],len(calendar)-1);require(m['annualization']['formal_admission_allowed']is False and m['annualization']['annualization_is_historical_diagnostic']is True,'Saved diagnostic scope')
def candidate_metrics(m,calendar,wealth):
 exact(sorted(m),sorted(('observation_count','interval_count','cumulative_return','maximum_drawdown','wealth','initial_one_in_drawdown','annualized_return_calculated','annualized_return_diagnostic_decimal','annualization','currency_label','currency_label_is_saved_conditional_assumption','uses_saved_chained_twr','formal_admission_allowed')))
 metrics_shape(m,calendar,wealth)
 # Independent all earlier/later pairs, deliberately different from peak scan.
 drawdown=max(Fraction(0),max(1-wealth[j]/wealth[i]for j in range(len(wealth))for i in range(j+1)))
 exact(m['maximum_drawdown'],ratio(drawdown));n=len(calendar)-1
 with localcontext(Context(prec=110,rounding=ROUND_HALF_EVEN)):
  terminal=Decimal(wealth[-1].numerator)/Decimal(wealth[-1].denominator)
  annual=(terminal.ln()*Decimal(252)/Decimal(n)).exp()-1
  saved=decimal(m['annualized_return_diagnostic_decimal']);require(abs(saved-annual)<=Decimal('1e-70')*max(Decimal(1),abs(annual)),'Independent annualization')
 exact(m['annualization'],dict(formula='terminal_normalized_wealth ** (252 / interval_count) - 1',sessions_per_year=252,interval_count=n,decimal_precision=80,rounding='ROUND_HALF_EVEN',arithmetic='DECIMAL80_POWER_FROM_EXACT_TERMINAL_FRACTION_NOT_EXACT_RATIONAL_ANNUALIZATION',annualization_is_historical_diagnostic=True,short_window_below_252_intervals=n<252,short_window_limitation='SHORT_WINDOW_COMPOUNDING_CAN_MAGNIFY_SMALL_MOVES_NOT_LONG_TERM_EVIDENCE',formal_admission_allowed=False))
 for k,v in enriched({},'candidate').items():exact(m[k],v)
def daily(e,calendar,event,signed=False,zero=False):
 a=e['account'];rows=a['daily'if signed else 'rows'];exact([r['session']for r in rows],calendar[1:]);require(number(a['transaction_cost_bps'])==10 and number(a['total_cash_injection_usd'])==number(event['amount_usd']),'Fee/flow')
 exact(a['schema'],'SIGNED_FLOW_FROZEN_INCUMBENT_OPEN_ACCOUNT_V1'if signed else 'BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1')
 exact(a['cash_event_timing'],'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES'if signed else 'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES')
 for k in ('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled'):require(a[k]is False,'Account scope')
 if signed:require(a['flow_policy']=='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN'and a['risk_is_order_gate']is False,'Incumbent policy')
 else:
  inputs=e['accounting_inputs'];require(number(inputs['transaction_cost_bps'])==10,'Input fee');exact([v['session']for v in inputs['sessions']],calendar[1:]);exact(rows[0]['holdings_before'],inputs['initial']['holdings'])
 for i,r in enumerate(rows):
  require(number(r['cash_injection_usd'])==(number(event['amount_usd'])if i==0 else 0),'Once-only flow')
  if not signed:
   inp=inputs['sessions'][i];exact(inp['buy_shares'],r['buy_shares']);require(number(inp['cash_injection_usd'])==number(r['cash_injection_usd']),'Saved input flow')
  if zero:exact(r['buy_shares'],{});require(number(r['fees_usd'])==number(r['gross_buy_usd'])==0,'Zero trade role')
 exact(a['chained_twr'],rows[-1]['cumulative_twr']);return [Fraction(1)]+[1+frac(r['cumulative_twr'])for r in rows]
def same_initial(a,b):
 exact(sorted(a),['cash_usd','close_prices','holdings','session']);exact(sorted(b),sorted(a));exact(a['session'],b['session']);exact(a['holdings'],b['holdings']);require(all(type(x)is int and x>=0 for x in a['holdings'].values()),'Exact shares')
 require(number(a['cash_usd'])==number(b['cash_usd'])>=0,'Initial cash');exact(sorted(a['close_prices']),sorted(a['holdings']));exact(sorted(b['close_prices']),sorted(a['holdings']))
 for sid in a['holdings']:require(number(a['close_prices'][sid])==number(b['close_prices'][sid])>0,'Initial prices')

def signed_wealth(envelope, calendar, event):
 """Independent signed-context validation; no ledger or producer calls.

 The prior report hash binds result bytes, not request/source authenticity.
 Cash ledger replay remains that external inspection's separate scope.
 """
 args=envelope['accounting_inputs']; account=envelope['account']; audit=envelope['account_inspection']
 ref(envelope['inspection_reference'])
 exact(account['schema'],'SIGNED_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1')
 exact(account['cash_event_timing'],'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_BASKET_AND_BOTH_SIDE_FEES')
 exact(account['execution_assumption'],'SAME_OPEN_NET_CASH_SETTLEMENT_SELL_PROCEEDS_AVAILABLE_FOR_BUYS')
 for key in ('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled','broker_settlement_or_intraday_ordering_verified','single_replacement_action_semantics_verified','cash_buffer_and_risk_gates_evaluated'):
  require(account[key]is False,'Signed account authority')
 exact(audit['schema'],'SIGNED_CASH_FLOW_ACCOUNT_INDEPENDENT_INSPECTION_V1');exact(audit['status'],'PASS')
 exact(audit['scope'],'EXPLICIT_SIGNED_WHOLE_SHARE_ACCOUNTING_ONLY_NOT_ACTION_POLICY_OR_SOURCE_AUTHENTICATION')
 for key in ('source_bytes_authenticated','producer_called','producer_helpers_called','account_executed','orders_executed','fit_executed','risk_evaluated','action_family_verified','exchange_session_adjacency_verified','broker_settlement_verified','point_in_time_verified','promotion_allowed'):
  require(audit[key]is False,'Signed inspection scope')
 require(audit['all_saved_rows_and_fields_checked']is True,'Complete prior inspection')
 exact(audit['saved_result_content_sha256'],hashlib.sha256(encode(account)).hexdigest())
 integer(audit['session_count'],len(calendar)-1);exact(audit['initial_session'],calendar[0]);exact(audit['terminal_session'],calendar[-1])
 require(number(args['transaction_cost_bps'])==number(account['transaction_cost_bps'])==10,'Signed fees')
 sessions=args['sessions']; rows=account['rows']
 require(type(sessions)is list and type(rows)is list,'Signed row lists')
 exact([r['session']for r in sessions],calendar[1:]);exact([r['session']for r in rows],calendar[1:])
 initial=args['initial'];exact(rows[0]['holdings_before'],initial['holdings']);exact(rows[0]['previous_close_session'],calendar[0])
 capital=number(initial['cash_usd'])+sum((q*number(initial['close_prices'][sid])for sid,q in initial['holdings'].items()),Fraction())
 require(capital>0 and capital==number(account['initial_equity_usd'])==number(rows[0]['previous_close_equity_usd']),'Original capital')
 universe=set(initial['holdings'])|set(sessions[0]['trade_shares']); total_fee=Fraction()
 for i,(source,saved)in enumerate(zip(sessions,rows)):
  exact(sorted(source),sorted(('session','open_prices','close_prices','cash_injection_usd','trade_shares')))
  trades=source['trade_shares'];require(type(trades)is dict and all(type(q)is int for q in trades.values()),'Signed integer legs')
  exact(trades,saved['trade_shares'])
  require(set(source['open_prices'])==set(source['close_prices'])==universe,'Full price union')
  if i==0:
   require(set(trades)==universe,'Zero share keys retained')
   outgoing=[sid for sid,q in trades.items()if q<0];incoming=[sid for sid,q in trades.items()if q>0]
   require(len(outgoing)==len(incoming)==2,'Two negative and two positive legs')
   require(set(outgoing).isdisjoint(incoming) and all(trades[sid]==-initial['holdings'][sid] for sid in outgoing) and all(initial['holdings'].get(sid,0)==0 for sid in incoming),'Two full outgoing and two new incoming')
  else:exact(trades,{})
  flow=number(event['amount_usd'])if i==0 else Fraction()
  require(number(source['cash_injection_usd'])==number(saved['cash_injection_usd'])==flow,'Single initial injection')
  buys=sells=Fraction()
  for sid in universe:
   price=number(source['open_prices'][sid]);require(price>0 and number(source['close_prices'][sid])>0,'Positive price')
   quantity=trades.get(sid,0)
   buys+=max(quantity,0)*price;sells+=max(-quantity,0)*price
  fee=(buys+sells)/1000
  require(number(saved['gross_buy_usd'])==buys and number(saved['gross_sell_usd'])==sells and number(saved['fees_usd'])==fee,'Signed gross amounts and both fees')
  total_fee+=fee
 require(number(account['total_fees_usd'])==total_fee and number(account['total_cash_injection_usd'])==number(event['amount_usd']),'Signed totals')
 exact(account['chained_twr'],rows[-1]['cumulative_twr'])
 return [Fraction(1)]+[1+frac(r['cumulative_twr'])for r in rows]

def inspect_case(*,case,comparison_row,scenario_index):
 with localcontext(Context(prec=160,rounding=ROUND_HALF_EVEN)):
  row=comparison_row;exact(sorted(row),sorted(('scenario_index','scenario_id','candidate_status','candidate_absence_reason','calendar','metrics','candidate_minus_references','nav_absolute_distance_diagnostics','candidate_minus_incumbent_nav_distance','nav_observation_lags','original_case_evidence','policy_asymmetry','nav_currency','saved_reference_metrics_recomputed','nav_is_same_flow_executable_account','short_and_unequal_windows_not_aggregated')+FLAGS));integer(row['scenario_index'],scenario_index);exact(row['scenario_id'],case['scenario_id']);exact(row['original_case_evidence'],case);flags(row)
  inputs=case['input_row'];event=inputs['cash_event'];exact(inputs['scenario_id'],case['scenario_id']);require(inputs['lane']in LANES and event['amount_usd']in ('1000','10000'),'Coordinate');calendar=case['calendar'];exact(row['calendar'],calendar)
  n=dict(((a,b),n)for a,b,n in CLOCKS).get((event['decision_date'],event['execution_date']));require(n is not None,'Frozen window');integer(len(calendar),n+1);exact(calendar[0],event['decision_date']);exact(calendar[1],event['execution_date']);exact(calendar[-1],'2023-09-01');exact(calendar,sorted(set(calendar)))
  for d in calendar:require(type(d)is str and date.fromisoformat(d).isoformat()==d,'Calendar literal')
  for k in ('input_reference','selection_reference','calendar_reference'):ref(case[k])
  require(number(inputs['transaction_cost_bps'])==10,'Original input fee')
  for k in ('orders_executed','point_in_time_verified','promotion_allowed'):require(inputs[k]is False,'Input limits')
  zero,inc,candidate=case['zero_trade_control'],case['incumbent'],case['candidate']
  for e in (zero,inc):ref(e['account_reference']);ref(e['evidence_reference'],True)
  ref(zero['inputs_reference']);ref(inc['mapping_reference']);mapping=inc['mapping'];exact(mapping['scenario_id'],case['scenario_id']);exact(mapping['original_input_row'],inputs);exact(mapping['input_reference'],case['input_reference']);exact(mapping['path_id'],event['decision_date']+'|'+event['amount_usd'])
  initial=zero['accounting_inputs']['initial'];same_initial(initial,inc['account']['initial']);exact(initial['holdings'],inputs['holdings']);exact(initial['session'],calendar[0]);require(number(initial['cash_usd'])==number(inputs['starting_cash_usd']),'Initial input cash')
  wealth={ROLES[0]:daily(zero,calendar,event,zero=True),ROLES[1]:daily(inc,calendar,event,signed=True)}
  ref(case['nav_evidence_reference'],True);exact([v['session']for v in case['nav_rows']],calendar);navvalues=[];lags=[];dates={};prior=''
  for v in case['nav_rows']:
   ref(v['reference']);d=v['nav_date'];require(type(d)is str and date.fromisoformat(d).isoformat()==d and prior<=d<=v['session'],'Backward NAV dates');price=number(v['value']);require(price>0 and (d not in dates or dates[d]==price),'NAV observation identity');dates[d]=price;prior=d;navvalues.append(price)
   lags.append(dict(session=v['session'],nav_date=d,calendar_day_lag=(date.fromisoformat(v['session'])-date.fromisoformat(d)).days,publication_time=None,publication_time_verified=False,source_reference=deepcopy(v['reference'])))
  wealth[ROLES[2]]=[v/navvalues[0]for v in navvalues];exact(row['nav_observation_lags'],lags);exact(sorted(case['saved_reference_metrics']),sorted(ROLES));exact(sorted(row['metrics']),sorted(ROLES+('candidate',)))
  for role in ROLES:
   saved=case['saved_reference_metrics'][role];ref(saved['reference']);ref(saved['evidence_reference'],True);metrics_shape(saved['metrics'],calendar,wealth[role]);exact(row['metrics'][role],enriched(saved['metrics'],role))
  status=candidate['status'];require(status in STATUSES,'Candidate status');exact(row['candidate_status'],status);exact(row['candidate_absence_reason'],candidate['reason']);ref(candidate['evidence_reference'],True);available=status=='AVAILABLE_NEW_SIGNED'
  if available:
   require(candidate['reason']is None,'Available reason');ref(candidate['account_reference']);ref(candidate['inputs_reference']);same_initial(initial,candidate['accounting_inputs']['initial']);w=signed_wealth(candidate,calendar,event);candidate_metrics(row['metrics']['candidate'],calendar,w)
  else:
   require(type(candidate['reason'])is str and candidate['reason'].strip(),'Explicit absent reason')
   for k in ('account','account_reference','accounting_inputs','inputs_reference','account_inspection','inspection_reference'):require(candidate[k]is None,'No invented cash path')
   require(row['metrics']['candidate']is None and row['candidate_minus_references']is None and row['candidate_minus_incumbent_nav_distance']is None,'Absent comparisons')
  measured=row['metrics'];nav=measured[ROLES[2]];distances={}
  with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN)):
   for role in ('candidate',ROLES[1],ROLES[0]):
    metric=measured[role]
    distances[role]=None if metric is None else dict(annualized_return_absolute_distance_diagnostic_decimal=str(abs(decimal(metric['annualized_return_diagnostic_decimal'])-decimal(nav['annualized_return_diagnostic_decimal']))),maximum_drawdown_absolute_distance=ratio(abs(frac(metric['maximum_drawdown'])-frac(nav['maximum_drawdown']))),currency_scope='NORMALIZED_ORIGINAL_CURRENCY_DIAGNOSTIC_NOT_USD_EQUIVALENT_NAV',formal_gate=False)
   exact(row['nav_absolute_distance_diagnostics'],distances)
   if available:
    c=measured['candidate'];diff={}
    for role in (ROLES[1],ROLES[0],ROLES[2]):
     r=measured[role];diff[role]=dict(cumulative_return=ratio(frac(c['cumulative_return'])-frac(r['cumulative_return'])),maximum_drawdown=ratio(frac(c['maximum_drawdown'])-frac(r['maximum_drawdown'])),annualized_return_diagnostic_decimal=str(decimal(c['annualized_return_diagnostic_decimal'])-decimal(r['annualized_return_diagnostic_decimal'])),annual_arithmetic='DECIMAL80_DIFFERENCE_OF_SAVED_DIAGNOSTICS',formal_gate=False)
    exact(row['candidate_minus_references'],diff)
    exact(row['candidate_minus_incumbent_nav_distance'],dict(annualized_absolute_distance_difference_diagnostic_decimal=str(decimal(distances['candidate']['annualized_return_absolute_distance_diagnostic_decimal'])-decimal(distances[ROLES[1]]['annualized_return_absolute_distance_diagnostic_decimal'])),maximum_drawdown_absolute_distance_difference=ratio(frac(distances['candidate']['maximum_drawdown_absolute_distance'])-frac(distances[ROLES[1]]['maximum_drawdown_absolute_distance'])),formal_noninferiority=False))
  exact(row['policy_asymmetry'],ASYMMETRY);exact(row['nav_currency'],'CNY');require(row['saved_reference_metrics_recomputed']is False and row['nav_is_same_flow_executable_account']is False and row['short_and_unequal_windows_not_aggregated']is True,'Reference scope')
  return dict(status='PASS',scenario_index=scenario_index,scenario_id=case['scenario_id'],candidate_status=status,interval_count=n,candidate_metrics_reconstructed=available,reused_reference_metrics_count=3,source_bytes_authenticated=False,formal_dual_benchmark_admission=False)

def inspect_comparison(*,cases,comparison,expected_scenario_ids):
 exact(sorted(comparison),sorted(('schema','scenario_count','rows','candidate_status_counts','incumbent_path_count','reference_metrics_dependency_sha256','source_scope','annualization_is_historical_diagnostic','policy_asymmetry','formal_cohort_statistics_computed','technical_statuses_are_caller_declarations','actual_failed_source_chain_supported','candidate_reuse_supported')+FLAGS))
 require(type(cases)is list and type(expected_scenario_ids)is list,'List inputs');integer(len(cases),40);integer(len(expected_scenario_ids),40);integer(len(set(expected_scenario_ids)),40);integer(comparison['scenario_count'],40);integer(len(comparison['rows']),40);flags(comparison)
 exact(comparison['schema'],'DOUBLE_REPLACEMENT_SIGNED_REFERENCE_COMPARISON_V1');exact(comparison['reference_metrics_dependency_sha256'],'0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163');exact(comparison['policy_asymmetry'],ASYMMETRY);exact(comparison['source_scope'],'CALLER_SUPPLIED_SAVED_PATHS_AND_REFERENCES_NOT_BYTE_AUTHENTICATION');require(comparison['formal_cohort_statistics_computed']is False and comparison['annualization_is_historical_diagnostic']is True,'Global diagnostic scope')
 require(comparison['technical_statuses_are_caller_declarations']is True and comparison['actual_failed_source_chain_supported']is False and comparison['candidate_reuse_supported']is False,'Signed declared scope')
 counts=dict.fromkeys(STATUSES,0);groups={};coordinates=set();out=[]
 for i,(c,r)in enumerate(zip(cases,comparison['rows'])):
  exact(c['scenario_id'],expected_scenario_ids[i]);out.append(inspect_case(case=c,comparison_row=r,scenario_index=i));counts[c['candidate']['status']]+=1;e=c['input_row']['cash_event'];lane=c['input_row']['lane'];coordinates.add((lane,e['decision_date'],e['execution_date'],e['amount_usd']));inc=c['incumbent'];key=inc['mapping']['path_id'];identity=encode(dict(account=inc['account'],reference=inc['account_reference']))
  if key in groups:exact(groups[key][0],identity.hex());groups[key][1].append(lane)
  else:groups[key]=[identity.hex(),[lane]]
 exact(coordinates=={(l,d,e,a)for l in LANES for d,e,_ in CLOCKS for a in ('1000','10000')},True);integer(len(groups),10);integer(comparison['incumbent_path_count'],10)
 for _,lanes in groups.values():exact(sorted(lanes),sorted(LANES))
 exact(comparison['candidate_status_counts'],counts)
 return dict(schema='DOUBLE_REPLACEMENT_SIGNED_COMPARISON_INSPECTION_V1',status='PASS',scenario_count=40,rows=out,candidate_status_counts=counts,old_reference_metrics_recomputed=False,signed_cash_ledger_replayed=False,producer_or_metrics_called=False,source_bytes_authenticated=False,formal_dual_benchmark_admission=False,annual_reference_method='DECIMAL110_LN_EXP_RELATIVE_OR_ABSOLUTE_1E-70')
