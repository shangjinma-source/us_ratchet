"""Independent saved single-plan arithmetic oracle; no producer/evaluator imports."""
import argparse,hashlib,json,os,re
from copy import deepcopy
from decimal import Context,Decimal,localcontext
from fractions import Fraction
from math import prod
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
ATTEMPTS=ROOT/'data/cache/research/cash_topup_neighbor_evaluation_20261003_v1'
OUTPUT=ROOT/'data/cache/research/cash_topup_neighbor_single_evaluation_independent_readback_20261003_v1'
POSTCHECK_SHA='7df4aa5f7285af105bcca01cafa2e132c0c0a3b15eca8bc0d7ae9b78615a0a57'
PRODUCER=ROOT/'scripts/ndx_cash_topup_neighbor_single_evaluation_20261003.py'
PRODUCER_SHA='6328a40a4c07f90b10b120ef348f924cf7cfa0dda9b12e63a80939e183c651ba'
PREP=ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1'
BOUND={
'preparation':(str(PREP/'preparation.json'),'04cf54101f56303cc656e60079f1434661845da6e13c6c7d23305f3e9f1dde2b'),
'publication':(str(PREP/'publication.json'),'dbe1e731c02293dab4a5cca4f0fa7fbf84367cd201dbf90b9e703cab1fd86b53'),
'audit':(str(ROOT/'data/cache/research/cash_topup_neighbor_preparation_independent_readback_20261003_v1/independent_readback.json'),'c29c98c5c48d61e2533c7a587291932eda3b5776d81a9d0288a75a6b7d891ce8')}
PINS={
'evaluator':('backtest/ndx_explicit_cash_plan_evaluation_research.py','bc98beb6afdf04110c61857aef4b573a3840811076d729d4efc022d9b6523191'),
'kernel':('backtest/ndx_conditional_new_cash_fork_research.py','5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f'),
'preparation_reader':('scripts/ndx_cash_topup_neighbor_preparation_independent_readback_20261003.py','483a11cbb1037ec9c30ff01ded864e883c2570110b0fe03660d209b3d2fe2f76'),
'original_score_semantics':('scripts/ndx_old_holding_topup_research_20261002.py','3898ab695053108742acc8e13d3fce7c81231f72d81d12c37156e07211c8723c')}
FLAGS=('old_search_reexecuted','old_audit_reexecuted','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_transitive_source_closure_reverified','full_integer_domain_exhausted','economic_winner_selected','target_weights_changed','holdings_sold','issuer_eligibility_verified','new_dated_77_pool_used','retry_allowed')
RISK_KEYS=('max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')
CHECKS=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def decode(b):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON');out[k]=v
        return out
    def bad(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=bad)
def ref(path,h):return dict(path=str(path),sha256=h)
def number(v):
    require(type(v) in (str,int,Decimal),'Exact decimal input, not float/bool');d=Decimal(v)
    require(d.is_finite() and len(d.as_tuple().digits)<=40 and abs(d.as_tuple().exponent)<=40 and abs(d)<=Decimal('1e40'),'Bounded decimal');return d

def risk(shares,prices,securities,params):
    amounts={s:q*Fraction(prices[s]) for s,q in sorted(shares.items()) if q>0};total=sum(amounts.values(),Fraction())
    if not total:return dict(checks=dict.fromkeys(CHECKS,False),all_passed=False,reason='ALL_CASH',positive_holding_count=0,weights={},effective_n=None)
    w={s:v/total for s,v in amounts.items()};ordered=sorted(w.values(),reverse=True);neff=1/sum((v*v for v in w.values()),Fraction());chain={}
    for s,v in w.items():chain[securities[s]['risk_chain']]=chain.get(securities[s]['risk_chain'],Fraction())+v
    tol=Fraction(1,10**9);checks=dict(zip(CHECKS,(ordered[0]<=params['max_single_weight']+tol,ordered[-1]>=params['min_single_weight']-tol,sum(ordered[:3])<=params['top_weight_cap']+tol,neff>=params['minimum_effective_n_ratio']*len(w)-tol,max(chain.values())<=params['risk_chain_top1_cap']+tol)))
    return dict(checks=checks,all_passed=all(checks.values()),reason=None,positive_holding_count=len(w),weights={s:str(v) for s,v in w.items()},effective_n=str(neff))
def conflicts(shares,securities):
    groups={}
    for s,q in sorted(shares.items()):
        if q:groups.setdefault(securities[s]['issuer_id'],[]).append(s)
    return {i:ss for i,ss in sorted(groups.items()) if len(ss)>1}

