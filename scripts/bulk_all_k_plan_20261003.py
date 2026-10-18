"""All issuer cardinalities as lazy integer intervals, never enumerate portfolios."""
import argparse
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from backtest import ndx_issuer_shard_prepare_research as contracts
indexing=contracts.indexing;bounds=contracts.bounds
SOURCE=Path(__file__).resolve();OUTPUT=ROOT/'data/cache/research/bulk_all_k_plan_20261003_v1'
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,
 min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
PINS={
 'panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
 'publication':('data/cache/research/bulk_conditional_panel_20261003_v1/publication.json','895b1d0f71fb3f4b1175845c3390f3d286c672519fa4aa2c0a13bb930f6a2a9d'),
 'audit':('DYNAMIC_BULK_CONDITIONAL_PANEL_INDEPENDENT_READBACK_20261003.md','8a432b70dfc3393850242873b700eb54097bec9981c8f488cc88bd578295c879'),
 'audit_reader':('scripts/ndx_bulk_conditional_panel_independent_review_20261003.py','5a3d35ba39e6a719dfafaa3e4e348f065c5cd297c403a08e087c78f02c5c1b0b'),
 'old_plan':('data/cache/research/new_cutoff_shard_prepare_20260925_v6/plan.json','c18b54c1f1aa41f7833f0b88a8fa7270b3eb0bc7c8ea0cebb0628c3645a78dd9')}
HARD={str(Path(contracts.__file__).resolve()):'722f48952a6d0c8c878df76eedeb0b8ca3b1e3feeb77560598414890ae00a4ec',**contracts.HARD_SOURCES}
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),**contracts.LOADED,**bounds._LOADED}
FALSE=dict.fromkeys(('combination_enumeration_performed','task_inputs_materialized','fit_performed','old_fit_results_reused',
 'old_plan_build_called','panel_audit_repeated','execution_authorized','point_in_time_verified','promotion_allowed',
 'legal_training_input_admitted','full_transitive_source_closure_reverified','complete_ndx_eligible_pool_verified',
 'continuous_weight_space_exhausted','winner_selected','dual_benchmark_evaluation_performed','oos_evaluation_performed'),False)
require=contracts.require;digest=contracts.digest


def prepare_lazy_plan(*,groups,panel_reference,panel_audit_reference,decision_cutoff,parameters,
                      fitter_source_hashes,previous_target_weights,shard_size=1000):
    require(type(shard_size) is int and 1<=shard_size<=10000,'Exact shard size1..10000')
    require(parameters==PARAMETERS,'Original eight parameters required')
    params=contracts.parameters_contract(parameters);prior=contracts.previous_contract(previous_target_weights)
    sources=contracts.source_map(fitter_source_hashes)
    panel=contracts.reference(panel_reference);audit=contracts.reference(panel_audit_reference)
    require(panel['path']!=audit['path'],'Independent audit reference')
    from datetime import date
    require(type(decision_cutoff) is str and date.fromisoformat(decision_cutoff).isoformat()==decision_cutoff,'Canonical cutoff')
    require(type(groups) in (list,tuple) and 0<len(groups)<=256 and sum(len(pair[1]) for pair in groups)<=512,'Engineering group bound')
    index=indexing.IssuerCombinationIndex(groups)
    context={'plan_version':'ISSUER_ALL_K_LAZY_INTERVAL_PLAN_V1','order_version':indexing.ORDER_VERSION,
        'group_fingerprint':index.group_fingerprint,'panel_reference':panel,'panel_audit_reference':audit,
        'decision_cutoff':decision_cutoff,'parameters':params,'fitter_source_fingerprint':digest(sources),
        'previous_target_weights':prior,'weight_specs':list(contracts.WEIGHT_SPECS),'shard_size':shard_size,
        'mathematical_source_fingerprint':digest(LOADED)}
    cards=[];excluded=planned=shards=0
    risk={key:Fraction(str(params[key])) for key in bounds._RISK_KEYS}
    for k,total in index.counts_by_k().items():
        certificates=deepcopy(bounds._necessary_bounds(k,risk));count=0 if certificates else total
        shard_count=(count+shard_size-1)//shard_size
        cards.append({'k':k,'combination_count':total,'necessary_bound_certificates':certificates,
            'status':'NECESSARY_BOUND_EXCLUDED' if certificates else 'PLANNED_NOT_ENUMERATED',
            'planned_combination_count':count,'planned_canonical_task_count':3*count,
            'planned_shard_count':shard_count,'first_global_shard_ordinal':shards,
            'first_global_planned_combination_ordinal':planned,
            'interval_rule':{'start':0,'stop':count,'shard_size':shard_size}})
        shards+=shard_count;planned+=count;excluded+=total if certificates else 0
    plan={'schema':context['plan_version'],'plan_id':digest(context),'context':context,
        'canonical_groups':[{'issuer_id':issuer,'security_ids':list(sids)} for issuer,sids in zip(index.issuer_ids,index.security_groups)],
        'cardinalities':cards,'issuer_count':len(index.issuer_ids),'security_count':sum(map(len,index.security_groups)),
        'all_k_combination_count':planned+excluded,'necessary_bound_excluded_combination_count':excluded,
        'planned_combination_count':planned,'planned_canonical_task_count':3*planned,
        'completed_canonical_task_count':0,'remaining_canonical_task_count':3*planned,'planned_shard_count':shards,
        'fitter_source_hashes':sources,'status':'PLANNED_NOT_ENUMERATED','shard_descriptors_materialized':False,
        'integer_encoding':'JSON_INTEGER_REQUIRE_ARBITRARY_PRECISION_PYTHON_INT_NOT_FLOAT_OR_JS_NUMBER',
        'shard_page_limit':1000,'page_limit_is_not_search_budget_or_denominator_limit':True,
        'all_three_specs_planned_without_alias_deduplication':True,'anchor_alias_equivalence_verified':False,
        'risk_feasibility_proven':False,'conservative_bound_contract':{
            'risk_tolerance':str(bounds._RISK_TOLERANCE),'simplex_tolerance':str(bounds._SIMPLEX_TOLERANCE),
            'rounding_margin_per_term':str(bounds._ROUNDING_MARGIN_PER_TERM),'source_hashes':deepcopy(HARD)},**FALSE}
    plan['content_sha256']=digest(plan)
    return plan


