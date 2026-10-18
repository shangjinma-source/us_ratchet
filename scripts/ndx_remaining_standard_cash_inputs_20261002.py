"""Source-bound remaining research inputs only; no search or account calls."""
import argparse
import copy
import hashlib
import json
import math
import os
from decimal import Decimal, Context, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE = ROOT / 'data/cache/research'
OUTPUT = BASE / 'remaining_standard_cash_inputs_20261002_v1'
BOUND = {
 'scenarios': ('standard_cash_scenarios_20261002_v1/scenarios.json', '5100a90a6b862492fadd2bd38f6596195cb6aba9dc08c37cb25552728469c5bf'),
 'inventory': ('conditional_new_cash_inventory_20260925_v2/inventory.json', 'f8b88fc72c6a3906440d4ddc83b5614e2a0a009a8843603a6028b713f62cb626'),
 'publication': ('conditional_new_cash_inventory_20260925_v2/publication.json', 'e18344ff2535d4cea735d57e5d1c5cd99e60da98c8990040055b2bab48aa53a7'),
 'account': ('return_six_period_conditional_execution_20260923_v2/account.json', 'ed69a9de921d94f9a186d59a6ef16c09f46544ede388e4fff271c10a77f433e2')}
LANES = ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'LEGACY_TARGET_DISTANCE')
RISK = ('max_single_weight', 'min_single_weight', 'top_weight_cap', 'minimum_effective_n_ratio', 'risk_chain_top1_cap')
FLAGS = dict.fromkeys(('cash_fork_called','search_called','account_rerun','fit_called','old_audit_rerun','point_in_time_verified','promotion_allowed','orders_executed','fork_executable','full_transitive_source_closure_reverified'), False)

def require(ok, message):
    if not ok: raise ValueError(message)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
def number(value):
    require(type(value) in (str,int,float), 'Numeric literal required')
    result=Decimal(str(value))
    require(result.is_finite(), 'Finite literal required')
    return result