def independent_result(arguments):
    with localcontext(Context(prec=160)):
        a=arguments['evaluation_inputs'];branch=a['branches'];require(len(branch)==1 and a['max_evaluations']==1 and type(a['max_evaluations']) is int,'One explicit plan')
        name=branch[0]['branch_id'];limits=branch[0]['buy_limits'];plans=arguments['plans_by_branch'];require(set(plans)=={name} and len(plans[name])==1,'One explicit branch')
        buy=plans[name][0];base=a['holdings'];require(set(buy)==set(limits),'Full buy vector')
        for s,q in base.items():require(type(q) is int and 0<=q<=10**12,'Whole old shares')
        for s,q in buy.items():require(type(q) is int and type(limits[s]) is int and 0<=q<=limits[s]<=10**12,'Saved integer caps')
        require(set(a['securities'])==set(a['execution_prices'])==set(base)|set(buy),'Full old/buy metadata union')
        marks={s:number(v) for s,v in a['execution_prices'].items()};require(all(v>0 for v in marks.values()),'Positive marks')
        params={k:Fraction(number(v)) for k,v in a['risk_parameters'].items()};require(set(params)==set(RISK_KEYS) and all(0<v<=1 for v in params.values()),'Original risk params')
        cash=number(a['starting_cash_usd']);amount=number(a['cash_event']['amount_usd']);fee=number(a['transaction_cost_bps']);buffer=number(a['minimum_cash_buffer_usd']);require(min(cash,amount,fee,buffer)>=0 and fee<=10000,'Original finance bounds')
        initial=cash+sum((marks[s]*q for s,q in base.items()),Decimal(0));after=dict(base)
        for s,q in buy.items():after[s]=after.get(s,0)+q
        gross=sum((marks[s]*q for s,q in buy.items()),Decimal(0));fees=gross*fee/Decimal(10000);remaining=cash+amount-gross-fees;equity=remaining+sum((marks[s]*q for s,q in after.items()),Decimal(0))
        assessed=risk(after,marks,a['securities'],params);duplicate=conflicts(after,a['securities']);financial=dict(NONNEGATIVE_CASH=remaining>=0,CASH_BUFFER=remaining>=buffer)
        rank=0
        for s in sorted(limits):rank=rank*(limits[s]+1)+buy[s]
        plan=dict(supplied_plan_index=0,original_cartesian_rank=rank,buy_shares=dict(sorted(buy.items())),proposed_holdings=dict(sorted(after.items())),gross_buy_usd=str(gross),fees_usd=str(fees),cash_after_usd=str(remaining),equity_after_usd=str(equity),cash_flow_adjusted_pnl_usd=str(equity-initial-amount),financial_checks=financial,risk=assessed,issuer_conflicts=duplicate,issuer_unique=not duplicate,feasible=all(financial.values()) and assessed['all_passed'] and not duplicate)
        denominator=prod(v+1 for v in limits.values());event=dict(a['cash_event'],amount_usd=str(amount))
        validation=dict(schema='CONDITIONAL_NEW_CASH_BOUNDED_FORK_V1',cash_event=event,starting_cash_usd=str(cash),starting_holdings=dict(sorted(base.items())),initial_equity_usd=str(initial),risk_parameters={k:str(v) for k,v in params.items()},transaction_cost_bps=str(fee),minimum_cash_buffer_usd=str(buffer),baseline_risk=risk(base,marks,a['securities'],params),baseline_issuer_conflicts=conflicts(base,a['securities']),candidate_count=denominator,evaluated_count=0,branches=[dict(branch_id=name,buy_limits=dict(sorted(limits.items())),candidate_count=denominator,evaluated_count=0,unevaluated_count=denominator,status='BUDGET_LIMITED',feasible_evaluated_count=0,candidates=[])],order_version='INPUT_BRANCH_ORDER_SORTED_SID_QUANTITY_LEX_V1',risk_denominator='POSITIVE_INVESTED_STOCK_ONLY_CASH_CHECKED_SEPARATELY',risk_arithmetic='EXACT_RATIONAL_ORIGINAL_1E_MINUS_9_TOLERANCE_NOT_FLOAT_BITWISE',risk_tolerance='1e-9',global_optimality_claimed=False,parameter_authority='SYNTHETIC_CALLER_SUPPLIED_NOT_SOURCE_BOUND',security_resource_cap=256,security_resource_cap_is_eligibility_or_k_limit=False,cash_event_timing='BEFORE_EXECUTION_MARK_BUYS_NO_INTERVENING_MARK_MODEL',full_integer_space_infeasibility_claimed=False,orders_executed=False,point_in_time_verified=False,promotion_allowed=False,historical_experiment_executed=False,return_series_calculated=False,time_series_return_evaluated=False)
        result=dict(schema='EXPLICIT_BUY_ONLY_CASH_PLAN_EVALUATION_V1',contract_validation_without_search=validation,cash_event=event,starting_holdings=dict(sorted(base.items())),starting_cash_usd=str(cash),initial_equity_usd=str(initial),risk_parameters=validation['risk_parameters'],transaction_cost_bps=str(fee),minimum_cash_buffer_usd=str(buffer),max_evaluations=1,cartesian_candidate_count=denominator,supplied_plan_count=1,evaluated_count=1,unevaluated_supplied_plan_count=0,branches=[dict(branch_id=name,buy_limits=limits,cartesian_candidate_count=denominator,supplied_plan_count=1,evaluated_count=1,unevaluated_supplied_plan_count=0,unsupplied_cartesian_candidate_count=denominator-1,status='ALL_SUPPLIED_PLANS_EVALUATED',supplied_plans=[dict(buy_shares=dict(sorted(buy.items())),cartesian_rank=rank)],evaluated_plans=[plan],feasible_evaluated_count=int(plan['feasible']))],evaluation_order='CALLER_BRANCH_ORDER_THEN_CALLER_PLAN_ORDER_V1',kernel_validation_call_count=1,kernel_cartesian_search_evaluation_count=0,engineering_max_supplied_plans=10000,supplied_plans_are_full_space_claim=False,global_optimality_claimed=False,full_integer_space_infeasibility_claimed=False,economic_winner_selected=False,orders_executed=False,point_in_time_verified=False,promotion_allowed=False,historical_experiment_executed=False,time_series_return_evaluated=False,parameter_authority='CALLER_SUPPLIED_NOT_SOURCE_BOUND')
        return result

