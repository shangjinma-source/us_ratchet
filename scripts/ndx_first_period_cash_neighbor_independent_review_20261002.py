"""One saved-result review using stdlib Fraction only; never executes a producer."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'data/cache/research/first_period_cash_neighbor_research_20261002_v1/results.json'
INPUT=ROOT/'data/cache/research/first_period_standard_cash_inputs_20261002_v1/inputs.json'
RESULT_SHA='dfd434e79c5f9f1242a1a2d11d7cbe7bf9d830f6d5e3e380225a64ff31dcdbdf'
INPUT_SHA='f583f6e55efeb78f0fc1c761bb2027076274012c30a7dda528ef6dee1a3004ee'
def load(path,sha):
 raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==sha;return json.loads(raw)
def ratio(d):return F(int(d['numerator']),int(d['denominator']))
def run():
 result=load(RESULT,RESULT_SHA);inputs=load(INPUT,INPUT_SHA)
 assert len(result['rows'])==len(inputs['rows'])==8
 assert result['input_references']['inputs']=={'path':str(INPUT),'sha256':INPUT_SHA}
 for flag in ('account_path_replayed','full_ndx_search_claimed','orders_executed','point_in_time_verified','promotion_allowed'):assert result[flag] is False
 checks=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
 summary=[]; totals=Counter(); tolerance=F(1,10**9)
 for j,(source,saved) in enumerate(zip(inputs['rows'],result['rows'])):
  assert source['scenario_id']==saved['scenario_id']
  assert saved['input_reference']==dict(result['input_references']['inputs'],json_pointer='/rows/'+str(j))
  px={s:F(v) for s,v in source['execution_prices'].items()};base=source['holdings'];cash=F(source['starting_cash_usd']);flow=F(source['cash_event']['amount_usd']);fee=F(source['transaction_cost_bps'])/10000;buffer=F(source['minimum_cash_buffer_usd'])
  parameters={k:F(v) for k,v in source['risk_parameters'].items()};target={s:F(v) for s,v in source['target_weights'].items()};targetsum=sum(target.values());target={s:v/targetsum for s,v in target.items()}
  evaluation=saved['evaluation'];assert len(evaluation['branches'])==1;branch=evaluation['branches'][0];limits=branch['buy_limits'];sids=sorted(limits)
  plans=saved['generator']['plans'];assert len(plans)==len(branch['evaluated_plans'])==branch['supplied_plan_count']==branch['evaluated_count']==17
  assert len({tuple(p[s] for s in sids) for p in plans})==17
  assert plans[0]==dict.fromkeys(sids,0)
  assert branch['unevaluated_supplied_plan_count']==evaluation['unevaluated_supplied_plan_count']==0
  assert saved['generator']['ungenerated_count']==0 and saved['generator']['distinct_supplied_domain_count']==17
  denominator=1
  for s in sids:denominator*=limits[s]+1
  assert branch['cartesian_candidate_count']==evaluation['cartesian_candidate_count']==denominator
  assert branch['unsupplied_cartesian_candidate_count']==denominator-17
  assert evaluation['kernel_cartesian_search_evaluation_count']==0
  scores=[];failures=Counter()
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
  actual=[(ratio(x['target_l1_distance']),ratio(x['fee_usd']),x['supplied_plan_index']) for x in saved['feasible_scores']]
  assert actual==scores
  assert branch['feasible_evaluated_count']==len(scores)
  chosen=min(scores)[2] if scores else None
  assert saved['selected_supplied_plan_index']==chosen
  assert saved['selection_status']==('BEST_TARGET_DISTANCE_AMONG_SUPPLIED_FEASIBLE_PLANS' if scores else 'NO_FEASIBLE_SUPPLIED_PLAN')
  for flag in ('economic_winner_selected','global_optimality_claimed','orders_executed','point_in_time_verified','promotion_allowed','time_series_return_evaluated'):assert saved[flag] is False
  totals['selected']+=chosen is not None
  summary.append({'scenario':source['scenario_id'],'evaluated':17,'feasible':len(scores),'selected_index':chosen,'selected_l1':str(min(scores)[0]) if scores else None,'cartesian_domain':denominator,'unsupplied':denominator-17,'failed_check_counts_nonexclusive':dict(failures)})
 assert totals=={'evaluated':136,'feasible':40,'selected':6}
 assert hashlib.sha256(RESULT.read_bytes()).hexdigest()==RESULT_SHA and hashlib.sha256(INPUT.read_bytes()).hexdigest()==INPUT_SHA
 return {'totals':dict(totals),'rows':summary,'result_sha256':RESULT_SHA,'inputs_sha256':INPUT_SHA}
if __name__=='__main__':print(json.dumps(run(),indent=2))
