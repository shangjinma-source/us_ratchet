"""Immutable saved NAV/USD diagnostic alignment; no accounts or return metrics."""
import argparse
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_nav_usd_observation_alignment_research.py';CORE_SHA='9c5c68453c3796f1f33656a2d8a0a16bd172ef00c2d8e02fc4f1b9ee69a2fb84'
OUTPUT=ROOT/'data/cache/research/nav_usd_observation_alignment_20261003_v1'
BOUND={
'requirements':('data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1/requirements.json','95461ba7b298347d969fe65cb3b93aa5632fecfdf331f1ba7a42af6abdee1c47'),
'requirements_publication':('data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1/publication.json','bf9290f263f92523d7bd2001d138321ef429705aa96ec494e665ec15dead8766'),
'nav_csv':('data/cache/research/new_cutoff_nav_snapshot_20260923_v1/nav.csv','020f3e636c732259dedb796606de49b89a0ee7df0263442ddae5f3e73dc76d1f'),
'nav_manifest':('data/cache/research/new_cutoff_nav_snapshot_20260923_v1/original_manifest.json','dcb18867c3b4f75192927ca66f05ad972490bbf6b45f0aea275af4547575ae38'),
'nav_snapshot':('data/cache/research/new_cutoff_nav_snapshot_20260923_v1/snapshot.json','7b2303f0ab5618ef35790d24637681e8ce58463f846ef303bf62acf7fa681061'),
'fx_readback':('DYNAMIC_OFFICIAL_FX_INDEPENDENT_READBACK_20261003.json','af62ce707f9208255f9158410ab05767c576c755df2b26c4c404dde350e60d53'),
'fx_manifest':('data/cache/research/official_fx_capture_20261003_v1/manifest.json','9e14efd21143687374425e7759c1f468a8cd99009164167f5b60f43fa96898e4'),
}
FLAGS=dict.fromkeys(('http_performed','old_audit_repeated','account_executed','returns_computed','drawdown_computed','fit_performed','mode_selected_using_results','point_in_time_verified','promotion_allowed','execution_authorized','benchmark_qualified','legal_training_input_admitted','historical_nav_currency_verified','historical_available_at_verified','full_transitive_source_closure_reverified'),False)


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
    def reject(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=reject)


def project_inputs(docs,refs):
    parent=docs['requirements'];pub=docs['requirements_publication'];req=parent['requirements']
    require(parent['schema']=='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1' and req['schema']=='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1','Requirements schema')
    require(pub['status']=='PUBLISHED_REQUIREMENTS_ONLY','Requirements publication')
    exact(pub['requirements_reference'],refs['requirements'],'Requirements reference');exact(pub['source_hashes'],parent['source_hashes'],'Requirements source closure')
    for item in (parent,req,pub):require(all(item[k] is False for k in ('point_in_time_verified','benchmark_qualified','execution_authorized')),'Requirements authority changed')
    require(req['content_sha256']==sha(encode({k:v for k,v in req.items() if k!='content_sha256'})),'Requirement content digest')
    calendar=req['reference_calendar']['dates'];require(len(calendar)==253 and calendar==sorted(set(calendar)) and calendar[0]=='2025-09-18' and calendar[126]=='2026-03-20' and calendar[-1]=='2026-09-21','Complete exact 253 window')
    navmeta=req['nav_metadata_preserved'];exact(navmeta['source_reference'],refs['nav_csv'],'Requirements NAV source')
    require(navmeta['publication_time_known'] is False and navmeta['selected_value_column']=='Close','Original NAV convention')
    snapshot=docs['nav_snapshot'];manifest=docs['nav_manifest']
    require(snapshot['schema']=='NEW_CUTOFF_LOCAL_NAV_BYTES_SNAPSHOT_V1' and snapshot['dataset_key']=='012922' and snapshot['nav_publication_time_verified'] is False,'Saved NAV snapshot')
    exact(snapshot['immutable_copies']['nav.csv'],refs['nav_csv'],'Snapshot CSV reference');exact(snapshot['immutable_copies']['original_manifest.json'],refs['nav_manifest'],'Snapshot manifest reference')
    require(manifest['content_sha256']==refs['nav_csv']['sha256'] and manifest['publication_time_known'] is False and type(manifest['row_count']) is int and manifest['row_count']==1101,'NAV manifest scope')
    rawrows=docs['nav_csv'];require(len(rawrows)==1101 and len(navmeta['rows'])==1101,'Full1101 NAV rows')
    nav=[]
    for i,row in enumerate(rawrows):
        require(set(row)=={'Date','UnitNav','AccumNav','DailyPct','Close'} and all(type(v) is str for v in row.values()),'Complete original NAV CSV fields')
        require(row['Close']==row['UnitNav'],'Saved Close is UnitNav, not AccumNav')
        exact(navmeta['rows'][i],dict(date=row['Date'],row_index=i,source_reference=refs['nav_csv']),'Original requirements NAV row coordinate')
        nav.append(dict(date=row['Date'],nav_cny_decimal=row['Close'],available_at=None,source_reference=dict(refs['nav_csv'],row_index=i,csv_record_number=i+2),original_csv_row=deepcopy(row)))
    fx=docs['fx_readback'];capture=docs['fx_manifest']
    require(fx['schema']=='OFFICIAL_FX_INDEPENDENT_SAVED_READBACK_V1' and fx['status']=='PASS' and fx['manifest_sha256']==refs['fx_manifest']['sha256'],'Official saved readback')
    require(capture['schema']=='OFFICIAL_FX_SOURCE_CAPTURE_V1' and capture['status']=='SAVED_SOURCE_ONLY','Official capture manifest')
    for item in (fx,capture):require(item['historical_available_at_verified'] is False and item['point_in_time_verified'] is False and item['benchmark_qualified'] is False,'FX authority changed')
    sources={r['name']:r for r in capture['sources']};require(set(sources)=={'country_data','china_history','fred_series'},'All three official sources')
    exact(sources,fx['source_references'],'Capture/readback source references')
    require(len(fx['table_rows'])==6975 and type(fx['summary']['table_row_count']) is int and fx['summary']['table_row_count']==6975,'Full6975 saved FX rows')
    require([r['session'] for r in fx['window_253']]==calendar,'Official readback full window')
    for i,row in enumerate(fx['table_rows']):
        ref=row['source_reference'];require(type(ref['table_row_index']) is int and ref['table_row_index']==i,'Original FX table index')
        require(ref['path']==sources['china_history']['raw']['path'] and ref['sha256']==sources['china_history']['raw']['sha256'],'FX raw row attribution')
    context={k:deepcopy(fx[k]) for k in ('rate_direction','historical_available_at_verified','page_release_label','limitations','source_references','frequency','official_clauses','receipts')}
    return dict(session_dates=deepcopy(calendar),nav_rows=nav,fx_rows=deepcopy(fx['table_rows']),nav_reference=deepcopy(refs['nav_csv']),fx_reference=deepcopy(refs['fx_readback']),fx_context=context)