def inspect_saved(started,raw,post):
    require(started['schema']=='CASH_TOPUP_SINGLE_EVALUATION_STARTED_V1' and raw['schema']=='CASH_TOPUP_SINGLE_EVALUATION_RAW_V1' and post['schema']=='CASH_TOPUP_SINGLE_EVALUATION_POSTCHECK_V1','Saved schemas')
    for obj in (started,raw,post):
        require(obj['task_id']==started['task_id'],'Task link')
        for k in FLAGS:require(obj[k] is False,'Saved authority')
    exact(raw['explicit_evaluator_call_attempt_count'],1,'Exactly one attempt');exact(raw['source_hashes'],started['source_hashes'],'Raw source map');exact(post['source_hashes'],started['source_hashes'],'Post source map');exact(post['evaluation_error'],raw['error'],'Original exception')
    for error in (raw['error'],post['validation_error']):
        if error is not None:require(type(error) is dict and set(error)=={'type','message'} and all(type(error[k]) is str for k in error),'Saved exception shape')
    if raw['error'] is not None:
        require(raw['result'] is None and type(raw['error']) is dict and set(raw['error'])=={'type','message'},'No invented returned result');exact(raw['returned_evaluation_count'],0,'Exception return count')
        outcome='VALIDATION_FAILURE' if post['validation_error'] is not None else 'EVALUATION_EXCEPTION';score=None;reason='UNACCEPTED_RETURNED_EVALUATION' if outcome=='VALIDATION_FAILURE' else 'NO_RETURNED_EVALUATION';verified=False
    else:
        exact(raw['returned_evaluation_count'],1,'Returned count')
        if post['validation_error'] is not None:outcome='VALIDATION_FAILURE';score=None;reason='UNACCEPTED_RETURNED_EVALUATION';verified=False
        else:
            result=independent_result(started['evaluation_arguments']);exact(raw['result'],result,'Independent complete arithmetic/zero-search metadata')
            p=result['branches'][0]['evaluated_plans'][0];outcome='FEASIBLE' if p['feasible'] else 'INFEASIBLE';verified=True;score=None
            if p['feasible']:
                r=started['original_contract']['contract']['original_input_row'];weights={s:Fraction(v) for s,v in r['target_weights'].items()};total=sum(weights.values(),Fraction());require(total>0,'Positive original target sum');values={s:q*Fraction(r['execution_prices'][s]) for s,q in p['proposed_holdings'].items()};stocks=sum(values.values(),Fraction());require(stocks>0,'Positive feasible stocks')
                distance=sum((abs(values.get(s,0)/stocks-weights.get(s,0)/total) for s in set(values)|set(weights)),Fraction());f=Fraction(p['fees_usd']);score=dict(distance=dict(numerator=distance.numerator,denominator=distance.denominator),fees_usd=dict(numerator=f.numerator,denominator=f.denominator))
            reason=None if score is not None else 'ORIGINAL_POLICY_SCORES_ONLY_FEASIBLE_PLANS'
    exact(post['outcome'],outcome,'Technical outcome not infeasible');exact(post['original_target_stock_weight_l1'],score,'Independent L1');exact(post['score_absence_reason'],reason,'Original score scope')
    require(post['status']==('ACCEPTED_SINGLE_PLAN_DIAGNOSTIC' if verified else 'TECHNICAL_FAILURE_NOT_INFEASIBILITY'),'Acceptance status')
    return dict(attempt_outcome=outcome,returned_arithmetic_independently_verified=verified,original_target_stock_weight_l1=score,technical_failure_preserved=not verified)

