"""Conditional continuous-share account with explicit USD flows and splits.

Targets are frozen at prior Close; continuous quantities are solved at next Open.
This is a dynamic BUY_AND_SELL companion, not the integer frozen basket or an
add-only search. No account, data source, calendar or execution is authenticated.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from urllib.parse import urlsplit
from numbers import Real
import hashlib,json,math,re
import numpy as np
import pandas as pd
from backtest import ndx_dynamic_whole_lot_path as identity

FLAGS=dict.fromkeys(('source_bytes_authenticated','point_in_time_verified','corporate_action_coverage_verified','event_source_authenticated','exchange_calendar_verified','fx_conversion_performed','dividend_cash_flows_included','actual_orders_executed','promotion_allowed','formal_benchmark_passed','add_only_search_performed','original_objective_v2_unchanged'),False)
SCHEMA='DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V1'

def require(ok,msg):
 if not ok:raise ValueError(msg)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def numeric(v,positive=False):
 require(isinstance(v,Real) and not isinstance(v,(bool,np.bool_)),'Finite nonboolean numeric input');x=float(v);require(math.isfinite(x) and (x>0 if positive else x>=0),'Nonnegative finite input');return x
def day(v):
 require(type(v)is str and date.fromisoformat(v).isoformat()==v and date.fromisoformat(v).weekday()<5,'Canonical weekday session');return pd.Timestamp(v)
def reference(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and r['path'].strip()==r['path'] and r['path'] and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Explicit source locator')
def frame(raw):
 require(isinstance(raw,pd.DataFrame),'Explicit DataFrame required')
 for v in raw.index:
  stamp=pd.Timestamp(v);require(stamp.tz is None and stamp==stamp.normalize() and stamp.weekday()<5,'Unambiguous daily sessions')
 return identity._normalise_prices(raw)
def mark(prices,session,ticker):return numeric(identity._price_at(prices,session,ticker),True)
def holdings_value(holdings,marks):return math.fsum(h['shares']*marks[s] for s,h in holdings.items())

def rebalance_projection(*,cash,holdings,targets,marks,buffer,fee_rate):
 """Original continuous 80-step cost solve, without mutating the old account."""
 ids=sorted(set(holdings)|set(targets));equity=cash+holdings_value(holdings,marks);maximum=equity-buffer
 def project(amount):
  desired={s:amount*targets[s]['target_weight']/marks[s] for s in sorted(targets)};buy=sell=0.
  for s in ids:
   delta=desired.get(s,0.)-holdings.get(s,{}).get('shares',0.)
   if delta>0:buy+=delta*marks[s]
   elif delta<0:sell-=delta*marks[s]
  fees=(buy+sell)*fee_rate;after_cash=cash+sell-buy-fees
  return desired,after_cash,buy,sell,fees
 if maximum<=0:return dict(status='REJECTED_NO_CAPITAL_ABOVE_BUFFER',cash=cash,holdings=deepcopy(holdings),buy_notional_usd=0.,sell_notional_usd=0.,fees_usd=0.,pretrade_equity_usd=equity)
 if project(0.)[1]<buffer-identity._amount_tolerance(cash,buffer):return dict(status='REJECTED_NO_FEASIBLE_FEE_AND_BUFFER_BASKET',cash=cash,holdings=deepcopy(holdings),buy_notional_usd=0.,sell_notional_usd=0.,fees_usd=0.,pretrade_equity_usd=equity)
 low=0.;high=maximum
 for _ in range(80):
  midpoint=(low+high)/2.
  if project(midpoint)[1]>=buffer:low=midpoint
  else:high=midpoint
 desired,after_cash,buy,sell,fees=project(low)
 require(all(math.isfinite(v) for v in (after_cash,buy,sell,fees)) and all(math.isfinite(v) and v>=0 for v in desired.values()),'Finite continuous projection')
 require(after_cash>=buffer-identity._amount_tolerance(after_cash,buffer),'Fee solver buffer invariant')
 updated={s:dict(ticker=targets[s]['ticker'],issuer_id=targets[s]['issuer_id'],shares=desired[s]) for s in sorted(targets)}
 require(abs(after_cash+holdings_value(updated,marks)-(equity-fees))<=identity._amount_tolerance(equity,fees),'Open account conservation')
 return dict(status='FILLED',cash=after_cash,holdings=updated,buy_notional_usd=buy,sell_notional_usd=sell,fees_usd=fees,pretrade_equity_usd=equity)

def simulate_dynamic_fractional_flow_split_research(*,closes,opens,schedule,corporate_actions,external_flows,initial_cash_usd,minimum_cash_buffer_usd,transaction_cost_bps=10.,valuation_end_date):
 """Complete common calendar; positive/zero USD cash receipts, no withdrawals.

