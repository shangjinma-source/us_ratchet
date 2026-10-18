"""Independent saved topup traces and candidates; stdlib rational arithmetic only."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
RESULT=ROOT/'data/cache/research/old_holding_topup_research_20261002_v1/results.json'
PUBLICATION=RESULT.parent/'publication.json'
INPUT=ROOT/'data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json'
PINS={RESULT:'1192aa5876b8ea9e36c84ad33d88f5504df849e8612312f1886fad6b579351fb',PUBLICATION:'ed4f230d5e74ac0fb2000149caab80825e48d36cf3d7cd98a5f0858abc0fbc16',INPUT:'1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'}
def load(path):
 raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==PINS[path];return json.loads(raw)
def ratio(x):return F(int(x['numerator']),int(x['denominator']))
def verify_closure(c,seed,source,limits):
 px={s:F(v) for s,v in source['execution_prices'].items()};sids=sorted(px)
 old={s:source['holdings'].get(s,0) for s in sids};a={s:old[s]*px[s] for s in sids};D=sum(a.values())
 support=seed['support_security_ids'];x=dict(seed['seed_buy_shares'])
 cash=F(source['starting_cash_usd'])+F(source['cash_event']['amount_usd']);buffer=F(source['minimum_cash_buffer_usd']);fee=F(source['transaction_cost_bps'])/10000
 threshold=max(F(0),F(source['risk_parameters']['min_single_weight'])-F(1,10**9))
 caps={s:limits[s] if s in support else 0 for s in sids}
 assert c['holdings']==old and c['execution_prices']==source['execution_prices'] and c['seed_buy_shares']==x
 assert c['support_security_ids']==support and c['buy_limits']==limits and c['effective_buy_limits']==caps
 assert all(s in support for s in sids if old[s]>0)
 assert all(x[s]>=1 for s in support if old[s]==0) and all(x[s]==0 for s in sids if s not in support)
 assert ratio(c['effective_minimum_weight'])==threshold and ratio(c['original_tolerance'])==F(1,10**9)
 for name,key in [('starting_cash_usd','starting_cash_usd'),('cash_injection_usd',None),('transaction_cost_bps','transaction_cost_bps'),('minimum_cash_buffer_usd','minimum_cash_buffer_usd')]:
  assert F(c[name])==F(source[key] if key else source['cash_event']['amount_usd'])
 assert F(c['original_min_single_weight'])==F(source['risk_parameters']['min_single_weight'])
 def finance(q):
  gross=sum((px[s]*q[s] for s in sids),F(0));return gross,gross*fee,gross*(1+fee),cash-gross*(1+fee)
 def failure(q,stage):
  base=dict(scope='FIXED_SUPPORT_SEED_UPWARD_DOMAIN_ONLY',stage=stage,lower_bound_buy_shares=q,all_feasible_upward_plans_dominate_this_lower_bound=True)
  over=[dict(security_id=s,required_buy_shares=q[s],cap=caps[s],strict_excess_shares=q[s]-caps[s]) for s in sids if q[s]>caps[s]]
  if over:return base|dict(kind='CAP_EXCEEDED',violations=over)
  g,f,cost,left=finance(q)
  if cost>cash-buffer:
   values=dict(gross_buy_usd=g,fees_usd=f,lower_bound_total_buy_cost_usd=cost,available_after_buffer_usd=cash-buffer,strict_cost_excess_usd=cost-(cash-buffer),cash_after_usd=left,required_cash_buffer_usd=buffer)
   return base|dict(kind='CASH_BUFFER_EXCEEDED',**{k:dict(numerator=str(v.numerator),denominator=str(v.denominator)) for k,v in values.items()})
  return None
 certificate=failure(x,'SEED');terminal=certificate is not None;fixed=False
 for index,step in enumerate(c['trace']):
  assert not terminal and step['iteration']==index+1 and step['before_buy_shares']==x
  equity=D+finance(x)[0];assert ratio(step['equity_before'])==equity
  new=dict(x);assert set(step['requirements'])==set(support)
  for sid in support:
   needed=(threshold*equity-a[sid])/px[sid];ceil=-(-needed.numerator//needed.denominator)
   assert ratio(step['requirements'][sid]['minimum_additional_shares_rational'])==needed
   assert step['requirements'][sid]['ceil_additional_shares']==ceil
   new[sid]=max(x[sid],ceil,0)
  assert step['next_buy_shares']==new
  g,f,cost,left=finance(new)
  for k,v in dict(gross_buy_usd=g,fees_usd=f,total_buy_cost_usd=cost,cash_after_usd=left).items():assert ratio(step[k])==v
  fixed=new==x;x=new;certificate=failure(x,'SYNCHRONOUS_UPDATE');terminal=certificate is not None or fixed
 assert c['iterations']==len(c['trace'])<=c['max_iterations']==100
 status='PROVEN_INFEASIBLE_UPWARD_DOMAIN' if certificate else 'FIXED_POINT' if fixed else 'UNKNOWN_ITERATION_BUDGET'
 assert c['status']==status and c['failure_certificate']==certificate
 assert c['last_iterate_buy_shares']==x and c['buy_shares']==(x if status=='FIXED_POINT' else None)
 assert c['minimum_weight_fixed_point_verified'] is (status=='FIXED_POINT')
 assert c['seed_upward_domain_necessarily_infeasible'] is (certificate is not None)
 assert c['least_feasible_buy_vector_in_seed_upward_domain_verified'] is (status=='FIXED_POINT')
 if not terminal:assert len(c['trace'])==c['max_iterations']
 g,f,cost,left=finance(x)
 for k,v in dict(gross_buy_usd=g,fees_usd=f,total_buy_cost_usd=cost,cash_after_usd=left,stock_equity_usd=D+g).items():assert ratio(c['last_iterate_financials'][k])==v
 minchecks={s:a[s]+px[s]*x[s]>=threshold*(D+g) for s in support}
 assert c['last_iterate_min_weight_checks']==minchecks
 if fixed and not certificate:assert all(minchecks.values()) and left>=buffer
 for flag in ('all_risks_evaluated','issuer_uniqueness_evaluated','eligibility_inferred','global_optimality_claimed','full_integer_space_infeasibility_claimed','orders_executed','point_in_time_verified','promotion_allowed'):assert c[flag] is False
 return status

def run():
 result=load(RESULT);publication=load(PUBLICATION);inputs=load(INPUT)
 assert publication['result_reference']==dict(path=str(RESULT),sha256=PINS[RESULT]) and publication['source_hashes']==result['source_hashes']
 assert publication['status']=='PUBLISHED_CONDITIONAL_TOPUPS_ONLY'
 selected=[(i,r) for i,r in enumerate(inputs['rows']) if r['branch_role']=='MAIN_LANE'];assert len(selected)==len(result['rows'])==result['scenario_count']==40
 assert result['controls_evaluated'] is False
 flags=('orders_executed','point_in_time_verified','promotion_allowed','formal_eligibility_verified','fork_executable','global_optimality_claimed','economic_winner_selected','time_series_return_evaluated','identity_gaps_resolved','old_experiments_reexecuted','full_transitive_source_closure_reverified')
 for flag in flags:assert result[flag] is publication[flag] is False
 totals=Counter();statuses=Counter();summary=[];tolerance=F(1,10**9)
 checks=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
 for j,((input_index,source),saved) in enumerate(zip(selected,result['rows'])):
  assert source==saved['input_row'] and source['scenario_id']==saved['scenario_id']
  assert saved['input_reference']==dict(path=str(INPUT),sha256=PINS[INPUT],json_pointer=f'/rows/{input_index}')
  domain=saved['domain'];px={s:F(v) for s,v in source['execution_prices'].items()};base=source['holdings'];cash=F(source['starting_cash_usd']);flow=F(source['cash_event']['amount_usd']);fee=F(source['transaction_cost_bps'])/10000;buffer=F(source['minimum_cash_buffer_usd'])
  parameters={k:F(v) for k,v in source['risk_parameters'].items()};target={s:F(v) for s,v in source['target_weights'].items()};targetsum=sum(target.values());target={s:v/targetsum for s,v in target.items()}
  grossbudget=max(F(0),cash+flow-buffer)/(1+fee);limits={s:grossbudget//p for s,p in px.items()};sids=sorted(limits)
  assert domain['buy_limits']==limits and ratio(domain['gross_budget_usd'])==grossbudget
  assert domain['conditional_research_buy_ids']==sids and domain['old_positive_ids']==sorted(s for s,q in base.items() if q>0)
  new=sorted(set(target)-set(domain['old_positive_ids']));assert domain['new_target_ids']==new
  assert ratio(domain['original_target_sum'])==targetsum and {s:ratio(v) for s,v in domain['normalized_original_targets'].items()}==target
  assert len(domain['supports'])==2**len(new)
  for mask,support in enumerate(domain['supports']):
   ids=sorted(set(domain['old_positive_ids'])|{s for i,s in enumerate(new) if mask&(1<<i)})
   assert support['support_index']==mask and support['support_security_ids']==ids
   issuers={}
   for s in ids:issuers.setdefault(source['securities'][s]['issuer_id'],[]).append(s)
   conflicts={k:v for k,v in issuers.items() if len(v)>1}
   assert support['issuer_conflicts']==conflicts and support['structurally_excluded'] is bool(conflicts)
   assert support['seed_count']==sum(x['support_index']==mask for x in domain['seeds'])
   if conflicts:assert support['seed_count']==0
  assert saved['unprocessed_seed_count']==len(domain['seeds'])-len(saved['closure_records'])==0
  plans=[];seen={};localstatus=Counter()
  for seed_index,(seed,record) in enumerate(zip(domain['seeds'],saved['closure_records'])):
   assert record['seed_index']==seed_index and seed['support_security_ids']==domain['supports'][seed['support_index']]['support_security_ids']
   assert not domain['supports'][seed['support_index']]['structurally_excluded']
   status=verify_closure(record['closure'],seed,source,limits);statuses[status]+=1;localstatus[status]+=1
   if status=='FIXED_POINT':
    plan=record['closure']['buy_shares'];key=tuple(plan[s] for s in sids)
    if key not in seen:seen[key]=len(plans);plans.append(plan)
    assert record['candidate_index']==seen[key]
   else:assert record['candidate_index'] is None
  evaluation=saved['evaluation'];assert len(evaluation['branches'])==1;branch=evaluation['branches'][0]
  assert branch['buy_limits']==limits and branch['branch_id']==source['scenario_id']
  assert len(plans)==len(branch['evaluated_plans'])==len(branch['supplied_plans'])==branch['evaluated_count']==evaluation['evaluated_count']
  assert evaluation['unevaluated_supplied_plan_count']==branch['unevaluated_supplied_plan_count']==0
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
  actual=[(ratio(x['distance']),ratio(x['fees_usd']),x['candidate_index']) for x in saved['feasible_scores']]
  assert actual==scores and branch['feasible_evaluated_count']==len(scores)
  assert saved['selected_candidate_index']==(min(scores)[2] if scores else None)
  totals['selected']+=bool(scores)
  assert saved['original_allowed_buy_security_ids']==source['allowed_buy_security_ids']
  assert saved['target_weights_changed'] is saved['cash_must_be_fully_invested'] is False
  assert saved['new_buy_domain_is_research_assumption'] is True
  for flag in flags:assert saved[flag] is False
  summary.append(dict(scenario=source['scenario_id'],seeds=len(domain['seeds']),closure_statuses=dict(localstatus),evaluated=len(plans),feasible=len(scores),selected=saved['selected_candidate_index'],failed_checks_nonexclusive=dict(failures)))
 for path,digest in PINS.items():assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
 return dict(totals=dict(totals),closure_statuses=dict(statuses),rows=summary,result_sha256=PINS[RESULT])
if __name__=='__main__':print(json.dumps(run(),indent=2))