def assemble(docs, refs):
    inv, scenarios, receipt = (docs[k] for k in ('inventory','scenarios','publication'))
    require(inv['schema']=='CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V2' and len(inv['rows'])==36, 'Inventory schema/count')
    require(scenarios['schema']=='STANDARD_CASH_RESEARCH_SCENARIOS_V1' and len(scenarios['rows'])==72, 'Scenario schema/count')
    for key in ('cash_fork_called','point_in_time_verified','promotion_allowed'):
        require(inv[key] is False and scenarios[key] is False, 'Source authority')
    require(scenarios['parent_inventory_reference']==refs['inventory'], 'Scenario parent')
    require(receipt['inventory_reference']==refs['inventory'] and receipt['source_hashes']==inv['source_hashes'] and receipt['status']=='SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY' and receipt['fork_executed'] is False, 'Inventory publication')
    contract=docs['account']['execution_contract']
    parameters={k:str(number(contract[k])) for k in (*RISK,'transaction_cost_bps','minimum_cash_buffer_usd')}
    require(all(0<number(parameters[k])<=1 for k in RISK) and number(parameters['transaction_cost_bps'])>=0 and number(parameters['minimum_cash_buffer_usd'])>=0, 'Execution parameters')
    rows=[]; seen=set()
    for si, scenario in enumerate(scenarios['rows']):
        if scenario['decision_date']=='2023-03-31' and scenario['lane'] in LANES: continue
        lane, amount=scenario['lane'],scenario['standardized_cash_injection_usd']
        require(amount in ('1000','10000') and (lane,scenario['decision_date'],amount) not in seen, 'Scenario duplicate/amount')
        seen.add((lane,scenario['decision_date'],amount))
        ref=scenario['parent_row_reference']; pointer=ref['json_pointer']
        require({k:v for k,v in ref.items() if k!='json_pointer'}==refs['inventory'], 'Row parent reference')
        require(pointer.startswith('/rows/') and pointer.split('/')[-1].isdigit(), 'Row pointer')
        index=int(pointer.split('/')[-1]); require(pointer==f'/rows/{index}' and 0<=index<36,'Canonical row pointer')
        row=inv['rows'][index]
        require(all(row[k]==scenario[k] for k in ('lane','decision_date','execution_date')) and row['decision_date']<row['execution_date'],'Coordinate')
        require(scenario['hypothetical_research_only'] is True and scenario['real_user_cash_claimed'] is False and scenario['fork_executable'] is False,'Scenario limits')
        require(row['cash_event_amount_usd'] is None and row['fork_executable'] is False,'Unexecuted parent')
        holdings=row['baseline']['shares']
        require(all(type(q) is int and q>=0 for q in holdings.values()) and number(row['baseline']['cash_usd'])>=0,'Baseline quantities/cash')
        cash=row['baseline_cash_encoding']; require(cash['decimal_literal']==str(row['baseline']['cash_usd']) and cash['encoding']=='SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE','Cash encoding')
        target=row['lane_target']; require(target['decision_date']==row['decision_date'] and target['execution_date']==row['execution_date'],'Target clock')
        targets=target['targets']; union={sid for sid,q in holdings.items() if q>0}|set(targets)
        require(set(row['union_security_ids'])==union and len(row['union_security_ids'])==len(union) and len(row['securities'])==len(union),'Complete old-holding and target union')
        require(lane in (*LANES,'INCUMBENT_ADD_ONLY_CONTROL','CASH_RETENTION_CONTROL'),'Lane')
        require((not targets) if lane=='CASH_RETENTION_CONTROL' else bool(targets),'Control target semantics')
        securities={}; prices={}; weights={}
        for security in row['securities']:
            sid=security['security_id']; require(sid in union and sid not in securities,'Unique target SID')
            require(security['identity_interval_certified'] is False and security['provider_binding_verified'] is False,'Security authority')
            coords=[v['value'] for v in security['saved_coordinates']]
            pairs={(v['ticker'],v['issuer_id']) for v in coords}
            require(len(pairs)==1,'Unique saved issuer/ticker')
            ticker,issuer=next(iter(pairs))
            for evidence in security['dated_identity_evidence']:
                value=evidence['value']
                require(value['security_id']==sid and value['ticker']==ticker and value['issuer_id']==issuer,'Dated coordinate conflicts')
            if sid in targets:
                t=targets[sid]
                require(t['ticker']==ticker and t['issuer_id']==issuer,'Target coordinate conflicts')
                require(type(t['target_weight']) is float and math.isfinite(t['target_weight']) and t['target_weight']>0,'Saved float target')
                weights[sid]=str(t['target_weight'])
            marks=security['execution_open_observations']; require(marks and all(v['currency']=='USD' for v in marks),'USD marks')
            values={number(v['decimal_literal']) for v in marks}; require(len(values)==1 and next(iter(values))>0,'Open conflict')
            observations=security['risk_observations']; require(observations and all(v['observation_date']<=row['decision_date'] for v in observations),'Future/missing risk')
            chains={v['risk_chain'] for v in observations}; require(len(chains)==1 and all(type(v) is str and v for v in chains),'Risk conflict')
            securities[sid]={'ticker':ticker,'issuer_id':issuer,'risk_chain':next(iter(chains))}
            prices[sid]=marks[0]['decimal_literal']
        require(set(securities)==union,'Union coverage')
        with localcontext(Context(prec=160)): total=str(sum((Decimal(v) for v in weights.values()),Decimal(0)))
        rows.append({'scenario_id':scenario['scenario_id'],'lane':lane,'scenario_reference':dict(refs['scenarios'],json_pointer=f'/rows/{si}'),'inventory_row_reference':ref,
          'cash_event':{'decision_date':row['decision_date'],'execution_date':row['execution_date'],'amount_usd':amount},'starting_cash_usd':cash['decimal_literal'],'holdings':copy.deepcopy(holdings),
          'securities':securities,'execution_prices':prices,'target_weights':weights,'original_target_weight_sum':total,'target_weights_normalized':False,
          'allowed_buy_security_ids':sorted(targets),'zero_buy_only':lane=='CASH_RETENTION_CONTROL',
          'target_l1_applicable':lane!='CASH_RETENTION_CONTROL','branch_role':('MAIN_LANE' if lane in LANES else 'MIGRATION_CONTROL' if lane=='INCUMBENT_ADD_ONLY_CONTROL' else 'CASH_RETENTION_CONTROL'),
          'target_encoding':'SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE','risk_parameters':{k:parameters[k] for k in RISK},
          'transaction_cost_bps':parameters['transaction_cost_bps'],'minimum_cash_buffer_usd':parameters['minimum_cash_buffer_usd'],
          'original_inventory_row':copy.deepcopy(row),'original_scenario':copy.deepcopy(scenario),'gaps':copy.deepcopy(row['gaps']),**FLAGS})
    clocks=('2023-03-31','2023-04-28','2023-05-31','2023-06-30','2023-07-31','2023-08-31')
    expected={(lane,day,amount) for lane in (*LANES,'INCUMBENT_ADD_ONLY_CONTROL','CASH_RETENTION_CONTROL') for day in clocks for amount in ('1000','10000') if not(day==clocks[0] and lane in LANES)}
    require(seen==expected and len(rows)==64,'Exact remaining64 scenarios')
    return {'schema':'REMAINING_STANDARD_CASH_INPUTS_V1','rows':rows,'scenario_count':64,'input_references':refs,
      'execution_contract_reference':dict(refs['account'],json_pointer='/execution_contract'),'original_execution_contract':copy.deepcopy(contract),
      'scope':'REMAINING64_CONDITIONAL_HISTORICAL_INPUTS_40_MAIN_12_MIGRATION_12_CASH_CONTROL',
      'other_dates_readiness_claimed':False,'real_user_cash_claimed':False,'selection_policy_frozen':False,'search_domain_frozen':False,
      'evidence_gaps_resolved':False,**FLAGS}