BEFORE_OPEN receipt means available before the Open rebalance. The performance
boundary marks old shares at Open before the receipt, then credits cash before
fees. Splits multiply only entering old shares before that Open mark.
"""
 close=frame(closes);open_=frame(opens);require(close.index.equals(open_.index) and close.columns.equals(open_.columns),'Same complete Open/Close calendar and column order')
 require(type(schedule)is list and schedule,'Explicit original schedule')
 for r in schedule:
  day(r['decision_date']);day(r['execution_date']);require(type(r['targets'])is dict and r['targets'],'Explicit successful targets')
  for t in r['targets'].values():numeric(t['target_weight'],True)
 items=identity._normalise_schedule(schedule);identity._validate_schedule_identity_and_execution_guards(items,valuation_prices=close,separate_execution_prices_supplied=True,require_separate_execution_prices=True,require_next_session_execution=True,require_issuer_trace=True)
 aliases={}
 for item in items:
  require(item['decision_date'] in close.index,'Every frozen decision Close must exist in the common calendar')
  for sid,target in item['targets'].items():
   require(sid not in aliases or aliases[sid]==target['ticker'],'Unbridged security ticker change')
   aliases[sid]=target['ticker']
 start=items[0]['decision_date'];end=day(valuation_end_date);require(start in close.index and end in close.index and end>=items[-1]['execution_date'],'Initial Close and final session complete')
 calendar=close.index[(close.index>=start)&(close.index<=end)];require(len(calendar)>=2,'At least one causal interval')
 # Validate the consumed interval only. No future prices affect this account.
 for f in (close.loc[calendar],open_.loc[calendar]):
  for v in f.to_numpy().flat:numeric(v,True)
 cash=numeric(initial_cash_usd,True);initial=cash;buffer=numeric(minimum_cash_buffer_usd);bps=numeric(transaction_cost_bps);require(bps<=10000,'Fees limited to at most notional');rate=bps/10000.
 universe={s for r in items for s in r['targets']};action_by_day={};seen=set()
 require(type(corporate_actions)is list and type(external_flows)is list,'Explicit full supplied events')
 for event in corporate_actions:
  require(type(event)is dict and set(event)=={'security_id','session','new_shares','old_shares','source_url','evidence_sha256'},'Exact security split schema')
  d=day(event['session']);sid=event['security_id'];require(sid in universe and d in calendar and d>start,'Split within original account calendar/domain');key=(d,sid);require(key not in seen,'Duplicate split application');seen.add(key)
  a,b=event['new_shares'],event['old_shares'];require(type(a)is int and type(b)is int and a>0 and b>0 and a!=b,'Positive nontrivial integer split ratio')
  url=event['source_url'];require(type(url)is str and not any(c.isspace() for c in url),'Explicit split locator');parsed=urlsplit(url);require(parsed.scheme=='https' and parsed.hostname and parsed.username is None and parsed.password is None and type(event['evidence_sha256'])is str and re.fullmatch('[a-f0-9]{64}',event['evidence_sha256']),'HTTPS evidence and digest')
  action_by_day.setdefault(d,[]).append(deepcopy(event))
 flow_by_day={};seen_flow=set()
 for event in external_flows:
  require(type(event)is dict and set(event)=={'session','amount_usd','timing','currency','source_reference'},'Exact external flow schema')
  d=day(event['session']);require(d in calendar and d>start and event['timing']=='BEFORE_OPEN' and event['currency']=='USD','Explicit USD receipt at original session before trading, no FX inference');numeric(event['amount_usd']);reference(event['source_reference'])
  key=(event['session'],event['source_reference']['path'],event['source_reference']['sha256']);require(key not in seen_flow,'Duplicate external event identity');seen_flow.add(key);flow_by_day.setdefault(d,[]).append(deepcopy(event))
 bydate={r['execution_date']:r for r in items};holdings={};daily=[];trades=[];rebalances=[];actions=[];flows=[];previous=initial;cumulative=1.;peak=1.;maxdd=0.;total_fees=total_flow=0.;applied=set()
 daily.append(dict(session=start.date().isoformat(),initial_point=True,cash_usd=cash,holdings={},close_equity_usd=cash,cash_injection_usd=0.,fees_usd=0.,session_twr=0.,cumulative_twr=0.,normalized_twr=1.))
 for d in calendar[1:]:
  session=d.date().isoformat();before_split=deepcopy(holdings)
  for event in action_by_day.get(d,[]):
   eid=hashlib.sha256(encode(event)).hexdigest();require(eid not in applied,'Split already applied');applied.add(eid);sid=event['security_id'];oldshares=holdings.get(sid,{}).get('shares',0.)
   after=float(Fraction(str(oldshares))*event['new_shares']/event['old_shares']);require(math.isfinite(after) and after>=0,'Finite fractional split entitlement')
   if sid in holdings:holdings[sid]['shares']=after
   actions.append(dict(event_id=eid,event=deepcopy(event),shares_before=oldshares,shares_after=after,split_cash_flow_usd=0.,split_fee_usd=0.,timing='BEFORE_OPEN_MARK_AND_NEW_TRADES',**FLAGS))
  before=deepcopy(holdings);openmarks={s:mark(open_,d,h['ticker']) for s,h in holdings.items()};pre_flow=cash+holdings_value(holdings,openmarks)
  cash_before=cash;injection=math.fsum(numeric(e['amount_usd']) for e in flow_by_day.get(d,[]));cash+=injection;total_flow+=injection
  require(math.isfinite(cash) and previous>0 and pre_flow>0 and pre_flow+injection>0,'Finite positive cash-flow performance boundaries')
  for event in flow_by_day.get(d,[]):flows.append(dict(event_id=hashlib.sha256(encode(event)).hexdigest(),event=deepcopy(event),performance_boundary='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE',**FLAGS))
  fees=0.;execution=None
  if d in bydate:
   item=bydate[d];targets=item['targets'];ids=sorted(set(holdings)|set(targets));marks={s:mark(open_,d,(targets[s] if s in targets else holdings[s])['ticker']) for s in ids}
   projection=rebalance_projection(cash=cash,holdings=holdings,targets=targets,marks=marks,buffer=buffer,fee_rate=rate);execution=projection['status']
   if execution=='FILLED':
    updated=projection['holdings']
    for sid in ids:
     pre=holdings.get(sid,{}).get('shares',0.);post=updated.get(sid,{}).get('shares',0.);delta=post-pre
     if delta!=0.:
      notional=abs(delta)*marks[sid];trades.append(dict(session=session,decision_date=item['decision_date'].date().isoformat(),security_id=sid,action='BUY' if delta>0 else 'SELL',shares_before=pre,shares_after=post,share_delta=delta,open_price_usd=marks[sid],notional_usd=notional,fee_usd=notional*rate))
    cash=projection['cash'];holdings=updated;fees=projection['fees_usd'];total_fees+=fees
   rebalances.append(dict(session=session,decision_date=item['decision_date'].date().isoformat(),status=execution,original_targets=deepcopy(schedule[item['sequence']-1]['targets']),effective_normalized_targets=deepcopy(targets),cash_after_flow_before_trades_usd=cash_before+injection,cash_after_usd=cash,holdings_after=deepcopy(holdings),projection=projection))
  closemarks={s:mark(close,d,h['ticker']) for s,h in holdings.items()};closing=cash+holdings_value(holdings,closemarks);postmarks={s:mark(open_,d,h['ticker']) for s,h in holdings.items()};posttrade=cash+holdings_value(holdings,postmarks)
  require(abs(posttrade-(pre_flow+injection-fees))<=identity._amount_tolerance(posttrade,pre_flow,injection,fees),'Open conservation including flows and fees');require(math.isfinite(closing) and closing>0,'Finite positive Close equity')
  overnight=pre_flow/previous;after_flow=closing/(pre_flow+injection);factor=overnight*after_flow;cumulative*=factor;require(math.isfinite(cumulative) and cumulative>0,'Finite positive chained TWR');peak=max(peak,cumulative);maxdd=max(maxdd,1.-cumulative/peak)
  daily.append(dict(session=session,initial_point=False,previous_close_equity_usd=previous,pre_flow_open_equity_usd=pre_flow,cash_injection_usd=injection,post_flow_pre_fee_open_equity_usd=pre_flow+injection,post_trade_open_equity_usd=posttrade,close_equity_usd=closing,cash_usd=cash,fees_usd=fees,holdings_before_split=before_split,holdings_before_trades=before,holdings=deepcopy(holdings),execution_status=execution,overnight_return=overnight-1.,after_flow_return=after_flow-1.,session_twr=factor-1.,cumulative_twr=cumulative-1.,normalized_twr=cumulative));previous=closing
 summary=dict(initial_cash_usd=initial,terminal_cash_usd=cash,terminal_equity_usd=previous,total_cash_injection_usd=total_flow,total_fees_usd=total_fees,net_dollar_pnl_excluding_injections_usd=previous-initial-total_flow,chained_twr=cumulative-1.,max_drawdown_twr=maxdd,return_interval_count=len(calendar)-1,rebalance_count=len(rebalances),rejected_rebalance_count=sum(r['status']!='FILLED' for r in rebalances),split_event_count=len(actions),flow_event_count=len(flows))
 return dict(schema=SCHEMA,calendar=[d.date().isoformat() for d in calendar],summary=summary,daily=daily,rebalances=rebalances,trades=trades,corporate_actions=actions,external_flows=flows,initial_cash_usd=initial,minimum_cash_buffer_usd=buffer,transaction_cost_bps=bps,quantity_policy='FROZEN_PRIOR_CLOSE_TARGET_WEIGHTS_OPEN_CONTINUOUS_TWO_SIDED_FEE_SOLVE',cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE_AND_FEES',split_timing='BEFORE_OPEN_OLD_SHARES_ONLY',arithmetic='BINARY64_RESEARCH_LEDGER_WITH_EXACT_RATIO_SPLIT_TRANSITION_NOT_EXACT_ECONOMIC_VALUES',original_objective_v2_fractional_trading_enabled=False,original_objective_v2_external_flows_enabled=False,new_conditional_fractional_trading_modelled=True,new_conditional_usd_external_flows_modelled=True,**FLAGS)