def readback(task_id,postcheck_reference,*,execute=False):
    require(type(execute) is bool and execute and type(POSTCHECK_SHA) is str,'Actual postcheck anchor pending/explicit opt in')
    require(type(task_id) is str and re.fullmatch('[a-f0-9]{64}',task_id),'Task SHA');directory=ATTEMPTS/task_id;out=OUTPUT/task_id;require(not out.exists(),'No readback retry')
    exact(postcheck_reference,ref(directory/'postcheck.json',POSTCHECK_SHA),'External saved postcheck anchor')
    sources={str(SOURCE):LOADED,str(PRODUCER):PRODUCER_SHA,**{str(ROOT/p):h for p,h in PINS.values()}}
    def read(r):
        require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Exact source reference')
        b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed source bytes');require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source collision');sources[r['path']]=r['sha256'];return b
    refs={k:ref(p,h) for k,(p,h) in BOUND.items()};docs={k:decode(read(r)) for k,r in refs.items()};prep,pub,audit=(docs[k] for k in ('preparation','publication','audit'))
    require(prep['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_V1' and len(prep['rows'])==40 and audit['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Sealed complete preparation')
    require(pub['schema']=='CASH_TOPUP_NEIGHBOR_PREPARATION_PUBLICATION_V1' and pub['status']=='PUBLISHED_UNEVALUATED_CANDIDATES_ONLY','Preparation publication')
    for obj in (pub,audit):exact(obj['preparation_reference'],refs['preparation'],'Preparation link')
    exact(audit['publication_reference'],refs['publication'],'Audit receipt');require(audit['reader_sha256']==PINS['preparation_reader'][1],'Independent preparation reader')
    for obj in (prep,pub,audit):
        for k in ('risk_evaluated','financial_feasibility_evaluated','fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed'):require(obj[k] is False,'No preparation authority')
    require(not (PREP/'failure.json').exists(),'Failed preparation')
    exact(pub['source_hashes'],prep['source_hashes'],'Preparation source claims');exact(prep['task_evaluation_count'],0,'Unevaluated parent');require(prep['declared_local_neighborhood_complete'] is True,'Complete declared domain')
    post=decode(read(postcheck_reference));require(Path(post['started_reference']['path'])==directory/'started.json' and Path(post['raw_reference']['path'])==directory/'raw.json','Fixed attempt artifacts');started=decode(read(post['started_reference']));raw=decode(read(post['raw_reference']));exact(raw['started_reference'],post['started_reference'],'Raw start link')
    require(started['task_id']==task_id,'Externally selected task')
    require({p.name for p in directory.iterdir()}=={'started.json','raw.json','postcheck.json'},'Complete successful attempt capture; failure namespace not consumed')
    identity=started['evaluation_identity'];require(sha(enc(identity))==started['evaluation_identity_sha256'],'Full evaluation identity')
    exact(identity['preparation_references'],refs,'Original preparation refs');contract_ref=identity['contract_reference'];task_ref=identity['task_reference']
    matches=[(i,r) for i,r in enumerate(prep['rows']) if r['contract_reference']==contract_ref];require(len(matches)==1,'Unique original scenario ref');i,scenario=matches[0]
    require(Path(contract_ref['path'])==PREP/f'scenario-{i:02d}'/'contract.json','Fixed contract path');prepared=decode(read(contract_ref));exact(started['original_contract'],prepared,'Full original contract')
    c=prepared['contract'];require(sha(enc(c))==prepared['contract_sha256']==scenario['contract_sha256'],'Saved contract digest')
    matches=[(j,s) for j,s in enumerate(scenario['shards']) if s['path']==task_ref['path'] and s['sha256']==task_ref['sha256']];require(len(matches)==1,'Unique shard ref');j,shard=matches[0]
    require(Path(shard['path'])==PREP/f'scenario-{i:02d}'/f'tasks-{j:05d}.jsonl','Fixed shard path')
    sr=ref(shard['path'],shard['sha256']);lines=read(sr).splitlines();index=task_ref['jsonl_line_index'];require(type(index) is int and 0<=index<len(lines) and len(lines)==shard['stop']-shard['start'],'Exact shard/local index');task=decode(lines[index]);exact(task['scenario_candidate_ordinal'],shard['start']+index,'Task global ordinal');exact(task_ref,dict(sr,jsonl_line_index=index,scenario_candidate_ordinal=task['scenario_candidate_ordinal']),'Task pointer complete');exact(started['task'],task,'Full source task');require(task['task_id']==task_id==sha(enc(task['identity'])),'Prepared task identity')
    exact(task['identity'],dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule=c['rule'],scenario_contract_sha256=prepared['contract_sha256'],buy_shares=task['identity']['buy_shares']),'Full task identity fields')
    exact(identity,dict(schema='CASH_TOPUP_SINGLE_EVALUATION_IDENTITY_V1',prepared_task=task['identity'],task_reference=task_ref,contract_reference=contract_ref,preparation_references=refs,numerical_sources={k:ref(ROOT/p,h) for k,(p,h) in PINS.items() if k in ('kernel','evaluator','original_score_semantics')}),'Complete numeric identity')
    r=c['original_input_row'];inputs={k:deepcopy(r[k]) for k in ('cash_event','starting_cash_usd','holdings','execution_prices','risk_parameters','transaction_cost_bps','minimum_cash_buffer_usd')};inputs['securities']={s:{k:v[k] for k in ('issuer_id','risk_chain')} for s,v in r['securities'].items()};inputs.update(branches=[dict(branch_id=r['scenario_id'],buy_limits=c['saved_buy_limits'])],max_evaluations=1)
    exact(started['evaluation_arguments'],dict(evaluation_inputs=inputs,plans_by_branch={r['scenario_id']:[task['identity']['buy_shares']]}),'Complete arguments from original row')
    producer_sources={str(PRODUCER):PRODUCER_SHA,**{str(ROOT/p):h for p,h in PINS.values()},**{r['path']:r['sha256'] for r in refs.values()},contract_ref['path']:contract_ref['sha256'],sr['path']:sr['sha256']};exact(started['source_hashes'],producer_sources,'Full producer closure')
    for r0 in (contract_ref,sr):require(audit['source_hashes'][r0['path']]==r0['sha256'],'Prepared independent audit includes exact evidence')
    def guard():
        for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Saved source drift')
    guard();result=inspect_saved(started,raw,post);guard();out.mkdir(parents=True,exist_ok=False)
    def save(path,value):
        b=enc(value)
        with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
        require(path.read_bytes()==b,'Output exact');return ref(path,sha(b))
    try:
        report=dict(schema='CASH_TOPUP_SINGLE_EVALUATION_INDEPENDENT_READBACK_V1',status='PASS',task_id=task_id,postcheck_reference=postcheck_reference,started_reference=post['started_reference'],raw_reference=post['raw_reference'],preparation_references=refs,task_reference=task_ref,contract_reference=contract_ref,source_hashes=sources,reader_sha256=LOADED,verification_scope='SAVED_ONE_PLAN_FINANCE_RISK_L1_NOT_TIME_SERIES_OR_EXECUTION',producer_called=False,evaluator_called=False,old_audit_called=False,**result,**dict.fromkeys(FLAGS,False))
        answer=save(out/'independent_readback.json',report);guard();require({p.name for p in out.iterdir()}=={'independent_readback.json'},'Exact reader output');return answer
    except Exception as e:save(out/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task-id',required=True);p.add_argument('--postcheck-sha',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();print(json.dumps(readback(a.task_id,ref(ATTEMPTS/a.task_id/'postcheck.json',a.postcheck_sha),execute=a.execute)))
