"""Independent saved eighty-path arithmetic and source-pointers; never executes kernel."""
from pathlib import Path
from fractions import Fraction as F
from copy import deepcopy
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
ACCOUNT=ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json'
ACCOUNT_SHA='7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'
PUBLICATION_SHA='fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'
PINS={'inputs': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json', '1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'), 'input_publication': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json', '54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'), 'topups': ('data/cache/research/old_holding_topup_research_20261002_v1/results.json', '1192aa5876b8ea9e36c84ad33d88f5504df849e8612312f1886fad6b579351fb'), 'topup_publication': ('data/cache/research/old_holding_topup_research_20261002_v1/publication.json', 'ed4f230d5e74ac0fb2000149caab80825e48d36cf3d7cd98a5f0858abc0fbc16'), 'control': ('data/cache/research/incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json', '53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'), 'RETURN_price': ('data/cache/research/return_eight_price_only_20260923_v1/raw_assembly.json', 'e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336'), 'BAD_TAIL_price': ('data/cache/research/bad_tail_five_input_projection_20260923_v1/projection.json', '77d03b11751322158158b66a18ecf19fd669cacfa730b99c3dbda1139b25e6be'), 'DRAWDOWN_price': ('data/cache/research/drawdown_four_input_assembly_20260923_v1/assembly.json', 'cb2ab027a2506a43d97e7c65494d524b1c7d7e890e7b9a2f67f863768c61aa67'), 'LEGACY_TARGET_DISTANCE_price': ('data/cache/research/legacy_twelve_price_only_20260923_v1/prices.json', 'a50c4fd387f10262527e82ad0edd2bae7b799b67e2d08cff2e4a47030a64b342')}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p,h):
 assert type(h) is str and len(h)==64,'Pending actual anchor'
 raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==h;return json.loads(raw)
def ratio(d):return F(int(d['numerator']),int(d['denominator']))
def ref(role,pointer=None):
 path,h=PINS[role];x=dict(path=str(ROOT/path),sha256=h)
 if pointer is not None:x['json_pointer']=pointer
 return x

def verify_path(path,initial,sessions):
 assert path['accounting_inputs']==dict(initial=initial,sessions=sessions,transaction_cost_bps='10')
 account=path['account'];assert len(account['rows'])==len(sessions)
 cash=F(initial['cash_usd']);holdings=dict(initial['holdings']);previous=cash+sum((q*F(initial['close_prices'][s]) for s,q in holdings.items()),F(0));initial_value=previous
 wealth=peak=F(1);dd=feesum=flowsum=F(0);previous_day=initial['session']
 for request,row in zip(sessions,account['rows']):
  buys=request['buy_shares'];flow=F(request['cash_injection_usd']);opens=request['open_prices'];closes=request['close_prices']
  assert set(opens)==set(closes)==set(holdings)|set(buys)
  before=cash+sum((q*F(opens[s]) for s,q in holdings.items()),F(0));after=before+flow
  gross=sum((q*F(opens[s]) for s,q in buys.items()),F(0));fee=gross/1000;newcash=cash+flow-gross-fee
  newhold={s:holdings.get(s,0)+buys.get(s,0) for s in set(holdings)|set(buys)}
  traded=newcash+sum((q*F(opens[s]) for s,q in newhold.items()),F(0));close=newcash+sum((q*F(closes[s]) for s,q in newhold.items()),F(0))
  assert newcash>=0 and traded==after-fee
  assert row['holdings_before']==holdings and row['buy_shares']==buys and row['holdings_after']==newhold
  assert row['previous_close_session']==previous_day and row['session']==request['session']
  money=dict(previous_close_equity_usd=previous,pre_flow_open_equity_usd=before,cash_injection_usd=flow,post_flow_pre_fee_open_equity_usd=after,post_trade_open_equity_usd=traded,close_equity_usd=close,gross_buy_usd=gross,fees_usd=fee,cash_after_usd=newcash,overnight_pnl_usd=before-previous,intraday_mark_pnl_before_fees_usd=close-traded,after_flow_pnl_net_fees_usd=close-after,cash_flow_adjusted_pnl_usd=close-previous-flow)
  for k,v in money.items():assert F(row[k])==v,(request['session'],k)
  overnight=before/previous;post=close/after;factor=overnight*post;wealth*=factor
  for k,v in dict(overnight_return=overnight-1,after_flow_return=post-1,session_twr=factor-1,cumulative_twr=wealth-1).items():assert ratio(row[k])==v
  peak=max(peak,wealth);dd=max(dd,1-wealth/peak);feesum+=fee;flowsum+=flow
  cash=newcash;holdings=newhold;previous=close;previous_day=request['session']
 for k,v in dict(initial_equity_usd=initial_value,terminal_equity_usd=previous,total_cash_injection_usd=flowsum,total_fees_usd=feesum,net_dollar_pnl_excluding_injections_usd=previous-initial_value-flowsum,transaction_cost_bps=F(10)).items():assert F(account[k])==v
 assert ratio(account['chained_twr'])==wealth-1
 draw=path['drawdown'];assert ratio(draw['maximum_drawdown'])==dd and ratio(draw['initial_wealth'])==1
 assert draw['initial_observation_included'] is True and draw['observation_clock']=='INITIAL_CLOSE_THEN_EACH_SESSION_CLOSE_ONLY'
 for flag in ('cash_buffer_and_risk_gates_evaluated','dividends_modelled','corporate_actions_modelled','cash_interest_modelled','orders_executed','point_in_time_verified','promotion_allowed'):assert account[flag] is False
 return wealth-1,dd,previous

