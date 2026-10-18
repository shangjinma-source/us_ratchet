"""Read the saved repair batch with Fraction arithmetic; no production imports."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'data/cache/research/first_period_standard_cash_inputs_20261002_v1/inputs.json'
OLD=ROOT/'data/cache/research/first_period_cash_neighbor_research_20261002_v1/results.json'
RESULT=ROOT/'data/cache/research/first_period_cash_repair_research_20261002_v1/results.json'
INPUT_SHA='f583f6e55efeb78f0fc1c761bb2027076274012c30a7dda528ef6dee1a3004ee'
OLD_SHA='dfd434e79c5f9f1242a1a2d11d7cbe7bf9d830f6d5e3e380225a64ff31dcdbdf'
RESULT_SHA='61b9e1e66c18b74fb503e1de57a292514e9467ec07215eaa7126055ae2b395b7'
def load(path,digest):
 raw=path.read_bytes(); assert hashlib.sha256(raw).hexdigest()==digest; return json.loads(raw)
def ratio(value): return F(int(value['numerator']),int(value['denominator']))
def run():
 inputs=load(INPUT,INPUT_SHA); old=load(OLD,OLD_SHA); result=load(RESULT,RESULT_SHA)
 assert len(inputs['rows'])==len(old['rows'])==len(result['rows'])==8
 checks=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
 tolerance=F(1,10**9); totals=Counter(); summary=[]
 assert result['old_candidate_evaluations_repeated']==0
 for flag in ('source_identity_gaps_resolved','full_ndx_search_claimed','account_replayed','orders_executed','point_in_time_verified','promotion_allowed'): assert result[flag] is False
 for j,(source,previous,saved) in enumerate(zip(inputs['rows'],old['rows'],result['rows'])):
  assert source['scenario_id']==previous['scenario_id']==saved['scenario_id']
  assert saved['input_reference']==dict(path=str(INPUT),sha256=INPUT_SHA,json_pointer=f'/rows/{j}')
  assert saved['previous_result_reference']==dict(path=str(OLD),sha256=OLD_SHA,json_pointer=f'/rows/{j}')
  px={s:F(v) for s,v in source['execution_prices'].items()}; base=source['holdings']; cash=F(source['starting_cash_usd']); flow=F(source['cash_event']['amount_usd']); fee=F(source['transaction_cost_bps'])/10000; buffer=F(source['minimum_cash_buffer_usd'])
  parameters={k:F(v) for k,v in source['risk_parameters'].items()}; target={s:F(v) for s,v in source['target_weights'].items()}; mass=sum(target.values()); target={s:v/mass for s,v in target.items()}
  evaluation=saved['evaluation']; assert len(evaluation['branches'])==1; branch=evaluation['branches'][0]; limits=branch['buy_limits']; sids=sorted(limits)
  generation=saved['repair_generation']; plans=[p['buy_shares'] for p in generation['generated_plans']]
  prior=previous['evaluation']['branches'][0]['evaluated_plans']; excluded=[p['buy_shares'] for p in prior]
  key=lambda p:tuple(p[s] for s in sids)
  assert limits==previous['evaluation']['branches'][0]['buy_limits']
  assert generation['excluded_plans']==excluded and generation['seed_plans']==[p for p in excluded if any(p.values())]
  assert len(excluded)==17 and len(generation['seed_plans'])==16
  assert not(set(map(key,plans)) & set(map(key,excluded))) and len(set(map(key,plans)))==len(plans)
  assert len(plans)==generation['generated_plan_count']==generation['distinct_remaining_plan_count']==branch['supplied_plan_count']==branch['evaluated_count']==evaluation['evaluated_count']
  assert generation['ungenerated_plan_count']==branch['unevaluated_supplied_plan_count']==evaluation['unevaluated_supplied_plan_count']==0
  assert generation['total_move_attempts']==sum(generation[k] for k in ('out_of_bounds_attempt_count','duplicate_valid_coordinate_attempt_count','unique_excluded_coordinate_count','distinct_remaining_plan_count'))
  assert evaluation['kernel_cartesian_search_evaluation_count']==0
  denominator=1
  for sid in sids: denominator*=limits[sid]+1
  assert branch['cartesian_candidate_count']==denominator and branch['unsupplied_cartesian_candidate_count']==denominator-len(plans)
  scores=[]; failures=Counter()
  assert len(plans)==len(branch['evaluated_plans'])==len(branch['supplied_plans'])
  for index,(buy,row,supplied) in enumerate(zip(plans,branch['evaluated_plans'],branch['supplied_plans'])):
   assert set(buy)==set(limits) and all(type(q) is int and 0<=q<=limits[s] for s,q in buy.items())
   assert row['buy_shares']==supplied['buy_shares']==buy and row['supplied_plan_index']==index
   rank=0
   for sid in sids:rank=rank*(limits[sid]+1)+buy[sid]
   assert rank==row['original_cartesian_rank']==supplied['cartesian_rank']
   holdings={s:base.get(s,0)+buy.get(s,0) for s in set(base)|set(buy)}
   assert row['proposed_holdings']==holdings
   gross=sum((px[s]*q for s,q in buy.items()),F(0));fees=gross*fee;remaining=cash+flow-gross-fees
   values={s:q*px[s] for s,q in holdings.items() if q>0};stock=sum(values.values(),F(0));equity=remaining+stock;initial=cash+sum((q*px[s] for s,q in base.items()),F(0))
   for key,value in {'gross_buy_usd':gross,'fees_usd':fees,'cash_after_usd':remaining,'equity_after_usd':equity,'cash_flow_adjusted_pnl_usd':equity-initial-flow}.items():assert F(row[key])==value,(j,index,key)
   assert equity-initial-flow==-fees
   finance={'NONNEGATIVE_CASH':remaining>=0,'CASH_BUFFER':remaining>=buffer}
   assert row['financial_checks']==finance and all(type(v) is bool for v in row['financial_checks'].values())
   groups={};chains={}
   for sid in sorted(values):groups.setdefault(source['securities'][sid]['issuer_id'],[]).append(sid)
   conflicts={k:v for k,v in groups.items() if len(v)>1}
   assert row['issuer_conflicts']==conflicts and row['issuer_unique'] is (not conflicts)
   weights={s:v/stock for s,v in values.items()} if stock else {}
   if stock:
    ordered=sorted(weights.values(),reverse=True);effective=1/sum((v*v for v in weights.values()),F(0))
    for sid,value in weights.items():
     chain=source['securities'][sid]['risk_chain'];chains[chain]=chains.get(chain,F(0))+value
    gates=dict(zip(checks,(ordered[0]<=parameters['max_single_weight']+tolerance,ordered[-1]>=parameters['min_single_weight']-tolerance,sum(ordered[:3])<=parameters['top_weight_cap']+tolerance,effective>=parameters['minimum_effective_n_ratio']*len(weights)-tolerance,max(chains.values())<=parameters['risk_chain_top1_cap']+tolerance)))
    assert F(row['risk']['effective_n'])==effective and row['risk']['reason'] is None
   else:
    gates=dict.fromkeys(checks,False);assert row['risk']['effective_n'] is None and row['risk']['reason']=='ALL_CASH'
   assert row['risk']['checks']==gates and all(type(v) is bool for v in row['risk']['checks'].values())
   assert row['risk']['all_passed'] is all(gates.values()) and row['risk']['positive_holding_count']==len(weights)
   assert {s:F(v) for s,v in row['risk']['weights'].items()}==weights
   feasible=all(finance.values()) and all(gates.values()) and not conflicts
   assert row['feasible'] is feasible
   totals['evaluated']+=1;totals['feasible']+=feasible
   for k,v in {**finance,**gates,'ISSUER_UNIQUE':not conflicts}.items():
    if not v:failures[k]+=1
   if feasible:
    distance=sum((abs(weights.get(s,F(0))-target.get(s,F(0))) for s in set(weights)|set(target)),F(0))
    scores.append((distance,fees,index))
  assert branch['feasible_evaluated_count']==len(scores)
  merged=[(distance,fees,1,index) for distance,fees,index in scores]
  # Old saved plans are used for ranking only, never re-evaluated for risk or finances.
  for index,plan in enumerate(prior):
   if plan['feasible']:
    values={s:q*px[s] for s,q in plan['proposed_holdings'].items()}; stock=sum(values.values())
    distance=sum((abs(values.get(s,F(0))/stock-target.get(s,F(0))) for s in set(values)|set(target)),F(0))
    merged.append((distance,F(plan['fees_usd']),0,index))
  winner=min(merged) if merged else None
  selected=saved['selected']
  assert saved['combined_feasible_count']==len(merged) and saved['combined_candidate_count']==17+len(plans)
  assert saved['previous_evaluation_repeated'] is False and saved['previous_candidate_count']==17
  assert saved['combined_tie_order']==['EXACT_L1','EXACT_FEES','PREVIOUS_BATCH_FIRST','PLAN_INDEX']
  if winner is None: assert selected is None
  else:
   assert (ratio(selected['target_l1_distance']),ratio(selected['fee_usd']),0 if selected['source']=='PREVIOUS_BATCH' else 1,selected['plan_index'])==winner
   assert selected['source'] in ('PREVIOUS_BATCH','NEW_REPAIR_BATCH')
  for flag in ('all_integer_space_exhausted','economic_winner_selected','orders_executed','time_series_return_evaluated','point_in_time_verified','promotion_allowed'): assert saved[flag] is False
  totals['selected']+=selected is not None
  summary.append({'scenario':source['scenario_id'],'new_evaluated':len(plans),'new_feasible':len(scores),'combined_feasible':len(merged),'selected':selected,'failed_checks_nonexclusive':dict(failures)})
 assert totals==dict(evaluated=1280,feasible=400,selected=8),totals
 for path,digest in ((INPUT,INPUT_SHA),(OLD,OLD_SHA),(RESULT,RESULT_SHA)): assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
 return {'totals':dict(totals),'rows':summary,'new_result_sha256':RESULT_SHA,'old_result_sha256':OLD_SHA,'input_sha256':INPUT_SHA}
if __name__=='__main__': print(json.dumps(run(),indent=2))