def get_shard_slice(plan,*,k,shard_start,shard_stop):
    """Return only requested descriptors, never any portfolio selections."""
    require(all(type(value) is int for value in (k,shard_start,shard_stop)),'Exact integer page coordinates')
    require(0<=shard_start<=shard_stop and shard_stop-shard_start<=1000,'Bounded page request required; no truncation')
    require(plan['schema']=='ISSUER_ALL_K_LAZY_INTERVAL_PLAN_V1','Lazy schema')
    unsigned=dict(plan);saved=unsigned.pop('content_sha256');require(digest(unsigned)==saved,'Plan content changed')
    require(1<=k<=plan['issuer_count'],'Public k range')
    card=plan['cardinalities'][k-1];require(card['k']==k and shard_stop<=card['planned_shard_count'],'Shard interval out of range')
    context=plan['context'];size=context['shard_size'];result=[]
    for local in range(shard_start,shard_stop):
        start=local*size;stop=min(start+size,card['planned_combination_count'])
        identity={**context,'k':k,'start':start,'stop':stop}
        result.append({**identity,'shard_id':digest(identity),'plan_id':plan['plan_id'],
            'ordinal':card['first_global_shard_ordinal']+local,'local_shard_ordinal':local,
            'first_global_planned_task_ordinal':3*(card['first_global_planned_combination_ordinal']+start),
            'combination_count':stop-start,'planned_canonical_task_count':3*(stop-start),
            'status':'PLANNED_NOT_ENUMERATED','completed_canonical_task_count':0,'remaining_canonical_task_count':3*(stop-start)})
    return result


