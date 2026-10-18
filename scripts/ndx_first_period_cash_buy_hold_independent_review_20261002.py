"""Standalone Fraction review of saved first-eight fixed holdings; no kernel imports."""
from pathlib import Path
from fractions import Fraction as F
from copy import deepcopy
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
ACCOUNT=ROOT/'data/cache/research/first_period_cash_buy_hold_account_20261002_v1/accounts.json'
ACCOUNT_SHA='4112089be89d196405da8df2e1a6266eb7ad95baad992b0759e28c7c8800c792'
PUBLICATION_SHA='d841df9120aead6a9cc8c0e6d003c5e4d48beed380d31fbe0d69daa032145ec9'
PINS={'inputs': ('data/cache/research/first_period_standard_cash_inputs_20261002_v1/inputs.json', 'f583f6e55efeb78f0fc1c761bb2027076274012c30a7dda528ef6dee1a3004ee'), 'input_publication': ('data/cache/research/first_period_standard_cash_inputs_20261002_v1/publication.json', '304303cd9e53cb92723d4fd463f58934f3506339a2f8170ffef9cd9f258e6d47'), 'repair_results': ('data/cache/research/first_period_cash_repair_research_20261002_v1/results.json', '61b9e1e66c18b74fb503e1de57a292514e9467ec07215eaa7126055ae2b395b7'), 'old_results': ('data/cache/research/first_period_cash_neighbor_research_20261002_v1/results.json', 'dfd434e79c5f9f1242a1a2d11d7cbe7bf9d830f6d5e3e380225a64ff31dcdbdf'), 'RETURN_price': ('data/cache/research/return_eight_price_only_20260923_v1/raw_assembly.json', 'e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336'), 'BAD_TAIL_price': ('data/cache/research/bad_tail_five_input_projection_20260923_v1/projection.json', '77d03b11751322158158b66a18ecf19fd669cacfa730b99c3dbda1139b25e6be'), 'DRAWDOWN_price': ('data/cache/research/drawdown_four_input_assembly_20260923_v1/assembly.json', 'cb2ab027a2506a43d97e7c65494d524b1c7d7e890e7b9a2f67f863768c61aa67'), 'LEGACY_TARGET_DISTANCE_price': ('data/cache/research/legacy_twelve_price_only_20260923_v1/prices.json', 'a50c4fd387f10262527e82ad0edd2bae7b799b67e2d08cff2e4a47030a64b342')}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path,expected):
 assert type(expected) is str and len(expected)==64,'Pending actual SHA'
 raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==expected;return json.loads(raw)
def ratio(x):return F(int(x['numerator']),int(x['denominator']))
def reference(role,pointer=None):
 path,h=PINS[role];r=dict(path=str(ROOT/path),sha256=h)
 if pointer is not None:r['json_pointer']=pointer
 return r
