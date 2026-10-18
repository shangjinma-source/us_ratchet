"""Independent saved-ledger arithmetic. Never imports an account engine.

Fraction arithmetic replays cash/entitlements and TWR from saved source quotes.
Binary64 ledgers admit explicit USD1e-7, ratio1e-11 rounding budgets. Whole-lot
repair search optimality/completeness is NOT independently enumerated here.
"""
from copy import deepcopy
from fractions import Fraction as F
import hashlib,json,math
USD=F(1,10**7);RATIO=F(1,10**11)
FLAGS=dict.fromkeys(('account_engine_called','fit_called','source_bytes_authenticated','point_in_time_verified','formal_benchmark_passed','promotion_allowed','execution_authorized','integer_repair_search_independently_recomputed','binary64_bitwise_reproduction_claimed'),False)
def require(x,m):
 if not x:raise ValueError(m)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):require(enc(a)==enc(b),m)
def n(v):require(type(v)in(int,float) and math.isfinite(v),'Finite nonboolean saved binary64/int');return F(v)
def near(v,w,ratio=False):require(abs(n(v)-w)<=(RATIO if ratio else USD),'Independent ledger arithmetic mismatch')
def shares_equal(got,want,whole):
 require(set(got)==set(want),'Complete share coordinates')
 for s,q in want.items():
  if whole:require(type(got[s])is int and got[s]==q,'Exact integer shares')
  else:near(got[s],q,True)
def risk(snapshot,counts,marks,chains,params):
 if not counts:exact(snapshot,{'all_passed':False,'checks':{'ALL_CASH':False}},'All cash risk observation');return False
 require(set(counts)==set(marks)==set(chains),'Risk identity scope')
 names=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
 if any(type(v)is not int or v<1 for v in counts.values()):
  require(snapshot['all_passed'] is False,'Nonpositive holding gate');exact(snapshot['checks'],dict.fromkeys(names,False),'Invalid basket gates');return False
 total=sum(F(counts[s])*marks[s] for s in counts);weights={s:F(counts[s])*marks[s]/total for s in counts};ordered=sorted(weights.values(),reverse=True);chain={}
 for s,v in weights.items():chain[chains[s]]=chain.get(chains[s],F(0))+v
 metrics=dict(top1_weight=ordered[0],minimum_single_weight=ordered[-1],top3_weight=sum(ordered[:3]),effective_n=1/sum(v*v for v in ordered),risk_chain_top1_weight=max(chain.values()))
 shares_equal(snapshot['actual_weights'],weights,False)
 for k,v in metrics.items():near(snapshot[k],v,True)
 # Original gate tolerance applies to saved binary64 risk metrics, independently
 # tied above to source quote/share arithmetic, rather than silently tightened.
 checks=dict(zip(names,(snapshot['top1_weight']<=params['max_single_weight']+1e-9,snapshot['minimum_single_weight']>=params['min_single_weight']-1e-9,snapshot['top3_weight']<=params['top_weight_cap']+1e-9,snapshot['effective_n']>=params['minimum_effective_n_ratio']*len(counts)-1e-9,snapshot['risk_chain_top1_weight']<=params['risk_chain_top1_cap']+1e-9)))
 exact(snapshot['checks'],checks,'Five original gates');require(snapshot['all_passed'] is all(checks.values()),'Exact risk verdict');return all(checks.values())

