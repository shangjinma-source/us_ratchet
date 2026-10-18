"""Evaluate only unseen local buy-plan repairs; retain the first research batch by reference."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/first_period_cash_repair_research_20261002_v1'
PINS={
 'inputs':('data/cache/research/first_period_standard_cash_inputs_20261002_v1/inputs.json','f583f6e55efeb78f0fc1c761bb2027076274012c30a7dda528ef6dee1a3004ee'),
 'input_publication':('data/cache/research/first_period_standard_cash_inputs_20261002_v1/publication.json','304303cd9e53cb92723d4fd463f58934f3506339a2f8170ffef9cd9f258e6d47'),
 'old_results':('data/cache/research/first_period_cash_neighbor_research_20261002_v1/results.json','dfd434e79c5f9f1242a1a2d11d7cbe7bf9d830f6d5e3e380225a64ff31dcdbdf'),
 'repair':('backtest/ndx_cash_plan_repair_neighbors_research.py','f1f2631f48a936a3c318dd97f290f58bc0a8b8d388492ec12df783ce9f031601'),
 'evaluator':('backtest/ndx_explicit_cash_plan_evaluation_research.py','bc98beb6afdf04110c61857aef4b573a3840811076d729d4efc022d9b6523191'),
 'kernel':('backtest/ndx_conditional_new_cash_fork_research.py','5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f')}


def require(value,message):
    if not value: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def ratio(value): return {'numerator':str(value.numerator),'denominator':str(value.denominator)}


def plan_key(plan): return tuple(sorted(plan.items()))


def process(row,old,generate,evaluate):
    require(row['scenario_id']==old['scenario_id'] and not row['holdings'],'First-period coordinate mismatch')
    old_branch=old['evaluation']['branches'][0]
    excluded=[plan['buy_shares'] for plan in old_branch['evaluated_plans']]
    require(len(excluded)==17 and len(set(map(plan_key,excluded)))==17,'Old 17-plan set differs')
    seeds=[plan for plan in excluded if any(plan.values())]
    require(len(seeds)==16,'Old 16 nonzero seeds required')
    generated=generate(buy_limits=old_branch['buy_limits'],seed_plans=seeds,excluded_plans=excluded,max_generated_plans=10000)
    require(generated['ungenerated_plan_count']==0,'Repair generation incomplete')
    new_plans=[item['buy_shares'] for item in generated['generated_plans']]
    require(not(set(map(plan_key,new_plans)) & set(map(plan_key,excluded))),'Old candidate regenerated')
    inputs={key:row[key] for key in ('cash_event','starting_cash_usd','holdings','execution_prices','risk_parameters','transaction_cost_bps','minimum_cash_buffer_usd')}
    inputs['securities']={sid:{key:entry[key] for key in ('issuer_id','risk_chain')} for sid,entry in row['securities'].items()}
    inputs.update(branches=[{'branch_id':row['scenario_id'],'buy_limits':old_branch['buy_limits']}],max_evaluations=10000)
    evaluation=evaluate(evaluation_inputs=inputs,plans_by_branch={row['scenario_id']:new_plans})
    require(evaluation['unevaluated_supplied_plan_count']==0,'Repair evaluation incomplete')
    normalized={sid:Fraction(int(v['numerator']),int(v['denominator'])) for sid,v in old['generator']['normalized_target_weights'].items()}
    scored=[]
    for source,plans in enumerate((old_branch['evaluated_plans'],evaluation['branches'][0]['evaluated_plans'])):
        for index,plan in enumerate(plans):
            if not plan['feasible']: continue
            notionals={sid:q*Fraction(row['execution_prices'][sid]) for sid,q in plan['proposed_holdings'].items()}
            total=sum(notionals.values(),Fraction(0))
            distance=sum((abs(value/total-normalized[sid]) for sid,value in notionals.items()),Fraction(0))
            scored.append((distance,Fraction(plan['fees_usd']),source,index))
    winner=min(scored) if scored else None
    selected=None if winner is None else {'source':'PREVIOUS_BATCH' if winner[2]==0 else 'NEW_REPAIR_BATCH',
        'plan_index':winner[3],'target_l1_distance':ratio(winner[0]),'fee_usd':ratio(winner[1])}
    return {'scenario_id':row['scenario_id'],'repair_generation':generated,'evaluation':evaluation,
        'previous_candidate_count':17,'previous_evaluation_repeated':False,
        'combined_feasible_count':len(scored),'combined_candidate_count':17+evaluation['evaluated_count'],
        'selected':selected,'combined_tie_order':['EXACT_L1','EXACT_FEES','PREVIOUS_BATCH_FIRST','PLAN_INDEX'],
        'all_integer_space_exhausted':False,'economic_winner_selected':False,'orders_executed':False,
        'time_series_return_evaluated':False,'point_in_time_verified':False,'promotion_allowed':False}


def write_new(path,value):
    raw=encode(value)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output mismatch')
    return sha(raw)


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no overwrite/retry')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source changed')
    require(all(type(value) is str and len(value)==64 for _,value in PINS.values()),'Pending source pin')
    sources={str(SOURCE):LOADED_SHA}; docs={}; refs={}
    for role,(relative,expected) in PINS.items():
        path=ROOT/relative; raw=path.read_bytes(); require(sha(raw)==expected,'Source hash mismatch: '+role)
        sources[str(path)]=expected; refs[role]={'path':str(path),'sha256':expected}
        if role in ('inputs','old_results','input_publication'): docs[role]=json.loads(raw)
    require({p.name for p in Path(refs['inputs']['path']).parent.iterdir()}=={'inputs.json','publication.json'},'Input publication incomplete')
    require({p.name for p in Path(refs['old_results']['path']).parent.iterdir()}=={'started.json','results.json'},'Old batch incomplete')
    receipt=docs['input_publication']
    require(receipt['input_reference']==refs['inputs'] and receipt['source_hashes']==docs['inputs']['source_hashes']
            and receipt['status']=='INPUTS_ONLY_NOT_EXECUTED','Input publication mismatch')
    names={'repair':'backtest.ndx_cash_plan_repair_neighbors_research','evaluator':'backtest.ndx_explicit_cash_plan_evaluation_research','kernel':'backtest.ndx_conditional_new_cash_fork_research'}
    require(all(name not in sys.modules for name in names.values()),'Fresh CLI required')
    modules={role:importlib.import_module(name) for role,name in names.items()}
    require(all(Path(module.__file__).resolve()==Path(refs[role]['path']).resolve() for role,module in modules.items()),'Wrong module path')
    def guard():
        for path,expected in sources.items(): require(sha(Path(path).read_bytes())==expected,'Source drift')
    guard(); require(len(docs['inputs']['rows'])==len(docs['old_results']['rows'])==8,'Expected eight input/old rows')
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'started_at_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':sources,'retry_allowed':False})
        rows=[]
        for index,(row,old) in enumerate(zip(docs['inputs']['rows'],docs['old_results']['rows'])):
            result=process(row,old,modules['repair'].generate_repair_neighbors,modules['evaluator'].evaluate_explicit_plans)
            result['input_reference']=dict(refs['inputs'],json_pointer=f'/rows/{index}')
            result['previous_result_reference']=dict(refs['old_results'],json_pointer=f'/rows/{index}')
            rows.append(result)
        guard()
        result={'schema':'FIRST_PERIOD_CASH_REPAIR_RESEARCH_V1','source_hashes':sources,'rows':rows,
            'old_candidate_evaluations_repeated':0,'historical_instant_plan_research_executed':True,
            'source_identity_gaps_resolved':False,'full_ndx_search_claimed':False,'account_replayed':False,
            'orders_executed':False,'point_in_time_verified':False,'promotion_allowed':False}
        digest=write_new(OUTPUT/'results.json',result); guard()
        require(sha((OUTPUT/'results.json').read_bytes())==digest and {p.name for p in OUTPUT.iterdir()}=={'started.json','results.json'},'Final output mismatch')
        return {'path':str(OUTPUT/'results.json'),'sha256':digest,'new_evaluated_count':sum(r['evaluation']['evaluated_count'] for r in rows),
                'new_feasible_count':sum(r['evaluation']['branches'][0]['feasible_evaluated_count'] for r in rows),
                'selected_scenarios':sum(r['selected'] is not None for r in rows)}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error)})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
