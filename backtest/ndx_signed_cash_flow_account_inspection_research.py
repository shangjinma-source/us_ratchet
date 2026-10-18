"""Independent exact inspection of explicit signed-share cash-flow account results.

Standard library only; no producer/helper import, IO, selection or execution.
The explicit input rows are declarations, not authenticated prices or sessions.
The entire saved V1 result (including all fields/types) must match reconstruction.
"""
from datetime import date
from decimal import Decimal
from fractions import Fraction
import hashlib
import json

SCHEMA='SIGNED_CASH_FLOW_ACCOUNT_INDEPENDENT_INSPECTION_V1'
MAX_SESSIONS=512
MAX_SECURITIES=256
MAX_SHARES=10**12
MAX_RATIO_BITS=12000
RESULT_FALSE=('zero_capital_inception_supported','broker_settlement_or_intraday_ordering_verified',
 'single_replacement_action_semantics_verified','cash_buffer_and_risk_gates_evaluated','dividends_modelled',
 'corporate_actions_modelled','cash_interest_modelled','withdrawals_supported','exchange_session_adjacency_verified',
 'historical_experiment_executed','orders_executed','point_in_time_verified','promotion_allowed')
FLAGS=dict.fromkeys(('source_bytes_authenticated','producer_called','producer_helpers_called','account_executed',
 'orders_executed','fit_executed','risk_evaluated','action_family_verified','exchange_session_adjacency_verified',
 'broker_settlement_verified','point_in_time_verified','promotion_allowed'),False)

def require(ok,message):
 if not ok:raise ValueError(message)
def keys(obj,expected,where):require(type(obj)is dict and set(obj)==set(expected),where+' exact object fields')
def scalar(value):
 require(type(value)in(str,int,Decimal),'Explicit decimal literal/int/Decimal; no bool/float')
 if type(value)is str:require(0<len(value)<=80 and value.strip()==value,'Bounded decimal text')
 if type(value)is int:require(abs(value)<=10**40,'Bounded integer amount')
 try:d=Decimal(value)
 except Exception as error:raise ValueError('Invalid decimal input')from error
 require(d.is_finite(),'Finite decimal input')
 parts=d.as_tuple();require(len(parts.digits)<=40 and abs(parts.exponent)<=40,'Decimal resource bound')
 # Decimal construction and Fraction conversion are exact and context independent.
 q=Fraction(d);require(0<=q<=10**40,'Nonnegative bounded amount');return q
def calendar_day(value):
 require(type(value)is str,'Session string')
 try:parsed=date.fromisoformat(value)
 except ValueError as error:raise ValueError('Invalid session')from error
 require(parsed.isoformat()==value,'Canonical session YYYY-MM-DD');return parsed

def holdings_map(value,signed=False):
 require(type(value)is dict and len(value)<=MAX_SECURITIES,'Bounded SID map')
 for sid,q in value.items():
  require(type(sid)is str and bool(sid)and sid.strip()==sid,'Nonblank SID')
  require(type(q)is int and -MAX_SHARES<=q<=MAX_SHARES and (signed or q>=0),'Typed whole share amount')
 return {sid:value[sid]for sid in sorted(value)}
def price_map(value,sids):
 keys(value,sids,'Exact old/traded SID prices');out={sid:scalar(value[sid])for sid in sorted(sids)}
 require(all(q>0 for q in out.values()),'Strictly positive marks even for zero keys');return out

