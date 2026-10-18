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
import shutil
from datetime import date,datetime,timezone

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_nav_usd_observation_alignment_research.py';CORE_SHA='9c5c68453c3796f1f33656a2d8a0a16bd172ef00c2d8e02fc4f1b9ee69a2fb84'
OUTPUT=ROOT/'data/cache/research/multidecision_target_scoring_inputs_20261003_v1'
TARGET_CORE=ROOT/'backtest/ndx_multidecision_target_scoring_inputs_research.py'
TARGET_CORE_SHA='e8f71288d19878b248589405c5696ace40f901e21ad03be1f8170202da389e10'
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
BOUND={
'history':('data/cache/research/bulk_history_requirements_20261003_v1/requirements.json','f3a317fd00800fe025003479358a6798cd893d4305511bcb1c39eb73ae94e2f5'),
'history_publication':('data/cache/research/bulk_history_requirements_20261003_v1/publication.json','171f4218d2ec3997b53d21d9e0e4c6081425ae963f79e7b7d0b3c5fa2ea5d13d'),
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
    calendar=full_calendar(docs,refs)
    first=calendar.index(CUTOFFS[0])-504;last=calendar.index(CUTOFFS[-1])+1
    calendar=calendar[first:last]
    return dict(session_dates=deepcopy(calendar),nav_rows=nav,fx_rows=deepcopy(fx['table_rows']),nav_reference=deepcopy(refs['nav_csv']),fx_reference=deepcopy(refs['fx_readback']),fx_context=context)


def full_calendar(docs,refs):
    d=docs['history'];p=docs['history_publication'];h=d['requirements']
    require(d['schema']=='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1' and h['schema']=='BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1','Original full calendar source')
    require(p['schema']=='BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1' and p['status']=='PUBLISHED_REQUIREMENTS_ONLY','History published')
    exact(p['requirements_reference'],refs['history'],'History publication binding');exact(p['source_hashes'],d['source_hashes'],'History preserved claims')
    for k in ('point_in_time_verified','execution_authorized','fit_performed'):require(d[k] is False,'History authority')
    c=h['reference_calendar'];require(c['ticker']=='AAPL','Reference provider');days=c['dates']
    require(type(days) is list and days==sorted(set(days)) and all(type(x) is str and date.fromisoformat(x).isoformat()==x and date.fromisoformat(x).weekday()<5 for x in days),'Full canonical calendar')
    require(days[-1]=='2026-09-21' and all(x in days and days.index(x)>=504 for x in CUTOFFS),'Six complete505 history')
    return days


def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper source drift')
    for role in ('history','requirements','fx_manifest','nav_snapshot'):
        require(not (ROOT/BOUND[role][0]).parent.joinpath('failure.json').exists(),'Parent failure '+role)
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Direct source drift: '+p)


def read_sources():
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
    read(CORE,CORE_SHA);guard(sources)
    return docs,refs,sources


def validate_result(result,args):
    require(result['schema']=='NAV_USD_OBSERVATION_ALIGNMENT_V1' and len(result['rows'])==len(args['session_dates']),'Alignment full window')
    exact(result['session_dates'],args['session_dates'],'Result calendar');exact(result['nav_rows_preserved'],args['nav_rows'],'Full NAV rows');exact(result['fx_rows_preserved'],args['fx_rows'],'Full FX rows')
    exact(result['modes'],['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'],'Both modes required')
    require(all(result[k] is False for k in ('point_in_time_verified','benchmark_qualified','returns_computed','drawdown_computed','mode_selected_using_results','account_executed')),'Result permission')
    require(result['content_sha256']==sha(encode({k:v for k,v in result.items() if k!='content_sha256'})),'Result digest')


TARGET_CONTRACT=dict(decision_cutoffs=CUTOFFS,price_count=505,return_count=504,fit_return_count=126,evaluation_return_count=126,step_return_count=21,window_count=13,target_modes=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'],native_cny_role='SOURCE_CONTEXT_NOT_USD_RANKING_TARGET',missing_policy='KEEP_SLOTS_BLOCK_FULL13_NO_PARTIAL_POOL',mode_selection_using_results_allowed=False)


def private_core(path,h):
    b=path.read_bytes();require(sha(b)==h,'Private source bytes changed');m=types.ModuleType('_private_'+path.stem);m.__file__=str(path);exec(compile(b,str(path),'exec'),m.__dict__);return m


def load_inputs():
    require(type(TARGET_CORE_SHA) is str and len(TARGET_CORE_SHA)==64,'Target core pin pending')
    docs,refs,sources=read_sources();b=TARGET_CORE.read_bytes();require(sha(b)==TARGET_CORE_SHA,'Target core bytes');sources[str(TARGET_CORE)]=TARGET_CORE_SHA;guard(sources)
    return docs,refs,sources,private_core(CORE,CORE_SHA),private_core(TARGET_CORE,TARGET_CORE_SHA)


def validate_targets(value,alignment_ref,calendar,alignment):
    require(value['schema']=='MULTIDECISION_TARGET_SCORING_INPUTS_V1' and value['status']=='CONDITIONAL_INPUT_PREPARATION_NOT_SCORING','Prepared target state')
    exact(value['contract'],TARGET_CONTRACT,'Fixed two-mode13window contract');exact(value['alignment_reference'],alignment_ref,'Saved alignment bytes');exact(value['alignment_preserved'],alignment,'No changed alignment')
    exact(value['reference_calendar_preserved'],calendar,'No calendar compression');exact(value['session_dates'],alignment['session_dates'],'Union dates')
    exact([x['mode'] for x in value['modes']],TARGET_CONTRACT['target_modes'],'Both FX modes')
    for k in ('source_bytes_authenticated','independent_alignment_verified','point_in_time_verified','benchmark_qualified','score_computed','fit_performed','account_executed','promotion_allowed','mode_selected_using_results','partial_window_pooling_allowed','missing_values_filled'):require(value[k] is False,'Target authority '+k)
    require(value['returns_computed'] is True and value['historical_retrospective_only'] is True,'Adjacent target arithmetic only')
    for mode in value['modes']:
        require(len(mode['price_slots'])==len(alignment['session_dates']) and len(mode['return_slots'])==len(alignment['session_dates'])-1 and len(mode['decisions'])==6,'All target slots')
        for d,c in zip(mode['decisions'],CUTOFFS):
            require(d['cutoff']==c and len(d['required_price_dates'])==505 and len(d['windows'])==13 and d['scoring_allowed'] is False and d['partial_window_pooling_allowed'] is False,'Complete13 or explicit blocked')
    require(value['content_sha256']==sha(encode({k:v for k,v in value.items() if k!='content_sha256'})),'Target content hash')


def save(path,value,failure=False):
    b=encode(value)
    if not failure:require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3+len(b),'5GiB plus encoded output')
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Output persisted');return dict(path=str(path),sha256=sha(b))


def run(*,execute=False):
    require(type(execute) is bool,'Exact execute boolean')
    if not execute:return dict(status='NOT_EXECUTED',output=str(OUTPUT))
    require(type(TARGET_CORE_SHA) is str and len(TARGET_CORE_SHA)==64,'Target core pin pending')
    require(not OUTPUT.exists(),'Immutable namespace exists')
    docs,refs,sources,aligner,target=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False);written=[]
    try:
        written.append(save(OUTPUT/'started.json',dict(schema='MULTIDECISION_TARGET_INPUTS_STARTED_V1',started_at_utc=datetime.now(timezone.utc).isoformat(),input_references=refs,source_hashes=sources,retry_allowed=False,**FLAGS)))
        args=project_inputs(docs,refs);alignment=aligner.align_nav_usd_observations(**args);validate_result(alignment,args)
        ar=save(OUTPUT/'alignment.json',alignment);written.append(ar)
        calendar=full_calendar(docs,refs)
        value=target.prepare_target_scoring_inputs(alignment=alignment,alignment_reference=ar,reference_calendar=calendar,contract=deepcopy(TARGET_CONTRACT));validate_targets(value,ar,calendar,alignment)
        tr=save(OUTPUT/'target_inputs.json',value);written.append(tr);guard(sources)
        index=dict(schema='MULTIDECISION_TARGET_SCORING_INPUTS_DOCUMENT_V1',status='PUBLISHED_CONDITIONAL_INPUTS_PENDING_INDEPENDENT_READBACK',alignment_reference=ar,target_inputs_reference=tr,input_references=refs,source_hashes=sources,contract=TARGET_CONTRACT,reference_calendar=deepcopy(docs['history']['requirements']['reference_calendar']),union_session_dates=args['session_dates'],nav_row_count=len(args['nav_rows']),fx_row_count=len(args['fx_rows']),mode_coverage=[dict(mode=m['mode'],decisions=[dict(cutoff=d['cutoff'],status=d['status'],blocked_window_count=sum(w['status']=='BLOCKED_WINDOW' for w in d['windows'])) for d in m['decisions']]) for m in value['modes']],original_requirements_source_hashes_preserved=docs['requirements']['source_hashes'],original_history_source_hashes_preserved=docs['history']['source_hashes'],nav_manifest_preserved=docs['nav_manifest'],nav_snapshot_preserved=docs['nav_snapshot'],fx_manifest_preserved=docs['fx_manifest'],score_computed=False,new_independent_numeric_readback_completed=False,**FLAGS)
        index['returns_computed']=True
        out=save(OUTPUT/'index.json',index);written.append(out)
        pub=save(OUTPUT/'publication.json',dict(schema='MULTIDECISION_TARGET_SCORING_INPUTS_PUBLICATION_V1',status=index['status'],index_reference=out,alignment_reference=ar,target_inputs_reference=tr,source_hashes=sources,input_references=refs,score_computed=False,**{**FLAGS,'returns_computed':True}));written.append(pub)
        guard(sources);require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in written},'Exact output namespace')
        for r in written:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final output drift')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),saved_references=written,retry_allowed=False),failure=True);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');a=parser.parse_args();print(json.dumps(run(execute=a.execute)))
