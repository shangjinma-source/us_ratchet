"""Independent saved-controls Fraction review; no producer or evaluator import."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'data/cache/research/standard_cash_controls_research_20261002_v1/results.json'
PUBLICATION=RESULT.parent/'publication.json'
INPUT=ROOT/'data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json'
PINS={RESULT:'e62de22d228c3dfdb7a49192064524992985880f9121b175d749eafcc0968392',PUBLICATION:'73037d5463fed0a6f57f72c0fe28810fa74a8093ce5c17c91aa4dbc3cf091301',INPUT:'1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'}
def load(path):
 raw=path.read_bytes(); assert hashlib.sha256(raw).hexdigest()==PINS[path]; return json.loads(raw)
def ratio(d):return F(int(d['numerator']),int(d['denominator']))
def run():
 result=load(RESULT); publication=load(PUBLICATION); inputs=load(INPUT)
 assert publication['result_reference']==dict(path=str(RESULT),sha256=PINS[RESULT])
 assert publication['source_hashes']==result['source_hashes'] and publication['status']=='PUBLISHED_CONDITIONAL_INSTANT_CONTROLS_ONLY'
 flags=('orders_executed','point_in_time_verified','promotion_allowed','account_path_replayed','repair_called','evidence_gaps_resolved','real_benchmark_return_claimed','time_series_return_evaluated','economic_winner_selected','global_optimality_claimed','full_transitive_source_closure_reverified')
 for flag in flags:assert result[flag] is publication[flag] is False
 assert len(result['rows'])==result['control_count']==24
 assert result['cash_retention_count']==result['migration_control_count']==12
 assert result['main_lane_count_not_evaluated']==40 and result['parent_scenario_count']==64
 assert result['parent_source_hashes_preserved_not_reaudited']==inputs['source_hashes']
 assert result['parent_execution_contract']==inputs['original_execution_contract']
 assert result['parent_execution_contract_reference']==inputs['execution_contract_reference']
 expected=[(i,r) for i,r in enumerate(inputs['rows']) if r['lane'] in ('INCUMBENT_ADD_ONLY_CONTROL','CASH_RETENTION_CONTROL')]
 assert len(expected)==24
 checks=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
 totals=Counter();summary=[];tolerance=F(1,10**9)
 for j,((source_index,source),saved) in enumerate(zip(expected,result['rows'])):
  assert saved['input_row']==source and saved['scenario_id']==source['scenario_id']
  assert saved['input_reference']==dict(path=str(INPUT),sha256=PINS[INPUT],json_pointer=f'/rows/{source_index}')
  cash_only=source['lane']=='CASH_RETENTION_CONTROL'
  assert saved['branch_role']==source['branch_role']
  px={s:F(v) for s,v in source['execution_prices'].items()};base=source['holdings'];cash=F(source['starting_cash_usd']);flow=F(source['cash_event']['amount_usd']);fee=F(source['transaction_cost_bps'])/10000;buffer=F(source['minimum_cash_buffer_usd'])
  parameters={k:F(v) for k,v in source['risk_parameters'].items()};target={s:F(v) for s,v in source['target_weights'].items()}
  if not cash_only:
   mass=sum(target.values());target={s:v/mass for s,v in target.items()}
  evaluation=saved['evaluation']; assert len(evaluation['branches'])==1;branch=evaluation['branches'][0];limits=branch['buy_limits'];sids=sorted(limits)
  assert limits==saved['buy_limits']
  if cash_only:
   assert not limits and not target and saved['generator'] is None
   plans=[{}];assert saved['cash_control_plan_index']==0
  else:
   plans=saved['generator']['plans'];assert 1<=len(plans)<=257
   assert saved['generator']['ungenerated_count']==0
   assert saved['cash_control_plan_index'] is None
  assert len(plans)==len(branch['evaluated_plans'])==len(branch['supplied_plans'])==evaluation['evaluated_count']==branch['evaluated_count']==branch['supplied_plan_count']
  assert len({tuple(p[s] for s in sids) for p in plans})==len(plans)
  assert branch['unevaluated_supplied_plan_count']==evaluation['unevaluated_supplied_plan_count']==0
  assert evaluation['kernel_cartesian_search_evaluation_count']==0
  denominator=1
  for sid in sids:denominator*=limits[sid]+1
  assert branch['cartesian_candidate_count']==denominator and branch['unsupplied_cartesian_candidate_count']==denominator-len(plans)
  scores=[];failures=Counter();feasible_count=0
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
   totals['evaluated']+=1;totals['feasible']+=feasible;feasible_count+=feasible
   for k,v in {**finance,**gates,'ISSUER_UNIQUE':not conflicts}.items():
    if not v:failures[k]+=1
   if feasible and not cash_only:
    distance=sum((abs(weights.get(s,F(0))-target.get(s,F(0))) for s in set(weights)|set(target)),F(0))
    scores.append((distance,fees,index))
  assert branch['feasible_evaluated_count']==feasible_count
  if cash_only:
   assert saved['feasible_scores']==[] and saved['selected_supplied_plan_index'] is None
   assert saved['selection_status']=='ZERO_BUY_CONTROL_RETAINED_WITH_ORIGINAL_RISK_RESULT'
   totals['cash_controls']+=1;totals['cash_feasible']+=feasible_count
  else:
   actual=[(ratio(x['target_l1_distance']),ratio(x['fee_usd']),x['supplied_plan_index']) for x in saved['feasible_scores']]
   assert actual==scores
   assert saved['selected_supplied_plan_index']==(min(scores)[2] if scores else None)
   assert saved['selection_status']==('BEST_TARGET_DISTANCE_AMONG_SUPPLIED_FEASIBLE_PLANS' if scores else 'NO_FEASIBLE_SUPPLIED_PLAN')
   totals['migration_controls']+=1;totals['migration_selected']+=bool(scores)
  for flag in flags:assert saved[flag] is False
  summary.append({'scenario':source['scenario_id'],'evaluated':len(plans),'feasible':feasible_count,'selected_index':saved['selected_supplied_plan_index'],'cash_control_index':saved['cash_control_plan_index'],'failed_checks_nonexclusive':dict(failures)})
 for path,digest in PINS.items(): assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
 return {'totals':dict(totals),'rows':summary,'result_sha256':PINS[RESULT],'publication_sha256':PINS[PUBLICATION],'input_sha256':PINS[INPUT]}
if __name__=='__main__':print(json.dumps(run(),indent=2))