def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper source drift')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Direct source drift: '+p)


def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64,'Reviewed core pin pending')
    docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    def read(path,h):
        path=path.resolve();require(str(path) not in sources or sources[str(path)]==h,'Conflicting source pin')
        blob=path.read_bytes();require(sha(blob)==h,'Source bytes differ: '+str(path));sources[str(path)]=h;return blob
    for role,(relative,h) in BOUND.items():
        p=ROOT/relative;blob=read(p,h);refs[role]=dict(path=str(p.resolve()),sha256=h)
        if role=='nav_csv':
            csvreader=csv.DictReader(io.StringIO(blob.decode('utf-8-sig')));require(csvreader.fieldnames==['Date','UnitNav','AccumNav','DailyPct','Close'],'Exact NAV columns');docs[role]=list(csvreader)
        else:docs[role]=loads(blob)
    for role in ('requirements','fx_manifest'):
        require(not (Path(refs[role]['path']).parent/'failure.json').exists(),'Parent namespace failed')
    require({p.name for p in Path(refs['requirements']['path']).parent.iterdir()}=={'started.json','requirements.json','publication.json'},'Requirements namespace incomplete/unexpected')
    fx=docs['fx_readback'];require(fx['manifest_sha256']==refs['fx_manifest']['sha256'],'FX manifest binding')
    for source in fx['source_references'].values():
        for role in ('raw','receipt'):
            r=source[role];read(ROOT/r['path'],r['sha256'])
    for filename,h in [('scripts/ndx_official_fx_independent_review_20261003.py',fx['reader_sha256']),('scripts/ndx_official_fx_capture_20261003.py',docs['fx_manifest']['source_sha256'])]:read(ROOT/filename,h)
    corebytes=read(CORE,CORE_SHA);guard(sources)
    core=types.ModuleType('_fresh_nav_usd_alignment');core.__file__=str(CORE);exec(compile(corebytes,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,core


def validate_result(result,args):
    require(result['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_V1' and len(result['rows'])==253,'Alignment full window')
    exact(result['session_dates'],args['session_dates'],'Result calendar');exact(result['nav_rows_preserved'],args['nav_rows'],'Full NAV rows');exact(result['fx_rows_preserved'],args['fx_rows'],'Full FX rows')
    exact(result['modes'],['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'],'Both modes required')
    require(all(result[k] is False for k in ('point_in_time_verified','benchmark_qualified','returns_computed','drawdown_computed','mode_selected_using_results','account_executed')),'Result permission')
    require(result['content_sha256']==sha(encode({k:v for k,v in result.items() if k!='content_sha256'})),'Result digest')


def save(path,value):
    blob=encode(value)
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Written bytes differ');return dict(path=str(path),sha256=sha(blob))


def run(*,execute=False):
    require(type(execute) is bool,'Exact execute boolean')
    require(not OUTPUT.exists(),'Immutable namespace already exists')
    if not execute:return dict(status='NOT_EXECUTED',output=str(OUTPUT))
    docs,refs,sources,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,retry_allowed=False,**FLAGS))
        args=project_inputs(docs,refs);result=core.align_nav_usd_observations(**args);validate_result(result,args)
        document=dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_DOCUMENT_V1',alignment=result,input_references=refs,source_hashes=sources,requirements_reference_preserved=refs['requirements'],original_requirements_source_hashes_preserved=docs['requirements']['source_hashes'],nav_manifest_preserved=docs['nav_manifest'],nav_snapshot_preserved=docs['nav_snapshot'],fx_capture_manifest_preserved=docs['fx_manifest'],prior_unbound_fx_requirement_not_overwritten=True,**FLAGS)
        guard(sources);out=save(OUTPUT/'alignment.json',document);guard(sources)
        pub=save(OUTPUT/'publication.json',dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_CONVERSION_ONLY',alignment_reference=out,source_hashes=sources,**FLAGS))
        guard(sources);require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(pub['path']).read_bytes())==pub['sha256'],'Final publication readback')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','alignment.json','publication.json'},'Unexpected output namespace')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),retry_allowed=False));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(execute=args.execute)))
