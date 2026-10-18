"""One-shot source-bound first-period cash-plan research; no account path or live orders."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE = ROOT / 'data/cache/research'
OUTPUT = BASE / 'first_period_cash_neighbor_research_20261002_v1'
PINS = {
    'inputs': ('data/cache/research/first_period_standard_cash_inputs_20261002_v1/inputs.json', 'f583f6e55efeb78f0fc1c761bb2027076274012c30a7dda528ef6dee1a3004ee'),
    'publication': ('data/cache/research/first_period_standard_cash_inputs_20261002_v1/publication.json', '304303cd9e53cb92723d4fd463f58934f3506339a2f8170ffef9cd9f258e6d47'),
    'generator': ('backtest/ndx_target_cash_neighbors_research.py', '77819f44ae8e7b73aa9683a544ff96a16d27b2194ca3d7fac4376e81dc0e4c68'),
    'evaluator': ('backtest/ndx_explicit_cash_plan_evaluation_research.py', 'bc98beb6afdf04110c61857aef4b573a3840811076d729d4efc022d9b6523191'),
    'kernel': ('backtest/ndx_conditional_new_cash_fork_research.py', '5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def rational(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def research_row(row, generate, evaluate):
    require(row['injection_usd']==row['cash_event']['amount_usd'],'Injection mismatch')
    cash, injection, buffer, fee = (Fraction(row[key]) for key in ('starting_cash_usd', 'injection_usd', 'minimum_cash_buffer_usd', 'transaction_cost_bps'))
    gross = max(Fraction(0), cash + injection - buffer) / (1 + fee / 10000)
    limits = {sid: gross // Fraction(row['execution_prices'][sid]) for sid in sorted(row['target_weights'])}
    generated = generate(holdings=row['holdings'], starting_cash_usd=row['starting_cash_usd'],
        injection_usd=row['injection_usd'], execution_prices=row['execution_prices'],
        target_weights=row['target_weights'], buy_limits=limits,
        transaction_cost_bps=row['transaction_cost_bps'], minimum_cash_buffer_usd=row['minimum_cash_buffer_usd'],
        max_generated_plans=32)
    require(generated['ungenerated_count'] == 0 and len(generated['plans']) <= 17, 'First four-target domain not fully generated')
    inputs = {key: row[key] for key in ('cash_event','starting_cash_usd','holdings','execution_prices','risk_parameters','transaction_cost_bps','minimum_cash_buffer_usd')}
    inputs['securities'] = {sid: {key: item[key] for key in ('issuer_id','risk_chain')} for sid,item in row['securities'].items()}
    inputs.update(branches=[{'branch_id': row['scenario_id'], 'buy_limits': limits}], max_evaluations=32)
    evaluation = evaluate(evaluation_inputs=inputs, plans_by_branch={row['scenario_id']:generated['plans']})
    require(evaluation['unevaluated_supplied_plan_count'] == 0, 'Supplied plan evaluation incomplete')
    normalized = {sid: Fraction(int(value['numerator']), int(value['denominator'])) for sid,value in generated['normalized_target_weights'].items()}
    scored=[]
    for plan in evaluation['branches'][0]['evaluated_plans']:
        if not plan['feasible']:
            continue
        notionals={sid: count*Fraction(row['execution_prices'][sid]) for sid,count in plan['proposed_holdings'].items()}
        total=sum(notionals.values(),Fraction(0))
        distance=sum((abs(value/total-normalized[sid]) for sid,value in notionals.items()),Fraction(0))
        scored.append((distance,Fraction(plan['fees_usd']),plan['supplied_plan_index']))
    winner=min(scored) if scored else None
    return {'scenario_id':row['scenario_id'],'generator':generated,'evaluation':evaluation,
        'feasible_scores':[{'supplied_plan_index':index,'target_l1_distance':rational(distance),'fee_usd':rational(fee)} for distance,fee,index in scored],
        'selected_supplied_plan_index':None if winner is None else winner[2],
        'selection_status':'NO_FEASIBLE_SUPPLIED_PLAN' if winner is None else 'BEST_TARGET_DISTANCE_AMONG_SUPPLIED_FEASIBLE_PLANS',
        'scope':'FOUR_TARGET_ROUNDING_NEIGHBORHOOD_NOT_FULL_INTEGER_OR_NDX_SPACE',
        'historical_instant_plan_research_executed':True, 'time_series_return_evaluated':False,
        'economic_winner_selected':False,'global_optimality_claimed':False,'orders_executed':False,
        'point_in_time_verified':False,'promotion_allowed':False}


def write_new(path, value):
    raw=encode(value)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output bytes changed')
    return sha(raw)


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry/overwrite')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source changed')
    require(all(type(pin) is str and len(pin)==64 for _,pin in PINS.values()),'Pending source anchors')
    sources={str(SOURCE):LOADED_SHA}; refs={}; raw={}
    for role,(relative,expected) in PINS.items():
        path=ROOT/relative; raw[role]=path.read_bytes(); require(sha(raw[role])==expected,'Source mismatch: '+role)
        sources[str(path)]=expected; refs[role]={'path':str(path),'sha256':expected}
    require({p.name for p in Path(refs['inputs']['path']).parent.iterdir()}=={'inputs.json','publication.json'},'Input namespace incomplete')
    inputs=json.loads(raw['inputs']); receipt=json.loads(raw['publication'])
    require(receipt['input_reference']==refs['inputs'] and receipt['source_hashes']==inputs['source_hashes'] and receipt['status']=='INPUTS_ONLY_NOT_EXECUTED','Input receipt mismatch')
    require(inputs['schema']=='FIRST_PERIOD_STANDARD_CASH_INPUTS_V1' and len(inputs['rows'])==8,'Eight inputs required')
    module_names={'generator':'backtest.ndx_target_cash_neighbors_research',
                  'evaluator':'backtest.ndx_explicit_cash_plan_evaluation_research',
                  'kernel':'backtest.ndx_conditional_new_cash_fork_research'}
    require(all(name not in sys.modules for name in module_names.values()),'Fresh CLI required; cached research module present')
    modules={role:importlib.import_module(name) for role,name in module_names.items()}
    require(all(Path(module.__file__).resolve()==Path(refs[role]['path']).resolve() for role,module in modules.items()),'Imported module path differs')
    generate_target_neighbors=modules['generator'].generate_target_neighbors
    evaluate_explicit_plans=modules['evaluator'].evaluate_explicit_plans
    def guard():
        for path,expected in sources.items(): require(sha(Path(path).read_bytes())==expected,'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'started_at_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':sources,'retry_allowed':False})
        rows=[]
        for index,original in enumerate(inputs['rows']):
            row=dict(original,injection_usd=original['cash_event']['amount_usd'])
            require(not row['holdings'] and len(row['target_weights'])==4,'Expected first-period empty baseline')
            result=research_row(row,generate_target_neighbors,evaluate_explicit_plans)
            result['input_reference']=dict(refs['inputs'],json_pointer=f'/rows/{index}')
            rows.append(result)
        guard()
        result={'schema':'FIRST_PERIOD_CASH_NEIGHBOR_RESEARCH_V1','source_hashes':sources,'input_references':refs,'rows':rows,
            'selection_order':['LOWEST_EXACT_STOCK_WEIGHT_L1','LOWEST_EXACT_FEES','LOWEST_SUPPLIED_PLAN_INDEX'],
            'generator_budget_per_scenario':32,'evaluation_budget_per_scenario':32,
            'historical_instant_plan_research_executed':True,'account_path_replayed':False,'full_ndx_search_claimed':False,
            'orders_executed':False,'promotion_allowed':False,'point_in_time_verified':False}
        digest=write_new(OUTPUT/'results.json',result); guard()
        require(sha((OUTPUT/'results.json').read_bytes())==digest,'Final result bytes changed')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','results.json'},'Unexpected output')
        return {'sha256':digest,'path':str(OUTPUT/'results.json'),'evaluated_count':sum(r['evaluation']['evaluated_count'] for r in rows),
                'feasible_count':sum(r['evaluation']['branches'][0]['feasible_evaluated_count'] for r in rows),
                'selected_count':sum(r['selected_supplied_plan_index'] is not None for r in rows)}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error)})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
