"""Ten independent same-injection incumbent paths mapped explicitly to forty scenarios."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/incumbent_cash_flow_paths_20261002_v1'
PINS={
 'inputs':('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json','1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'),
 'input_publication':('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json','54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'),
 'nominal':('data/cache/research/incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json','53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'),
 'policy':('backtest/ndx_dynamic_frozen_incumbent_control.py','537908ef0447b1e4e7104afdd2008d4d3d04b60f820bfaab33562dc7114f54e6'),
 'execution_policy':('backtest/ndx_dynamic_frozen_execution_research.py','69d2bf761eac32edd8c39a9fdbffed300ba7cb4740771fbd008b4f09b204813b'),
 'core':('backtest/ndx_incumbent_cash_flow_research.py','e905dfaa2962e0bc52f32115093cea782ae39072b5723e07519b254762203c6e')}
FLAGS=dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled',
 'corporate_actions_modelled','fx_modelled','formal_dual_benchmark_admission','old_accounts_reexecuted',
 'original_target_weights_modified','risk_is_order_gate','full_transitive_source_closure_reverified'),False)
CLOCKS=(('2023-04-28','2023-05-01',87),('2023-05-31','2023-06-01',65),
        ('2023-06-30','2023-07-03',44),('2023-07-31','2023-08-01',24),('2023-08-31','2023-09-01',1))
LANES=('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE')


def require(ok,message):
    if not ok: raise ValueError(message)


def literal(value):
    require(type(value) is float and math.isfinite(value),'Finite saved JSON float required')
    return str(value)


def pointer(ref,path): return dict(ref,json_pointer=path)


def grouped_rows(document):
    require(document['schema']=='REMAINING_STANDARD_CASH_INPUTS_V1' and len(document['rows'])==64,'Frozen remaining64 contract')
    groups={}; coordinates=set()
    fields=('holdings','starting_cash_usd','cash_event','transaction_cost_bps','minimum_cash_buffer_usd','risk_parameters')
    for index,row in enumerate(document['rows']):
        if row['branch_role']!='MAIN_LANE': continue
        event=row['cash_event']; coordinate=(row['lane'],event['decision_date'],event['execution_date'],event['amount_usd'])
        require(coordinate not in coordinates,'Duplicate main coordinate'); coordinates.add(coordinate)
        key=(event['decision_date'],event['amount_usd'])
        if key in groups:
            first=groups[key][0][1]
            require(all(row[field]==first[field] for field in fields),'Shared path inputs differ across lane')
            require(row['original_inventory_row']['baseline']==first['original_inventory_row']['baseline'],'Baseline provenance differs')
        groups.setdefault(key,[]).append((index,row))
    require(coordinates=={(lane,d,e,a) for lane in LANES for d,e,_ in CLOCKS for a in ('1000','10000')},'Exact40 main scenarios required')
    require(len(groups)==10 and all(len(rows)==4 for rows in groups.values()),'Ten exact four-lane groups required')
    return groups


def prepare_path(row,nominal,ref):
    fixed=nominal['original_fixed_schedule']; original=fixed['schedule']; first=original[0]['targets']
    require(nominal['schema']=='ndx_incumbent_nominal_control_research_v1'
            and nominal['execution']['schema']=='ndx_dynamic_frozen_incumbent_control_v1','Actual dynamic Open incumbent source required')
    for flag in ('point_in_time_verified','promotion_allowed','dividends_modelled','price_identity_binding_verified','risk_is_order_gate'):
        require(nominal[flag] is False,'Original source authority changed')
    require(all(item['targets']==first for item in original),'Original fixed targets changed')
    sids=sorted(first)
    require(set(row['holdings'])==set(sids),'Whole original eight holdings required')
    require({sid:row['securities'][sid]['ticker'] for sid in sids}=={sid:first[sid]['ticker'] for sid in sids},'Prepared ticker attribution mismatch')
    require(all(row['securities'][sid]['issuer_id']==first[sid]['issuer_id'] for sid in sids),'Prepared issuer attribution mismatch')
    require(row['risk_parameters']=={key:literal(value) for key,value in nominal['original_risk_parameters'].items()},'Original risk parameters differ')
    require(Fraction(row['transaction_cost_bps'])==Fraction(literal(fixed['transaction_cost_bps']))
            and Fraction(row['minimum_cash_buffer_usd'])==Fraction(literal(fixed['minimum_cash_buffer_usd'])),'Fee/buffer contract differs')
    start=row['cash_event']['decision_date']; end='2023-09-01'
    calendar=[day for day in fixed['calendar'] if start<=day<=end]
    require(calendar==sorted(set(calendar)) and calendar[0]==start and calendar[-1]==end
            and calendar[1]==row['cash_event']['execution_date']
            and len(calendar)-1==next(n for d,e,n in CLOCKS if d==start),'Exact saved path clock')
    selected=[(index,item) for index,item in enumerate(original) if start<=item['decision_date'] and item['execution_date']<=end]
    require(selected and selected[0][1]['decision_date']==start,'Initial decision missing')
    chain_map=fixed['risk_chains_by_decision'][start]
    require(all(fixed['risk_chains_by_decision'][item['decision_date']]==chain_map for _,item in selected),'Static core cannot consume changed risk labels')
    securities={sid:{'ticker':first[sid]['ticker'],'issuer_id':first[sid]['issuer_id'],'risk_chain':chain_map[sid]} for sid in sids}
    indexed={}
    for sid in sids:
        ticker=securities[sid]['ticker']; rows=nominal['nominal_quotes']['by_ticker'][ticker]['rows']
        require(len({quote['session'] for quote in rows})==len(rows),'Duplicate source quote date')
        indexed[sid]={quote['session']:(i,quote) for i,quote in enumerate(rows)}
    evidence=[]
    def marks(day,field):
        output={}; observed={}
        for sid in sids:
            index,quote=indexed[sid][day]; ticker=securities[sid]['ticker']
            require(quote['ticker']==ticker and quote['currency']=='USD','USD ticker mismatch')
            value=literal(quote['nominal_'+field]); require(Fraction(value)>0,'Nonpositive price')
            output[sid]=value
            observed[sid]={'literal':value,'reference':pointer(ref,f'/nominal_quotes/by_ticker/{ticker}/rows/{index}/nominal_{field}')}
        evidence.append({'session':day,'field':field,'quotes':observed})
        return output
    initial={'session':start,'cash_usd':row['starting_cash_usd'],'holdings':deepcopy(row['holdings']),'close_prices':marks(start,'close')}
    sessions=[{'session':day,'open_prices':marks(day,'open'),'close_prices':marks(day,'close'),
        'cash_injection_usd':row['cash_event']['amount_usd'] if i==0 else '0'} for i,day in enumerate(calendar[1:])]
    saved=[(i,entry) for i,entry in enumerate(nominal['execution']['daily']) if entry['session']==start]
    require(len(saved)==1 and saved[0][1]==row['original_inventory_row']['baseline'],'Initial old account baseline mismatch')
    require(saved[0][1]['shares']==initial['holdings'] and literal(saved[0][1]['cash_usd'])==initial['cash_usd'],'Initial state differs from saved baseline')
    planned=[(i,entry) for i,entry in enumerate(nominal['execution']['decisions']) if entry['decision_date']==start]
    require(len(planned)==1,'Saved initial decision missing')
    return {'core_inputs':{'initial':initial,'sessions':sessions,'fixed_weights':{sid:literal(first[sid]['target_weight']) for sid in sids},
        'schedule':[{'decision_date':item['decision_date'],'execution_date':item['execution_date']} for _,item in selected],
        'securities':securities,'risk_parameters':deepcopy(row['risk_parameters']),
        'transaction_cost_bps':row['transaction_cost_bps'],'minimum_cash_buffer_usd':row['minimum_cash_buffer_usd']},
        'quote_evidence':evidence,'quote_encoding':'SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE',
        'baseline_reference':pointer(ref,f'/execution/daily/{saved[0][0]}'),
        'initial_saved_decision':deepcopy(planned[0][1]),'initial_saved_decision_reference':pointer(ref,f'/execution/decisions/{planned[0][0]}'),
        'schedule_evidence':[{'source_row':deepcopy(item),'reference':pointer(ref,f'/original_fixed_schedule/schedule/{index}'),
            'risk_labels':deepcopy(fixed['risk_chains_by_decision'][item['decision_date']]),
            'risk_observation_date':item['decision_date'],'risk_reference':pointer(ref,f'/original_fixed_schedule/risk_chains_by_decision/{item["decision_date"]}')} for index,item in selected]}


def assemble(inputs,nominal,refs,simulate):
    groups=grouped_rows(inputs); paths=[]; mappings=[]
    for (decision,amount),members in sorted(groups.items()):
        row=members[0][1]; prepared=prepare_path(row,nominal,refs['nominal'])
        result=simulate(**prepared['core_inputs'])
        require(result['decisions'][0]['desired_shares']==prepared['initial_saved_decision']['desired_shares']
                and result['decisions'][0]['delta']==prepared['initial_saved_decision']['delta'],'Initial unannounced-flow plan differs from original saved decision')
        contract=prepared['core_inputs']
        require(result['schema']=='SIGNED_FLOW_FROZEN_INCUMBENT_OPEN_ACCOUNT_V1'
                and result['flow_policy']=='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN','Core output contract differs')
        for flag in ('weights_normalized','risk_is_order_gate','open_replan_performed','orders_executed',
                     'point_in_time_verified','promotion_allowed','old_experiments_executed',
                     'dividends_modelled','corporate_actions_modelled','fx_modelled'):
            require(result[flag] is False,'Core authority changed: '+flag)
        require(result['initial']==contract['initial'] and result['sessions']==contract['sessions']
                and result['schedule']==contract['schedule'] and result['original_fixed_weights']==contract['fixed_weights'],
                'Core input preservation differs')
        require([item['session'] for item in result['daily']]==[item['session'] for item in contract['sessions']]
                and [(item['decision_date'],item['execution_date']) for item in result['decisions']]
                    ==[(item['decision_date'],item['execution_date']) for item in contract['schedule']],
                'Core observed calendar or decisions differ')
        require(Fraction(result['total_cash_injection_usd'])==Fraction(amount)
                and all(Fraction(actual['cash_injection_usd'])==Fraction(source['cash_injection_usd'])
                        for actual,source in zip(result['daily'],contract['sessions'])),'Cash event timing differs')
        path_id=decision+'|'+amount
        paths.append({'path_id':path_id,'prepared':prepared,'account':result,
            'same_original_first_decision_shares_verified':True,'old_float_monetary_bitwise_equivalence_claimed':False,**FLAGS})
        for index,member in members:
            mappings.append({'scenario_id':member['scenario_id'],'path_id':path_id,
                'input_reference':pointer(refs['inputs'],f'/rows/{index}'),'original_input_row':deepcopy(member)})
    metadata=deepcopy(nominal)
    metadata.pop('execution')
    for channel in metadata['nominal_quotes']['by_ticker'].values(): channel.pop('rows')
    return {'schema':'INCUMBENT_SAME_FLOW_TEN_PATHS_FORTY_SCENARIOS_V1','paths':paths,'scenario_mappings':mappings,
        'path_count':10,'scenario_count':40,'parent_nominal_metadata':metadata,
        'parent_input_sources_preserved_not_reaudited':deepcopy(inputs['source_hashes']),
        'flow_policy':'FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN','future_decisions_use_counterfactual_own_state':True,
        'deduplication':'EXACT_INITIAL_STATE_FLOW_AND_ORIGINAL_POLICY_EQUALITY_ACROSS_FOUR_LANES',**FLAGS}


def sha(raw): return hashlib.sha256(raw).hexdigest()


def write_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output bytes differ')
    return sha(raw)


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source changed')
    sources={str(SOURCE):LOADED_SHA}; refs={}; documents={}
    for role,(relative,digest) in PINS.items():
        require(len(digest)==64,'Pending source pin'); path=ROOT/relative; raw=path.read_bytes()
        require(sha(raw)==digest,'Source mismatch: '+role); sources[str(path)]=digest; refs[role]={'path':str(path),'sha256':digest}
        if role in ('inputs','input_publication','nominal'): documents[role]=json.loads(raw)
    receipt=documents['input_publication']; inputs=documents['inputs']
    require({p.name for p in Path(refs['inputs']['path']).parent.iterdir()}=={'inputs.json','publication.json'},'Input namespace incomplete')
    require(receipt['schema']=='REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1' and receipt['status']=='INPUTS_ONLY_NOT_EXECUTED'
            and receipt['input_reference']==refs['inputs'] and receipt['source_hashes']==inputs['source_hashes'],'Input receipt differs')
    for flag in ('point_in_time_verified','orders_executed','promotion_allowed','fork_executable'):
        require(receipt[flag] is False,'Input authority changed')
    name='backtest.ndx_incumbent_cash_flow_research'; require(name not in sys.modules,'Fresh CLI required')
    module=importlib.import_module(name); require(Path(module.__file__).resolve()==Path(refs['core']['path']).resolve(),'Core path mismatch')
    def guard():
        require(all(sha(Path(path).read_bytes())==digest for path,digest in sources.items()),'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'source_hashes':sources,'started_at_utc':datetime.now(timezone.utc).isoformat(),'retry_allowed':False})
        result=assemble(inputs,documents['nominal'],refs,module.simulate_incumbent_cash_flow)
        result.update(source_hashes=sources,input_references=refs); guard()
        digest=write_new(OUTPUT/'accounts.json',result); guard()
        pubsha=write_new(OUTPUT/'publication.json',{'schema':'INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V1',
            'status':'PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS','account_reference':{'path':str(OUTPUT/'accounts.json'),'sha256':digest},'source_hashes':sources,**FLAGS}); guard()
        require(sha((OUTPUT/'accounts.json').read_bytes())==digest and sha((OUTPUT/'publication.json').read_bytes())==pubsha
                and {p.name for p in OUTPUT.iterdir()}=={'started.json','accounts.json','publication.json'},'Final publication mismatch')
        return {'path':str(OUTPUT/'accounts.json'),'sha256':digest,'publication_sha256':pubsha}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