def run():
 result=load(ACCOUNT,ACCOUNT_SHA);receipt=load(ACCOUNT.parent/'publication.json',PUBLICATION_SHA)
 docs={k:load(ROOT/path,h) for k,(path,h) in PINS.items()}
 assert receipt['account_reference']==dict(path=str(ACCOUNT),sha256=ACCOUNT_SHA)
 assert receipt['source_hashes']==result['source_hashes'] and receipt['status']=='PUBLISHED_CONDITIONAL_PRICE_ONLY_PATHS'
 assert result['schema']=='FIRST_PERIOD_CASH_FIXED_BUY_HOLD_PRICE_ONLY_TWR_V1'
 flags=('old_experiments_reexecuted','selected_plans_reselected','dividends_modelled','fx_modelled','corporate_actions_modelled','cash_interest_modelled','total_return_claimed','old_six_period_strategy_replayed','formal_dual_benchmark_comparison','point_in_time_verified','promotion_allowed','orders_executed','economic_winner_selected','identity_gaps_resolved','full_transitive_source_closure_reverified','exchange_calendar_completeness_verified','real_user_cash_claimed')
 for flag in flags:assert result[flag] is receipt[flag] is False
 assert len(result['rows'])==result['scenario_count']==len(docs['inputs']['rows'])==8
 assert result['account_session_count']==106
 calendar=result['observed_calendar'];assert len(calendar)==107 and calendar==sorted(set(calendar))
 assert (calendar[0],calendar[1],calendar[-1])==('2023-03-31','2023-04-03','2023-09-01')
 for role in ('RETURN_price','BAD_TAIL_price','DRAWDOWN_price','LEGACY_TARGET_DISTANCE_price'):
  assert docs[role]['calendar']==calendar
  metadata=deepcopy(docs[role]);(metadata['price_projection'] if 'price_projection' in metadata else metadata).pop('matrices')
  assert result['price_evidence_metadata'][role[:-6]]==metadata
 for role in PINS:assert result['input_references'][role]==reference(role)
 summary=[];old_routes=[];count=0
 for index,(source,saved) in enumerate(zip(docs['inputs']['rows'],result['rows'])):
  assert source==saved['input_row'] and source['scenario_id']==saved['scenario_id']
  assert saved['input_reference']==reference('inputs',f'/rows/{index}')
  selected=docs['repair_results']['rows'][index]['selected'];assert saved['saved_selection']==selected
  assert saved['selection_reference']==reference('repair_results',f'/rows/{index}/selected')
  role='old_results' if selected['source']=='PREVIOUS_BATCH' else 'repair_results'
  assert selected['source'] in ('PREVIOUS_BATCH','NEW_REPAIR_BATCH')
  plan_index=selected['plan_index'];assert type(plan_index) is int
  plan=docs[role]['rows'][index]['evaluation']['branches'][0]['evaluated_plans'][plan_index]
  assert saved['selected_plan']==plan and plan['feasible'] is True
  assert saved['selected_plan_reference']==reference(role,f'/rows/{index}/evaluation/branches/0/evaluated_plans/{plan_index}')
  if role=='old_results':
   old_routes.append((source['lane'],source['cash_event']['amount_usd'],plan_index))
   wrong=docs['repair_results']['rows'][index]['evaluation']['branches'][0]['evaluated_plans'][plan_index]
   assert wrong['buy_shares']!=plan['buy_shares'],'Wrong-route fixture must be discriminating'
  mapping={sid:source['securities'][sid]['ticker'] for sid in plan['buy_shares']}
  assert saved['security_to_ticker']==mapping and len(set(mapping.values()))==len(mapping)
  assert saved['security_mapping_reference']==reference('inputs',f'/rows/{index}/securities')
  price_doc=docs[source['lane']+'_price'];price=price_doc.get('price_projection',price_doc)
  prefix='/price_projection' if 'price_projection' in price_doc else ''
  account=saved['account'];rows=account['rows'];assert len(rows)==len(saved['quote_evidence'])==len(saved['accounting_inputs']['sessions'])==106
  assert saved['accounting_inputs']['initial']==dict(session=calendar[0],cash_usd=source['starting_cash_usd'],holdings={},close_prices={})
  assert F(source['starting_cash_usd'])==25000 and source['holdings']=={}
  fee_rate=F(source['transaction_cost_bps'])/10000;assert fee_rate==F(1,1000)
  cash=F(25000);holdings={};previous=F(25000);wealth=peak=F(1);drawdown=F(0);total_fee=total_flow=F(0)
  peak_day=calendar[0];worst_peak=worst_day=None
  for day_index,(day,row,quotes,request) in enumerate(zip(calendar[1:],rows,saved['quote_evidence'],saved['accounting_inputs']['sessions'])):
   first=day_index==0;buys=plan['buy_shares'] if first else {};flow=F(source['cash_event']['amount_usd']) if first else F(0)
   marks={field:{sid:price['matrices'][field][day][ticker] for sid,ticker in mapping.items()} for field in ('open','close')}
   assert request==dict(session=day,open_prices=marks['open'],close_prices=marks['close'],cash_injection_usd=source['cash_event']['amount_usd'] if first else '0',buy_shares=buys)
   assert quotes['session']==day and set(quotes['quotes'])=={'open','close'}
   for field in ('open','close'):
    assert set(quotes['quotes'][field])==set(mapping)
    for sid,ticker in mapping.items():
     literal=marks[field][sid];assert type(literal) is str and F(literal)>0
     assert quotes['quotes'][field][sid]==dict(ticker=ticker,decimal_literal=literal,reference=reference(source['lane']+'_price',f'{prefix}/matrices/{field}/{day}/{ticker}'))
     if first and field=='open':assert literal==source['execution_prices'][sid]
   before=cash+sum((q*F(marks['open'][s]) for s,q in holdings.items()),F(0));after_flow=before+flow
   gross=sum((q*F(marks['open'][s]) for s,q in buys.items()),F(0));fee=gross*fee_rate
   next_cash=cash+flow-gross-fee;newhold={s:holdings.get(s,0)+buys.get(s,0) for s in set(holdings)|set(buys)}
   assert next_cash>=0 and newhold==plan['proposed_holdings']
   open_after=next_cash+sum((q*F(marks['open'][s]) for s,q in newhold.items()),F(0))
   closing=next_cash+sum((q*F(marks['close'][s]) for s,q in newhold.items()),F(0))
   assert open_after==after_flow-fee
   assert row['session']==day and row['previous_close_session']==calendar[day_index]
   assert row['holdings_before']==holdings and row['holdings_after']==newhold and row['buy_shares']==buys
   fields=dict(previous_close_equity_usd=previous,pre_flow_open_equity_usd=before,cash_injection_usd=flow,post_flow_pre_fee_open_equity_usd=after_flow,post_trade_open_equity_usd=open_after,close_equity_usd=closing,gross_buy_usd=gross,fees_usd=fee,cash_after_usd=next_cash,overnight_pnl_usd=before-previous,intraday_mark_pnl_before_fees_usd=closing-open_after,after_flow_pnl_net_fees_usd=closing-after_flow,cash_flow_adjusted_pnl_usd=closing-previous-flow)
   for key,value in fields.items():assert F(row[key])==value,(index,day,key)
   overnight=before/previous;intraday=closing/after_flow;factor=overnight*intraday;wealth*=factor
   for key,value in dict(overnight_return=overnight-1,after_flow_return=intraday-1,session_twr=factor-1,cumulative_twr=wealth-1).items():assert ratio(row[key])==value
   if wealth>peak:peak=wealth;peak_day=day
   dd=1-wealth/peak
   if dd>drawdown:drawdown=dd;worst_peak=peak_day;worst_day=day
   cash=next_cash;holdings=newhold;previous=closing;total_fee+=fee;total_flow+=flow;count+=1
  assert total_flow==F(source['cash_event']['amount_usd']) and total_fee==F(plan['fees_usd'])
  for key,value in dict(initial_equity_usd=F(25000),terminal_equity_usd=previous,total_cash_injection_usd=total_flow,total_fees_usd=total_fee,net_dollar_pnl_excluding_injections_usd=previous-25000-total_flow,transaction_cost_bps=F(10)).items():assert F(account[key])==value
  assert ratio(account['chained_twr'])==wealth-1 and wealth==previous/(25000+total_flow)
  assert ratio(saved['drawdown']['maximum_drawdown'])==drawdown and ratio(saved['drawdown']['initial_wealth'])==1
  assert saved['drawdown']['initial_observation_included'] is True and saved['drawdown']['observation_clock']=='INITIAL_CLOSE_THEN_EACH_SESSION_CLOSE_ONLY'
  for flag in flags:assert saved[flag] is False
  for flag in ('dividends_modelled','corporate_actions_modelled','orders_executed','point_in_time_verified','promotion_allowed','cash_buffer_and_risk_gates_evaluated'):assert account[flag] is False
  summary.append(dict(scenario=source['scenario_id'],selected_source=selected['source'],selected_index=plan_index,terminal_equity=str(previous),twr=str(wealth-1),maximum_drawdown=str(drawdown),drawdown_peak=worst_peak,drawdown_trough=worst_day,display_twr=float(wealth-1),display_drawdown=float(drawdown)))
 assert old_routes==[('BAD_TAIL','1000',13),('LEGACY_TARGET_DISTANCE','1000',9)]
 assert count==848
 assert digest(ACCOUNT)==ACCOUNT_SHA and digest(ACCOUNT.parent/'publication.json')==PUBLICATION_SHA
 for role,(path,h) in PINS.items():assert digest(ROOT/path)==h
 return dict(account_sha256=ACCOUNT_SHA,publication_sha256=PUBLICATION_SHA,sessions_checked=count,initial_wealth_observations=8,old_route_cases=old_routes,rows=summary)
if __name__=='__main__':print(json.dumps(run(),indent=2))