def publish():
    require(not OUTPUT.exists(),'Namespace exists; no overwrite/retry')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source changed')
    sources={str(SOURCE):LOADED_SHA}; docs={}; refs={}
    for role,(relative,digest) in BOUND.items():
        path=BASE/relative; raw=path.read_bytes(); require(sha(raw)==digest,'Input bytes differ')
        sources[str(path)]=digest; refs[role]={'path':str(path),'sha256':digest}; docs[role]=json.loads(raw)
    require({p.name for p in (BASE/BOUND['inventory'][0]).parent.iterdir()}=={'inventory.json','publication.json'},'Parent namespace incomplete')
    require({p.name for p in (BASE/BOUND['scenarios'][0]).parent.iterdir()}=={'scenarios.json'},'Scenario namespace incomplete')
    result=assemble(docs,refs); result['source_hashes']=sources
    def guard():
        for path,digest in sources.items(): require(sha(Path(path).read_bytes())==digest,'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        path=OUTPUT/'inputs.json'; payload=encode(result)
        with path.open('xb') as f: f.write(payload); f.flush(); os.fsync(f.fileno())
        guard(); require(path.read_bytes()==payload,'Output differs')
        receipt={'schema':'REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1','status':'INPUTS_ONLY_NOT_EXECUTED','input_reference':{'path':str(path),'sha256':sha(payload)},'source_hashes':sources,**FLAGS}
        receipt_raw=encode(receipt)
        with (OUTPUT/'publication.json').open('xb') as f: f.write(receipt_raw); f.flush(); os.fsync(f.fileno())
        guard(); require(path.read_bytes()==payload and (OUTPUT/'publication.json').read_bytes()==receipt_raw and {p.name for p in OUTPUT.iterdir()}=={'inputs.json','publication.json'},'Publication differs')
        return {'path':str(path),'sha256':sha(payload),'publication_sha256':sha(receipt_raw)}
    except Exception as error:
        with (OUTPUT/'failure.json').open('xb') as f: f.write(encode({'status':'FAILED_DO_NOT_CONSUME','error':str(error)}))
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--publish',action='store_true')
    if not parser.parse_args().publish: parser.error('Explicit --publish required')
    print(json.dumps(publish(),indent=2))