def inspect_saved_account(*,prepared_track,result):
 kind=prepared_track['track'];whole=kind=='WHOLE_LOT';require(kind in ('WHOLE_LOT','CONTINUOUS'),'Known track')
 require(prepared_track['status']=='ENGINE_INPUTS_PREPARED_NOT_EXECUTED','No fabricated blocked account');k=deepcopy(prepared_track['engine_binding']['keyword_arguments']);calendar=prepared_track['stateful_input']['calendar']
 require(result['schema']==('DYNAMIC_WHOLE_LOT_USD_FLOW_SPLIT_ACCOUNT_V1' if whole else 'DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2'),'Original result role')
 fields=('point_in_time_verified','promotion_allowed','formal_benchmark_passed','corporate_action_coverage_verified','fx_conversion_performed','original_objective_v2_unchanged','add_only_search_performed','original_objective_v2_external_flows_enabled')
 fields+=('source_authenticity_verified','broker_atomic_execution_verified','auto_replan_enabled','identity_event_source_authenticity_verified','dividend_modelled') if whole else ('source_bytes_authenticated','event_source_authenticated','exchange_calendar_verified','dividend_cash_flows_included','actual_orders_executed','original_objective_v2_fractional_trading_enabled')
 for field in fields:require(result[field] is False,'Saved account authority must remain False '+field)
 if not whole:
  exact(result['calendar'],calendar,'Original complete source calendar')
  for key in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps'):require(n(result[key])==n(k[key]),'Original account capital/buffer/fee '+key)
  for key,value in dict(quantity_policy='FROZEN_PRIOR_CLOSE_TARGET_WEIGHTS_OPEN_CONTINUOUS_TWO_SIDED_FEE_SOLVE',cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE_AND_FEES',split_timing='BEFORE_OPEN_OLD_SHARES_ONLY',arithmetic='BINARY64_RESEARCH_LEDGER_WITH_EXACT_RATIO_SPLIT_TRANSITION_NOT_EXACT_ECONOMIC_VALUES').items():require(result[key]==value,'Original fractional arithmetic policy')
  require(result['new_conditional_fractional_trading_modelled'] is True and result['new_conditional_usd_external_flows_modelled'] is True,'Original model capability flags')
 else:
  exact(result['identity_events'],[],'No invented identity event bridge')
  for key,value in dict(flow_policy='ONLY_ALREADY_CREDITED_CASH_AVAILABLE_AT_DECISION_CLOSE',cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES',same_day_split_policy='CANCEL_PENDING_WITHOUT_OPEN_REPLAN',execution_policy='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET',risk_label_policy='LAST_KNOWN_DECISION_OBSERVATION',portfolio_track='portfolio_optimization',alias_policy='UNSUPPORTED_FAIL_CLOSED_REQUIRES_PRICE_IDENTITY_INTERVAL_CONTRACT').items():require(result[key]==value,'Original integer arithmetic policy')
  require(result['new_conditional_usd_external_flows_modelled'] is True,'Original USD model capability')
 exact([r['session'] for r in result['daily']],calendar,'Full preserved calendar')
 frames={}
 for name in ('opens','closes'):
  frame=k[name];require(type(frame['columns'])is list and frame['columns'] and len(frame['columns'])==len(set(frame['columns'])),'Unique complete source columns');exact(frame['index'],calendar,'Full source frame');require(len(frame['data'])==len(calendar) and all(type(row)is list and len(row)==len(frame['columns']) for row in frame['data']),'All source rows/column widths');frames[name]={d:dict(zip(frame['columns'],row)) for d,row in zip(calendar,frame['data'])}
 schedule=k['schedule'];require(schedule and len({r['execution_date'] for r in schedule})==len(schedule),'Unique explicit decisions')
 aliases={};issuers={};normalized={}
 for row in schedule:
  require(row['decision_date'] in calendar and calendar.index(row['execution_date'])==calendar.index(row['decision_date'])+1,'Original next source Open')
  total=sum(t['target_weight'] for t in row['targets'].values());require(total>0,'Positive original target mass');targets=deepcopy(row['targets'])
  for s,t in targets.items():
   require(s not in aliases or aliases[s]==t['ticker'],'No unbound alias');aliases[s]=t['ticker'];require(s not in issuers or issuers[s]==t['issuer_id'],'Original issuer identity');issuers[s]=t['issuer_id'];t['target_weight']=t['target_weight']/total
  normalized[row['decision_date']]=targets
 def holdings_identity(h,counts):
  require(set(h)==set(counts),'Full saved holding identities')
  for sid,value in h.items():
   require(set(value)=={'ticker','issuer_id','shares'},'Exact holding fields');exact([value['ticker'],value['issuer_id']],[aliases[sid],issuers[sid]],'Saved holding label tied to source')
  shares_equal({s:v['shares'] for s,v in h.items()},counts,False)
 def mark(name,day,s):
  v=n(frames[name][day][aliases[s]]);require(v>0,'Positive exact saved quote');return v
 cash=n(k['initial_cash_usd']);initial=cash;buffer=n(k['minimum_cash_buffer_usd']);rate=n(k['transaction_cost_bps'])/10000;hold={};cumulative=F(1);peak=F(1);dd=F(0);previous=cash;flow_total=F(0);fee_total=F(0)
 events={};flows={}
 for e in k['corporate_actions']:events.setdefault(e['session'],[]).append(e)
 for e in k['external_flows']:require(e['currency']=='USD' and e['timing']=='BEFORE_OPEN' and e['session'] in calendar[1:],'Explicit post-initial USD event');flows.setdefault(e['session'],[]).append(e)
 trades={}
 for t in result['trades']:require(t['session'] in calendar,'Trade calendar');trades.setdefault(t['session'],[]).append(t)
 decision_by={r['decision_date']:r for r in schedule};execution_by={r['execution_date']:r for r in schedule}
 records=result['decisions'] if whole else result['rebalances'];require(len(records)==len(schedule),'All scheduled decisions/rebalances');records_by={r['decision_date']:r for r in records};require(set(records_by)==set(decision_by),'No omitted decision')
 execution_records={} if not whole else {r['session']:r for r in result['executions']};require(not whole or len(execution_records)==len(result['executions']),'Unique execution records')
 action_traces=result['corporate_actions'];ai=0;seen_executions=set();pending=None;chains={};chain_dates={};seen_trades=0
 for index,day in enumerate(calendar):
  daily=result['daily'][index];before_split=deepcopy(hold)
  if not whole:
   require(daily['initial_point'] is (index==0),'Exact initial point')
   if index:require(daily['execution_status']==(records_by[execution_by[day]['decision_date']]['status'] if day in execution_by else None),'Daily execution outcome tied to saved rebalance')
  if events.get(day):
   if whole:
    require(ai<len(action_traces),'Missing split trace');trace=action_traces[ai];ai+=1;require(trace['session']==day,'Split session');near(trace['cash_usd'],cash);near(trace['split_cash_flow_usd'],F(0));near(trace['split_fees_usd'],F(0));expected=[]
   for event in events[day]:
    s=event['security_id'];before=hold.get(s,0);ratio=F(event['new_shares'],event['old_shares'])
    if whole:
     after=F(before)*ratio;require(after.denominator==1,'No guessed fractional integer entitlement');after=after.numerator
     ev={('ticker' if key=='security_id' else key):v for key,v in event.items()};expected.append(dict(event=ev,pre_shares=before,post_shares=after))
    else:
     after=F(float(F(str(float(before)))*ratio));require(ai<len(action_traces),'Missing fractional split trace');trace=action_traces[ai];ai+=1;exact(trace['event'],event,'Full event source preserved');require(trace['event_id']==hashlib.sha256(enc(event)).hexdigest(),'Action identity');near(trace['shares_before'],F(before),True);near(trace['shares_after'],after,True);near(trace['split_cash_flow_usd'],F(0));near(trace['split_fee_usd'],F(0));require(trace['timing']=='BEFORE_OPEN_MARK_AND_NEW_TRADES','Old shares split before purchases')
    if s in hold:hold[s]=after
   if whole:
    exact(trace['applied_events'],expected,'Exact integer split events');shares_equal(trace['shares'],{s:hold.get(s,0) for s in aliases},True)
    if pending is not None:
     ex=execution_records.get(day);require(ex is not None and ex['status']=='CANCELLED_SPLIT','Pending split basket must cancel');exact(ex['plan'],pending,'Cancelled original basket');exact(trace['cancelled_plan'],pending,'Original pending source');require(ex['decision_date']==pending['decision_date'],'Cancelled decision clock');seen_executions.add(day);pending=None
    else:require(trace['cancelled_plan'] is None,'No invented cancellation')
    require(trace['pending_plan'] is None,'No split replan')
  preflow=cash+sum(F(q)*mark('opens',day,s) for s,q in hold.items());injection=sum((n(e['amount_usd']) for e in flows.get(day,[])),F(0));require(injection>=0,'No inferred withdrawal');cash+=injection;flow_total+=injection;fees=F(0);before=deepcopy(hold);beforecash=cash
  if whole and pending is not None and pending['execution_date']==day:
   ex=execution_records.get(day);require(ex is not None,'Missing frozen execution');require(ex['decision_date']==pending['decision_date'],'Frozen execution decision clock');seen_executions.add(day);wanted=pending['desired_shares'];delta={s:wanted.get(s,0)-hold.get(s,0) for s in sorted(set(hold)|set(wanted))};exact(ex['frozen_delta'],pending['delta'],'Same frozen basket');exact(delta,pending['delta'],'No flow resizing');exact(ex['desired_shares'],wanted,'Same Close integer target');shares_equal(ex['shares_before'],hold,True);near(ex['cash_before_usd'],cash)
   marks={s:mark('opens',day,s) for s in set(hold)|set(wanted)};shares_equal(ex['prices'],marks,False);projectedfees=sum(abs(q)*marks[s]*rate for s,q in delta.items());projectedcash=cash-sum(q*marks[s] for s,q in delta.items())-projectedfees;near(ex['projected_cash_usd'],projectedcash);near(ex['projected_fees_usd'],projectedfees)
   passed=risk(ex['risk'],wanted,{s:marks[s] for s in wanted},{s:chains[s] for s in wanted},k);fails=[key for key,value in ex['risk']['checks'].items() if not value]
   if ex['projected_cash_usd']<k['minimum_cash_buffer_usd']-1e-8:fails.append('CASH_BUFFER')
   exact(ex['failure_reasons'],fails,'Actual Open risk/buffer rejection');require(ex['status']==('REJECTED' if fails else 'FILLED'),'No fabricated fill/reject')
   if not fails:hold=deepcopy(wanted);cash=projectedcash;fees=projectedfees
   shares_equal(ex['shares_after'],hold,True);near(ex['cash_after_usd'],cash);pending=None
  elif not whole and day in execution_by:
   item=execution_by[day];record=records_by[item['decision_date']];targets=normalized[item['decision_date']];exact(record['original_targets'],item['targets'],'Original target weights retained');exact(record['effective_normalized_targets'],targets,'Original normalization separately labelled');require(record['session']==day,'Exact execution clock');near(record['cash_after_flow_before_trades_usd'],cash)
   projection=record['projection'];status=record['status'];require(projection['status']==status,'Same continuous projection status');near(projection['pretrade_equity_usd'],preflow+injection)
   if status=='FILLED':
    after=projection['holdings'];require(set(after)==set(targets),'Complete continuous target coordinates');desired={s:n(v['shares']) for s,v in after.items()};require(all(q>=0 for q in desired.values()),'Nonnegative continuous shares')
    investments=[]
    for s,t in targets.items():exact([after[s]['ticker'],after[s]['issuer_id']],[t['ticker'],t['issuer_id']],'Original holding identity');investments.append(desired[s]*mark('opens',day,s)/n(t['target_weight']))
    require(max(investments)-min(investments)<=USD,'One common Open allocation, no daily rebalancing')
    delta={s:desired.get(s,F(0))-hold.get(s,F(0)) for s in set(hold)|set(desired)};buy=sum(q*mark('opens',day,s) for s,q in delta.items() if q>0);sell=sum(-q*mark('opens',day,s) for s,q in delta.items() if q<0);fees=(buy+sell)*rate;cash+=sell-buy-fees;hold=desired
    near(projection['buy_notional_usd'],buy);near(projection['sell_notional_usd'],sell);near(projection['fees_usd'],fees);near(projection['cash'],cash);require(abs(cash-buffer)<=USD,'Maximal continuous investment preserves only fee/buffer reserve')
   else:
    liquidation=cash+sum(F(q)*mark('opens',day,s)*(1-rate) for s,q in hold.items())
    require((status=='REJECTED_NO_CAPITAL_ABOVE_BUFFER' and preflow+injection<=buffer) or (status=='REJECTED_NO_FEASIBLE_FEE_AND_BUFFER_BASKET' and preflow+injection>buffer and liquidation<buffer+USD),'Saved legitimate continuous rejection')
    for field in ('buy_notional_usd','sell_notional_usd','fees_usd'):near(projection[field],F(0))
    near(projection['cash'],cash);holdings_identity(projection['holdings'],hold)
   near(record['cash_after_usd'],cash);holdings_identity(record['holdings_after'],hold)
  actual_trades=trades.get(day,[]);expected_delta={s:F(hold.get(s,0))-F(before.get(s,0)) for s in set(before)|set(hold)};expected_delta={s:q for s,q in expected_delta.items() if q};require(len(actual_trades)==len(expected_delta) and {t['security_id'] for t in actual_trades}==set(expected_delta),'Every nonzero signed trade once')
  for t in actual_trades:
   s=t['security_id'];q=expected_delta[s];near(t['share_delta'],q,True);price=mark('opens',day,s);near(t['price_usd' if whole else 'open_price_usd'],price);near(t['transaction_cost_usd' if whole else 'fee_usd'],abs(q)*price*rate)
   if not whole:require(t['decision_date']==execution_by[day]['decision_date'],'Trade decision clock')
   if whole:require(t['ticker']==aliases[s],'Trade source alias')
   if whole:require(type(t['share_delta'])is int,'Integer signed trade')
   else:near(t['shares_before'],F(before.get(s,0)),True);near(t['shares_after'],F(hold.get(s,0)),True);near(t['notional_usd'],abs(q)*price);require(t['action']==('BUY' if q>0 else 'SELL'),'Signed side')
  seen_trades+=len(actual_trades);fee_total+=fees
  if whole and day in decision_by:
   item=decision_by[day];record=records_by[day];targets=normalized[day];require(type(record['target_k'])is int and record['target_k']==len(targets),'Original decision coordinate count');exact(record['targets'],targets,'Frozen original strategic targets');require(record['execution_date']==item['execution_date'],'Next original Open');shares_equal(record['shares_before'],hold,True);near(record['cash_before_usd'],cash)
   for s in targets:chains[s]=k['risk_chains_by_decision'][day][s];chain_dates[s]=day
   marks={s:mark('closes',day,s) for s in set(hold)|set(targets)};exact(record['risk_chains'],{s:chains[s] for s in marks},'Decision risk labels');exact(record['risk_chain_observation_dates'],{s:chain_dates[s] for s in marks},'Decision risk observation dates');shares_equal(record['prices'],marks,False);investable=cash+sum(F(q)*marks[s] for s,q in hold.items())-buffer
   projection=record['projection']
   if record['status']=='NO_PLAN':require(type(projection)is dict and all(type(projection[key])is bool for key in ('search_complete','feasible_projection_found')) and not(projection['search_complete'] and projection['feasible_projection_found']),'Explicit saved failed/incomplete repair, not assumed cash target')
   else:
    require(record['status']=='FROZEN','Known decision state');wanted=record['desired_shares'];require(set(wanted)==set(targets) and all(type(q)is int and q>=1 for q in wanted.values()),'Positive original integer basket')
    if projection is None:
     basic={s:math.floor(float(investable)*t['target_weight']/float(marks[s])) for s,t in targets.items()}
     def cash_after(q):return cash-sum(F(q.get(s,0)-hold.get(s,0))*marks[s] for s in set(hold)|set(q))-sum(abs(q.get(s,0)-hold.get(s,0))*marks[s]*rate for s in set(hold)|set(q))
     while all(q>=1 for q in basic.values()) and cash_after(basic)<buffer-F(1,10**8):
      reducible=[s for s,q in basic.items() if q>1]
      if not reducible:break
      basic[max(reducible,key=lambda s:(marks[s],s))]-=1
     exact(wanted,basic,'Original Close floor and deterministic fee decrement')
    else:require(projection['search_complete'] is True and projection['feasible_projection_found'] is True,'Saved complete repair selection');exact(projection['projected_shares'],wanted,'Original repair quantity preserved')
    delta={s:wanted.get(s,0)-hold.get(s,0) for s in sorted(set(hold)|set(wanted))};exact(record['delta'],delta,'Frozen signed Close basket');pf=sum(abs(q)*marks[s]*rate for s,q in delta.items());pc=cash-sum(q*marks[s] for s,q in delta.items())-pf;near(record['projected_cash_usd'],pc);near(record['projected_fees_usd'],pf);require(record['projected_cash_usd']>=k['minimum_cash_buffer_usd']-1e-8,'Frozen fee/buffer gate');require(risk(record['decision_risk'],wanted,{s:marks[s] for s in wanted},{s:chains[s] for s in wanted},k),'Original decision five risks');pending=deepcopy(record)
  closing=cash+sum(F(q)*mark('closes',day,s) for s,q in hold.items());factor=preflow/previous*closing/(preflow+injection);cumulative*=factor;peak=max(peak,cumulative);dd=max(dd,1-cumulative/peak)
  near(daily['cash_usd'],cash);near(daily['cash_injection_usd'],injection);near(daily['normalized_twr'],cumulative,True);near(daily['cumulative_twr'],cumulative-1,True);near(daily['session_twr'],factor-1,True)
  if whole:
   shares_equal(daily['shares'],hold,True);exact(daily['tickers'],{s:aliases[s] for s in hold},'Daily whole aliases');shares_equal(daily['prices'],{s:mark('closes',day,s) for s in hold},False);exact(daily['risk_chains'],{s:chains[s] for s in hold},'Last-known daily risk labels');exact(daily['risk_chain_observation_dates'],{s:chain_dates[s] for s in hold},'Risk observation clock');near(daily['total_value_usd'],closing);near(daily['previous_close_equity_usd'],previous);near(daily['pre_flow_open_equity_usd'],preflow);exact(daily['flow_events'],flows.get(day,[]),'Original USD events unchanged');risk(daily['risk'],hold,{s:mark('closes',day,s) for s in hold},{s:chains[s] for s in hold},k)
  else:
   holdings_identity(daily['holdings'],hold);near(daily['close_equity_usd'],closing);near(daily['fees_usd'],fees)
   if index:
    holdings_identity(daily['holdings_before_split'],before_split);holdings_identity(daily['holdings_before_trades'],before);near(daily['previous_close_equity_usd'],previous);near(daily['pre_flow_open_equity_usd'],preflow);near(daily['post_flow_pre_fee_open_equity_usd'],preflow+injection);near(daily['post_trade_open_equity_usd'],preflow+injection-fees);near(daily['overnight_return'],preflow/previous-1,True);near(daily['after_flow_return'],closing/(preflow+injection)-1,True)
  previous=closing
 require(ai==len(action_traces) and seen_trades==len(result['trades']),'All actions/trades consumed exactly');require(not whole or seen_executions==set(execution_records),'No extra Open execution')
 summary=result['summary'];near(summary['chained_twr'],cumulative-1,True);near(summary['total_cash_injection_usd'],flow_total);near(summary['net_dollar_pnl_excluding_injections_usd'],previous-initial-flow_total)
 if whole:
  for key,value in dict(session_count=len(calendar),all_cash_session_count=sum(not row['shares'] for row in result['daily'])).items():require(type(summary[key])is int and summary[key]==value,'Exact integer summary count')
  exact(summary['k_path'],[len(normalized[item['decision_date']]) for item in schedule],'Complete original k path');near(summary['unadjusted_capital_change_ratio'],previous/initial-1,True)
  near(summary['terminal_value_usd'],previous);near(summary['path_max_drawdown'],dd,True);near(summary['path_return_net'],cumulative-1,True);exact(result['external_flows'],k['external_flows'],'All original flows')
 else:
  near(summary['terminal_equity_usd'],previous);near(summary['terminal_cash_usd'],cash);near(summary['total_fees_usd'],fee_total);near(summary['max_drawdown_twr'],dd,True);require(len(result['external_flows'])==len(k['external_flows']),'All fractional flow traces')
  exact([r['event'] for r in result['external_flows']],k['external_flows'],'All original fractional events')
  require(n(summary['initial_cash_usd'])==initial,'Original summary initial capital')
  for key,value in dict(return_interval_count=len(calendar)-1,rebalance_count=len(schedule),rejected_rebalance_count=sum(r['status']!='FILLED' for r in records),split_event_count=len(action_traces),flow_event_count=len(k['external_flows'])).items():require(type(summary[key])is int and summary[key]==value,'Exact fractional summary count')
  for trace in result['external_flows']:
   require(trace['event_id']==hashlib.sha256(enc(trace['event'])).hexdigest(),'Original flow event identity');require(trace['performance_boundary']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE','Original flow performance boundary')
   for field in ('source_bytes_authenticated','point_in_time_verified','corporate_action_coverage_verified','event_source_authenticated','exchange_calendar_verified','fx_conversion_performed','dividend_cash_flows_included','actual_orders_executed','promotion_allowed','formal_benchmark_passed','add_only_search_performed','original_objective_v2_unchanged'):require(trace[field] is False,'Flow trace authority False')
 return dict(schema='MULTIDECISION_ACCOUNT_LEDGER_INSPECTION_V1',status='PASS',track=kind,daily_rows=len(calendar),return_intervals=len(calendar)-1,scheduled_decisions=len(schedule),trades=len(result['trades']),split_trace_rows=ai,terminal_cash_exact=str(cash),terminal_equity_exact=str(previous),cash_injections_exact=str(flow_total),fees_exact=str(fee_total),chained_twr_exact=str(cumulative-1),maximum_drawdown_exact=str(dd),monetary_tolerance_usd='1e-7',ratio_tolerance='1e-11',whole_lot_frozen_basket_checked=True if whole else False,continuous_open_allocation_and_fee_boundary_checked=not whole,**FLAGS)