def decimal_text(value):
 """Construct terminating decimal independently by exact base-10 scaling."""
 denominator=value.denominator;places=0;scale=1
 while scale%denominator:
  scale*=10;places+=1;require(places<=200,'Money must have bounded terminating representation')
 scaled=value.numerator*(scale//denominator)
 if places==0:return str(scaled)
 sign='-'if scaled<0 else'';digits=str(abs(scaled)).rjust(places+1,'0')
 return sign+(digits[:-places]+'.'+digits[-places:]).rstrip('0').rstrip('.')
def fraction_object(value):
 require(abs(value.numerator).bit_length()<=MAX_RATIO_BITS and value.denominator.bit_length()<=MAX_RATIO_BITS,'Explicit ratio resource bound')
 return dict(numerator=str(value.numerator),denominator=str(value.denominator))
def typed_equal(actual,expected,path='$'):
 require(type(actual)is type(expected),'Saved result type mismatch at '+path)
 if type(expected)is dict:
  require(set(actual)==set(expected),'Saved result fields mismatch at '+path)
  for key in expected:typed_equal(actual[key],expected[key],path+'.'+key)
 elif type(expected)is list:
  require(len(actual)==len(expected),'Saved result length mismatch at '+path)
  for i,(a,b)in enumerate(zip(actual,expected)):typed_equal(a,b,path+'['+str(i)+']')
 else:require(actual==expected,'Saved result value mismatch at '+path)

def inspect_saved_signed_account(*,initial,sessions,transaction_cost_bps,saved_result):
 keys(initial,('session','cash_usd','holdings','close_prices'),'Initial input')
 require(type(sessions)is list and 1<=len(sessions)<=MAX_SESSIONS,'Complete bounded explicit session list')
 previous_session=calendar_day(initial['session']);cash=scalar(initial['cash_usd']);positions=holdings_map(initial['holdings'])
 marks=price_map(initial['close_prices'],positions)
 original_capital=cash+sum((F*marks[sid]for sid,F in positions.items()),Fraction())
 require(original_capital>0,'Unsupported zero-capital inception')
 previous_close=original_capital;bps=scalar(transaction_cost_bps);require(bps<=10000,'Fee bps bound');fee_rate=bps/10000
 cumulative=Fraction(1);injected=Fraction();paid=Fraction();rows=[]
 for source in sessions:
  keys(source,('session','open_prices','close_prices','cash_injection_usd','trade_shares'),'Session input')
  session=calendar_day(source['session']);require(session>previous_session,'Strict original date order')
  changes=holdings_map(source['trade_shares'],signed=True);sids=set(positions)|set(changes);require(len(sids)<=MAX_SECURITIES,'Full SID resource bound')
  opening=price_map(source['open_prices'],sids);closing=price_map(source['close_prices'],sids);flow=scalar(source['cash_injection_usd'])
  before=cash+sum((q*opening[sid]for sid,q in positions.items()),Fraction())
  post_flow=before+flow;require(previous_close>0 and before>0 and post_flow>0,'Defined prior/preflow/postflow capital')
  ending={sid:positions.get(sid,0)+changes.get(sid,0)for sid in sorted(sids)}
  require(all(0<=q<=MAX_SHARES for q in ending.values()),'No short or oversized resulting position')
  bought=Fraction();sold=Fraction()
  for sid,delta in changes.items():
   if delta<0:sold-=delta*opening[sid]
   else:bought+=delta*opening[sid]
  sell_fee=sold*fee_rate;buy_fee=bought*fee_rate;fees=sell_fee+buy_fee
  end_cash=cash+flow+sold-sell_fee-bought-buy_fee;require(end_cash>=0,'Exact cash covers bilateral fees')
  after=end_cash+sum((q*opening[sid]for sid,q in ending.items()),Fraction())
  end_equity=end_cash+sum((q*closing[sid]for sid,q in ending.items()),Fraction())
  require(after+fees==post_flow,'Self financing at Open')
  # Fees enter the second factor, whose denominator includes injection before fees.
  overnight=before/previous_close;intraday=end_equity/post_flow;period=overnight*intraday;cumulative*=period
  injected+=flow;paid+=fees
  amounts=dict(previous_close_equity_usd=previous_close,pre_flow_open_equity_usd=before,cash_injection_usd=flow,
   post_flow_pre_fee_open_equity_usd=post_flow,post_trade_open_equity_usd=after,close_equity_usd=end_equity,
   gross_buy_usd=bought,gross_sell_usd=sold,fees_usd=fees,cash_after_usd=end_cash,
   overnight_pnl_usd=before-previous_close,intraday_mark_pnl_before_fees_usd=end_equity-after,
   after_flow_pnl_net_fees_usd=end_equity-post_flow,cash_flow_adjusted_pnl_usd=end_equity-previous_close-flow)
  rows.append(dict(previous_close_session=previous_session.isoformat(),session=session.isoformat(),
   **{key:decimal_text(value)for key,value in amounts.items()},holdings_before=dict(positions),trade_shares=dict(changes),
   holdings_after=dict(ending),overnight_return=fraction_object(overnight-1),after_flow_return=fraction_object(intraday-1),
   session_twr=fraction_object(period-1),cumulative_twr=fraction_object(cumulative-1)))
  previous_session=session;previous_close=end_equity;cash=end_cash;positions=ending
 expected=dict(schema='SIGNED_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1',rows=rows,initial_equity_usd=decimal_text(original_capital),
  terminal_equity_usd=decimal_text(previous_close),total_cash_injection_usd=decimal_text(injected),total_fees_usd=decimal_text(paid),
  net_dollar_pnl_excluding_injections_usd=decimal_text(previous_close-original_capital-injected),chained_twr=fraction_object(cumulative-1),
  transaction_cost_bps=decimal_text(bps),cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_BASKET_AND_BOTH_SIDE_FEES',
  arithmetic='EXACT_RATIONAL_VALUES_FINITE_DECIMAL_MONEY_NO_FLOAT_INPUT',
  execution_assumption='SAME_OPEN_NET_CASH_SETTLEMENT_SELL_PROCEEDS_AVAILABLE_FOR_BUYS',
  parameter_authority='CALLER_SUPPLIED_SYNTHETIC_OR_EXPLICIT_SCENARIO_NOT_SOURCE_BOUND',
  engineering_resource_limits_not_investment_policy=dict(sessions=MAX_SESSIONS,security_ids=MAX_SECURITIES,ratio_bits=MAX_RATIO_BITS),
  **dict.fromkeys(RESULT_FALSE,False))
 typed_equal(saved_result,expected)
 raw=json.dumps(saved_result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
 return dict(schema=SCHEMA,status='PASS',session_count=len(rows),initial_session=initial['session'],terminal_session=sessions[-1]['session'],
  saved_result_content_sha256=hashlib.sha256(raw).hexdigest(),all_saved_rows_and_fields_checked=True,
  scope='EXPLICIT_SIGNED_WHOLE_SHARE_ACCOUNTING_ONLY_NOT_ACTION_POLICY_OR_SOURCE_AUTHENTICATION',**FLAGS)