def assemble(documents,refs):
    panel=documents['panel'];old=documents['old_plan']['plan'];inner=panel['panel']
    require(panel['schema']=='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and inner['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1','New bulk schema')
    require(documents['publication']['panel_reference']==refs['panel'] and documents['publication']['source_hashes']==panel['source_hashes']
        and documents['publication']['status']=='PUBLISHED_CONDITIONAL_PANEL_ONLY','Panel receipt')
    for key in ('point_in_time_verified','legal_training_input_admitted','promotion_allowed','fit_performed'):
        require(panel[key] is False and inner[key] is False,'Parent authority')
    require(old['context']['parameters']==PARAMETERS and old['context']['weight_specs']==list(contracts.WEIGHT_SPECS)
        and old['context']['previous_target_weights'] is None and len(old['fitter_source_hashes'])==25,'Frozen numerical contract')
    universe=inner['universe'];require(universe['type']=='dataframe' and universe['index_kind']=='RangeIndex','Typed universe')
    columns=universe['columns'];rows=universe['data'];require(len(rows)==77 and len(universe['index'])==77 and len(universe['dtypes'])==len(columns),'Typed universe size')
    require(all(len(row)==len(columns) for row in rows),'Rectangular universe')
    records=[dict(zip(columns,row)) for row in rows];sids=[row['security_id'] for row in records]
    require(sids==sorted(set(sids)) and len({row['issuer_id'] for row in records})==76,'77SID76issuer')
    tickers=[row['ticker'] for row in records]
    require(all(type(ticker) is str and ticker.strip()==ticker and ticker for ticker in tickers)
        and len(set(tickers))==77,'Unique explicit ticker mapping')
    require(all(type(row['risk_chain']) is str and row['risk_chain'].strip() for row in records),'Explicit saved risk labels')
    returns=inner['returns']
    require(returns['type']=='dataframe' and returns['index_kind']=='DatetimeIndex' and
        returns['columns']==sorted(tickers) and returns['dtypes']==['float64']*77 and
        len(returns['index'])==len(returns['data'])==126 and inner['cutoff']=='2026-09-21','Returns ticker coordinate metadata')
    days=[]
    for timestamp in returns['index']:
        require(type(timestamp) is str and timestamp==timestamp[:10]+'T00:00:00' and
            date.fromisoformat(timestamp[:10]).isoformat()==timestamp[:10],'Exact observed return timestamp')
        days.append(timestamp[:10])
    require(days==sorted(set(days)) and days[-1]==inner['cutoff'],'Exact126 cutoff return dates')
    require(all(type(row) is list and len(row)==77 and all(type(number) in (int,float) and
        math.isfinite(number) and number>-1 for number in row) for row in returns['data']),'Complete finite return cells')
    groups={}
    for row in records:groups.setdefault(row['issuer_id'],[]).append(row['security_id'])
    plan=prepare_lazy_plan(groups=list(groups.items()),panel_reference=refs['panel'],panel_audit_reference=refs['audit'],
        decision_cutoff=inner['cutoff'],parameters=PARAMETERS,fitter_source_hashes=old['fitter_source_hashes'],previous_target_weights=None)
    sidecars={key:{**refs['panel'],'json_pointer':'/'+key} for key in panel if 'evidence_and_projection' in key}
    return {'schema':'BULK_ALL_K_LAZY_PLAN_V1','plan':plan,'panel_content_sha256':inner['panel_content_sha256'],
        'input_references':deepcopy(refs),'complete_observed_provenance_and_missing':deepcopy(inner['observed_provenance_and_missing']),
        'preserved_evidence_sidecar_references':sidecars,'old_completed_tasks_deducted':0,
        'old_completed_numeric_identity_rebinding_required':True,'conditional_security_count':77,'conditional_issuer_count':76,
        'policy':'ALL_K_MATHEMATICAL_PLAN_NOT_SEARCH_OR_FIT',**FALSE}


def guard(sources):
    require(all(LOADED.get(path)==digest for path,digest in HARD.items()),'Frozen math source differs')
    require(all(path not in sources or sources[path]==digest for path,digest in LOADED.items()),'Loaded source hash conflict')
    for path,digest in {**sources,**LOADED}.items():require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Source drift')


def write_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Readback changed')
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry');sources=dict(LOADED);docs={};refs={}
    for role,(relative,digest) in PINS.items():
        path=ROOT/relative;raw=path.read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'Pinned input changed')
        sources[str(path)]=digest;refs[role]={'path':str(path),'sha256':digest}
        if role not in ('audit','audit_reader'):docs[role]=json.loads(raw)
    for path,digest in docs['old_plan']['plan']['fitter_source_hashes'].items():
        require(path not in sources or sources[path]==digest,'Source conflict');sources[path]=digest
    guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'source_hashes':sources,'retry_allowed':False,**FALSE})
        value=assemble(docs,refs);value['source_hashes']=sources;guard(sources)
        result=write_new(OUTPUT/'plan.json',value);guard(sources)
        receipt=write_new(OUTPUT/'publication.json',{'schema':'BULK_ALL_K_LAZY_PLAN_PUBLICATION_V1','status':'PLANNED_NOT_ENUMERATED',
            'plan_reference':result,'source_hashes':sources,**FALSE});guard(sources)
        for ref in (result,receipt):require(hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()==ref['sha256'],'Final readback')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','plan.json','publication.json'},'Unexpected output')
        return {'plan_reference':result,'publication_reference':receipt}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False});raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute:parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
