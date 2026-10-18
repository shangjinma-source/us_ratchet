"""Source-bound external reference metrics, never fund subscription execution."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_same_window_nav_reference_metrics_research.py';CORE_SHA='bfb582e72dd3a23da5da4898d633d5afa310af0132aa16bb6896ebcac0d82a4f'
OUTPUT=ROOT/'data/cache/research/same_window_nav_reference_metrics_20261003_v1'
BOUND={
 'alignment':('data/cache/research/nav_usd_observation_alignment_20261003_v1/alignment.json','ddd36e3bd3236d1494d9e42e08e66ce88e09d06c6c16f133c0214a951d54d90a'),
 'alignment_publication':('data/cache/research/nav_usd_observation_alignment_20261003_v1/publication.json','f1c1e0c75fbdd1da09d590a3e534fb8bb39671f2cdd6d4c796c6ba9f86080878'),
 'alignment_audit':('DYNAMIC_NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_20261003.json','53cba7de3d78cbf6b0fff8d00e77daf429ac497b75a021f0a8e2db7da1fe1ca9'),
 'alignment_audit_reader':('scripts/ndx_nav_usd_alignment_independent_review_20261003.py','8bf0f70985932f2413144c6135ec0b5df81c619172b5baa24ffd49d4e8449675'),
 'requirements':('data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1/requirements.json','95461ba7b298347d969fe65cb3b93aa5632fecfdf331f1ba7a42af6abdee1c47'),
 'requirements_publication':('data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1/publication.json','bf9290f263f92523d7bd2001d138321ef429705aa96ec494e665ec15dead8766'),
 'panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
}
FLAGS=dict.fromkeys(('http_performed','old_audit_repeated','raw_sources_reaudited','account_executed','subscription_redemption_modeled','fit_performed','mode_selected_using_results','point_in_time_verified','promotion_allowed','execution_authorized','benchmark_qualified','formal_comparison_passed','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','legal_training_input_admitted','historical_nav_currency_verified','historical_available_at_verified','full_transitive_source_closure_reverified','future_independent_oos','untouched_holdout'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def loads(raw):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON literal')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)

def project_inputs(docs,refs):
    outer=docs['alignment'];pub=docs['alignment_publication'];audit=docs['alignment_audit'];parent=docs['requirements'];req=parent['requirements'];rp=docs['requirements_publication'];panel=docs['panel']
    require(outer['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_DOCUMENT_V1' and pub['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_CONVERSION_ONLY','Alignment publication schema')
    exact(pub['alignment_reference'],refs['alignment'],'External alignment bytes');exact(pub['source_hashes'],outer['source_hashes'],'Alignment publication source map')
    require(audit['schema']=='NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['alignment_sha256']==refs['alignment']['sha256'] and audit['publication_sha256']==refs['alignment_publication']['sha256'] and audit['reader_sha256']==refs['alignment_audit_reader']['sha256'],'Independent arithmetic source binding')
    require(parent['schema']=='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1' and req['schema']=='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1' and rp['schema']=='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1' and rp['status']=='PUBLISHED_REQUIREMENTS_ONLY','Benchmark requirement schema')
    exact(rp['requirements_reference'],refs['requirements'],'Requirement receipt reference');exact(rp['source_hashes'],parent['source_hashes'],'Requirement receipt sources');exact(outer['requirements_reference_preserved'],refs['requirements'],'Alignment original requirement')
    exact(outer['input_references']['requirements'],refs['requirements'],'Alignment input requirement');exact(outer['input_references']['requirements_publication'],refs['requirements_publication'],'Alignment input receipt')
    for v in (outer,pub,audit,parent,rp):require(all(v[k] is False for k in ('point_in_time_verified','benchmark_qualified','account_executed')) if v is audit else all(v[k] is False for k in ('point_in_time_verified','benchmark_qualified','execution_authorized')),'No input authority upgrade')
    require(req['content_sha256']==sha(encode({k:v for k,v in req.items() if k!='content_sha256'})),'Requirement checksum')
    all_dates=req['reference_calendar']['dates'];require(len(all_dates)==253 and all_dates[126]=='2026-03-20' and all_dates[-1]=='2026-09-21','Fixed253 requirement scope')
    dates=[req['evaluation_initial_close_date']]+req['evaluation_return_end_dates'];exact(dates,all_dates[126:],'InitialClose plus126 individual dates');require(len(dates)==127 and dates[0]=='2026-03-20' and dates[-1]=='2026-09-21','New reference127 calendar')
    exact(outer['alignment']['session_dates'],all_dates,'Same full alignment calendar')
    require(panel['schema']=='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and panel['panel']['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1','Saved panel scope')
    exact(panel['panel']['returns']['index'],[d+'T00:00:00' for d in dates[1:]],'Old fit interval confirms consumed126, not NAV input')
    require(panel['fit_performed'] is False and panel['point_in_time_verified'] is False,'Panel authority')
    return dict(alignment=deepcopy(outer['alignment']),alignment_reference=deepcopy(refs['alignment']),reference_calendar=dict(dates=deepcopy(dates),source_reference=dict(refs['requirements'],json_pointer='/requirements'),initial_close_pointer='/requirements/evaluation_initial_close_date',interval_end_dates_pointer='/requirements/evaluation_return_end_dates'))

def validate_result(value,args):
    require(value['schema']=='SAME_WINDOW_NAV_REFERENCE_METRICS_V1' and value['status']=='HISTORICAL_EXTERNAL_REFERENCE_ONLY','Reference-only output')
    exact(value['reference_calendar'],args['reference_calendar'],'Output calendar');exact(value['alignment_reference'],args['alignment_reference'],'Output source');exact(value['mode_order'],['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'],'Both modes')
    require(set(value['modes'])==set(value['mode_order']) and value['modes_retained_separately'] is True,'Separate complete modes')
    for k in ('point_in_time_verified','benchmark_qualified','formal_comparison_passed','cohort_statistics_computed','account_executed','mode_selected_using_results','future_independent_oos','untouched_holdout'):require(value[k] is False,'Result authority')
    require(value['evaluation_interval_previously_used_for_candidate_fitting'] is True,'Historical consumed interval')
    for mode in value['mode_order']:
        row=value['modes'][mode];require(type(row['observation_count']) is int and row['observation_count']==127 and type(row['interval_count']) is int and row['interval_count']==126,'Fixed output dimensions')
        exact([r['session'] for r in row['observations']],args['reference_calendar']['dates'],'No compressed dates');require(len(row['interval_returns'])==126,'Complete interval slots')
        require((row['status']=='BLOCKED_MISSING_REFERENCE_INPUT' and bool(row['missing_sessions']) and row['metrics'] is None) or (row['status']=='RETROSPECTIVE_REFERENCE_METRICS_COMPUTED' and row['missing_sessions']==[] and row['metrics'] is not None),'Explicit numeric/missing mode')
    require(value['content_sha256']==sha(encode({k:v for k,v in value.items() if k!='content_sha256'})),'Result content hash')

def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Direct source drift '+path)
def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64 and all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Pending hard source pin')
    docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    for role,(relative,h) in BOUND.items():
        path=ROOT/relative;blob=path.read_bytes();require(sha(blob)==h,'Bound bytes');require(str(path) not in sources or sources[str(path)]==h,'Source conflict');sources[str(path)]=h;refs[role]=dict(path=str(path),sha256=h)
        if not role.endswith('_reader'):docs[role]=loads(blob)
    for role,filename in [('alignment','alignment.json'),('requirements','requirements.json')]:require({p.name for p in Path(refs[role]['path']).parent.iterdir()}=={'started.json',filename,'publication.json'},'Exact successful source namespace')
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Fresh core source');sources[str(CORE)]=CORE_SHA;guard(sources)
    core=types.ModuleType('_fresh_reference_metrics');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,core
def save(path,value):
    blob=encode(value)
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Durable output');return dict(path=str(path),sha256=sha(blob))
def run(*,execute=False):
    require(type(execute) is bool,'Exact execute bool');require(not OUTPUT.exists(),'Immutable reference namespace exists')
    if not execute:return dict(status='NOT_EXECUTED',output=str(OUTPUT))
    docs,refs,sources,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,input_references=refs,retry_allowed=False,**FLAGS))
        args=project_inputs(docs,refs);result=core.calculate_reference_metrics(**args);validate_result(result,args)
        document=dict(schema='SAME_WINDOW_NAV_REFERENCE_METRICS_DOCUMENT_V1',metrics=result,input_references=refs,source_hashes=sources,prior_fitting_interval_reference=dict(refs['panel'],json_pointer='/panel/returns/index'),requirements_reference=refs['requirements'],original_nav_manifest=deepcopy(docs['alignment']['nav_manifest_preserved']),original_nav_snapshot=deepcopy(docs['alignment']['nav_snapshot_preserved']),original_fx_capture_manifest=deepcopy(docs['alignment']['fx_capture_manifest_preserved']),**FLAGS)
        guard(sources);out=save(OUTPUT/'metrics.json',document);guard(sources)
        pub=save(OUTPUT/'publication.json',dict(schema='SAME_WINDOW_NAV_REFERENCE_METRICS_PUBLICATION_V1',status='PUBLISHED_RETROSPECTIVE_EXTERNAL_REFERENCE_ONLY',metrics_reference=out,source_hashes=sources,**FLAGS))
        guard(sources);require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(pub['path']).read_bytes())==pub['sha256'],'Final output bytes');require({p.name for p in OUTPUT.iterdir()}=={'started.json','metrics.json','publication.json'},'Exact namespace');return out
    except Exception as exc:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(exc),retry_allowed=False));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(execute=args.execute)))