def run():
 result=load(ACCOUNT,ACCOUNT_SHA);receipt=load(ACCOUNT.parent/'publication.json',PUBLICATION_SHA)
 docs={r:load(ROOT/p,h) for r,(p,h) in PINS.items()}
 assert receipt['account_reference']==dict(path=str(ACCOUNT),sha256=ACCOUNT_SHA) and receipt['source_hashes']==result['source_hashes']
 assert receipt['status']=='PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS'
 assert result['schema']=='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1' and result['new_account_path_count']==80
 flags=('old_experiments_reexecuted','selected_plans_reselected','dividends_modelled','fx_modelled','corporate_actions_modelled','cash_interest_modelled','total_return_claimed','old_six_period_strategy_replayed','formal_dual_benchmark_comparison','point_in_time_verified','promotion_allowed','orders_executed','economic_winner_selected','identity_gaps_resolved','full_transitive_source_closure_reverified','exchange_calendar_completeness_verified','real_user_cash_claimed')
 for f in flags:assert result[f] is receipt[f] is False
 assert result['continuous_forty_scenario_strategy_claimed'] is result['annualized_return_calculated'] is False
 for r in PINS:assert result['input_references'][r]==ref(r)
 calendar=result['observed_calendar'];assert len(calendar)==107 and calendar==sorted(set(calendar))
 assert calendar[0]=='2023-03-31' and calendar[-1]=='2023-09-01'
 control={t:{q['session']:(i,q) for i,q in enumerate(v['rows'])} for t,v in docs['control']['nominal_quotes']['by_ticker'].items()}
 metadata=deepcopy(docs['control']);metadata.pop('execution')
 for v in metadata['nominal_quotes']['by_ticker'].values():v.pop('rows')
 assert metadata==result['incumbent_price_metadata_without_old_execution_or_quote_rows']
 for r in PINS:
  if r.endswith('_price'):
   doc=docs[r];assert doc['calendar']==calendar
   copy=deepcopy(doc);(copy['price_projection'] if 'price_projection' in copy else copy).pop('matrices')
   assert result['price_evidence_metadata'][r[:-6]]==copy
 observed={'lane_only':0,'control_only':0,'intersection':0};summary=[];dailycount=0
 assert len(result['rows'])==len(docs['topups']['rows'])==40
 for i,(saved,topup) in enumerate(zip(result['rows'],docs['topups']['rows'])):
  reference=topup['input_reference'];index=int(reference['json_pointer'][6:]);source=docs['inputs']['rows'][index]
  assert reference==ref('inputs',f'/rows/{index}') and saved['input_reference']==reference
  assert saved['input_row']==topup['input_row']==source and saved['scenario_id']==source['scenario_id']
  assert saved['topup_context']=={k:v for k,v in topup.items() if k not in ('evaluation','closure_records','feasible_scores')}
  assert saved['topup_context_reference']==ref('topups',f'/rows/{i}')
  pi=topup['selected_candidate_index'];plan=topup['evaluation']['branches'][0]['evaluated_plans'][pi]
  assert saved['selected_plan']==plan and plan['feasible'] is True
  assert saved['selected_plan_reference']==ref('topups',f'/rows/{i}/evaluation/branches/0/evaluated_plans/{pi}')
  mapping={s:x['ticker'] for s,x in source['securities'].items()};assert mapping==saved['security_to_ticker']
  pd=docs[source['lane']+'_price'];projection=pd.get('price_projection',pd);prefix='/price_projection' if 'price_projection' in pd else ''
  def marks(day,field,sids):
   values={};evidence={}
   for sid in sorted(sids):
    ticker=mapping[sid];observations=[]
    if ticker in projection['tickers']:
     literal=projection['matrices'][field][day][ticker]
     observations.append(dict(decimal_literal=literal,encoding='SAVED_DECIMAL_STRING_NO_RECONSTRUCTION',reference=ref(source['lane']+'_price',f'{prefix}/matrices/{field}/{day}/{ticker}')))
    if ticker in control:
     ix,q=control[ticker][day];v=q['nominal_'+field]
     assert type(v) is float and q['currency']=='USD' and q['ticker']==ticker
     observations.append(dict(decimal_literal=str(v),encoding='SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE',currency='USD',reference=ref('control',f'/nominal_quotes/by_ticker/{ticker}/rows/{ix}/nominal_{field}')))
    assert observations and len({F(x['decimal_literal']) for x in observations})==1 and F(observations[0]['decimal_literal'])>0
    observed['intersection' if len(observations)==2 else 'lane_only' if ticker in projection['tickers'] else 'control_only']+=1
    values[sid]=observations[0]['decimal_literal']
    evidence[sid]=dict(security_id=sid,ticker=ticker,chosen_observation_index=0,priority='LANE_SAVED_DECIMAL_THEN_INCUMBENT_SAVED_FLOAT_STR',observations=observations,identity_scope='FROZEN_PREPARED_SID_TICKER_ATTRIBUTION_NOT_NEW_IDENTITY_CERTIFICATION')
   return values,evidence
  event=source['cash_event'];decision=event['decision_date'];execution=event['execution_date'];assert calendar.index(execution)==calendar.index(decision)+1
  days=calendar[calendar.index(execution):];assert len(days)==saved['observed_path_session_count'] and saved['post_execution_close_intervals']==len(days)-1
  initial_marks,initial_evidence=marks(decision,'close',source['holdings']);assert saved['initial_close_quote_evidence']==initial_evidence
  initial=dict(session=decision,cash_usd=source['starting_cash_usd'],holdings=source['holdings'],close_prices=initial_marks)
  candidate=[];cashcontrol=[];assert len(saved['path_quote_evidence'])==len(days)
  for j,day in enumerate(days):
   opens,oe=marks(day,'open',plan['proposed_holdings']);closes,ce=marks(day,'close',plan['proposed_holdings'])
   assert saved['path_quote_evidence'][j]==dict(session=day,open=oe,close=ce)
   if j==0:assert {s:F(v) for s,v in opens.items()}=={s:F(v) for s,v in source['execution_prices'].items()}
   flow=event['amount_usd'] if j==0 else '0'
   candidate.append(dict(session=day,open_prices=opens,close_prices=closes,cash_injection_usd=flow,buy_shares=plan['buy_shares'] if j==0 else {}))
   cashcontrol.append(dict(session=day,open_prices={s:opens[s] for s in source['holdings']},close_prices={s:closes[s] for s in source['holdings']},cash_injection_usd=flow,buy_shares={}))
  assert set(saved['paths'])=={'candidate','same_flow_zero_trade_control'}
  c=verify_path(saved['paths']['candidate'],initial,candidate);z=verify_path(saved['paths']['same_flow_zero_trade_control'],initial,cashcontrol)
  for name,sessions in [('candidate',candidate),('same_flow_zero_trade_control',cashcontrol)]:
   a=saved['paths'][name]['account'];is_candidate=name=='candidate'
   for j,day in enumerate(a['rows']):
    assert day['holdings_after']==(plan['proposed_holdings'] if is_candidate else source['holdings'])
    assert F(day['cash_after_usd'])==(F(plan['cash_after_usd']) if is_candidate else F(source['starting_cash_usd'])+F(event['amount_usd']))
    assert F(day['fees_usd'])==(F(plan['fees_usd']) if is_candidate and j==0 else 0)
   if is_candidate:
    for k in ('gross_buy_usd','fees_usd','cash_after_usd'):assert F(a['rows'][0][k])==F(plan[k])
  differences=saved['candidate_minus_control']
  for k,v in zip(('chained_twr_difference','maximum_drawdown_difference','terminal_equity_usd_difference'),(c[0]-z[0],c[1]-z[1],c[2]-z[2])):assert ratio(differences[k])==v
  for flag in flags:assert saved[flag] is False
  assert saved['equal_horizons_across_decision_dates_claimed'] is False
  dailycount+=len(days)*2
  summary.append(dict(scenario=source['scenario_id'],session_count=len(days),candidate_twr=float(c[0]),control_twr=float(z[0]),twr_difference=float(c[0]-z[0]),candidate_dd=float(c[1]),control_dd=float(z[1]),dd_difference=float(c[1]-z[1])))
 assert dailycount==3536
 assert sha(ACCOUNT)==ACCOUNT_SHA and sha(ACCOUNT.parent/'publication.json')==PUBLICATION_SHA
 for r,(p,h) in PINS.items():assert sha(ROOT/p)==h
 return dict(account_sha256=ACCOUNT_SHA,paths=80,pairs=40,daily_rows=dailycount,quote_observations=observed,rows=summary)
if __name__=='__main__':print(json.dumps(run(),indent=2))
