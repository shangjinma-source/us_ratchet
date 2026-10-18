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
PARENT=ROOT/'data/cache/research/multidecision_target_scoring_inputs_20261003_v1'
OUTPUT=ROOT/'data/cache/research/multidecision_target_inputs_independent_readback_20261003_v1'
INDEX_SHA='0bfe5f4ef9f52dedaeb6606208395bce4940159dd934e7121754ceb30528f8a7'
PUBLICATION_SHA='ef4be2ac7ae209479eb991f78fe4c4b19d46ed8b609dfe817d01358e62bd992c'
PRODUCER=ROOT/'scripts/ndx_multidecision_target_scoring_inputs_20261003.py'
PRODUCER_SHA='1f1c7617926f652c5f211d600e5333128e8136b6a3e17a1f288d78c2d0a48414'
INSPECTOR=ROOT/'backtest/ndx_multidecision_target_inputs_inspection_research.py'
INSPECTOR_SHA='413747edc7e617812c22275dac20c8d558d752d8f2d3851ac286bf9c96e440f0'
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


TARGET_CONTRACT=dict(decision_cutoffs=CUTOFFS,price_count=505,return_count=504,fit_return_count=126,evaluation_return_count=126,step_return_count=21,window_count=13,target_modes=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'],native_cny_role='SOURCE_CONTEXT_NOT_USD_RANKING_TARGET',missing_policy='KEEP_SLOTS_BLOCK_FULL13_NO_PARTIAL_POOL',mode_selection_using_results_allowed=False)


def reference(path,h):return dict(path=str(path),sha256=h)

def take(r,sources):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['sha256']) is str and len(r['sha256'])==64,'Exact file reference')
    b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Byte mismatch '+r['path'])
    require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source collision');sources[r['path']]=r['sha256'];return b


def inspect_saved_metadata(index,pub,started,docs,refs,expected_sources,index_ref,alignment_ref,target_ref,args):
    require(index['schema']=='MULTIDECISION_TARGET_SCORING_INPUTS_DOCUMENT_V1' and pub['schema']=='MULTIDECISION_TARGET_SCORING_INPUTS_PUBLICATION_V1','New schemas')
    for obj in (index,pub):
        require(obj['status']=='PUBLISHED_CONDITIONAL_INPUTS_PENDING_INDEPENDENT_READBACK','Conditional publication')
        for k,v in FLAGS.items():require(obj[k] is (True if k=='returns_computed' else False),'Outer permission '+k)
        require(obj['score_computed'] is False,'Not scoring');exact(obj['source_hashes'],expected_sources,'Independent producer closure');exact(obj['input_references'],refs,'Original source roles')
        exact(obj['alignment_reference'],alignment_ref,'Alignment file ref');exact(obj['target_inputs_reference'],target_ref,'Target file ref')
    exact(pub['index_reference'],index_ref,'External index anchor')
    require(index['new_independent_numeric_readback_completed'] is False,'Producer cannot self audit')
    exact(index['contract'],TARGET_CONTRACT,'Original scoring input contract');exact(index['reference_calendar'],docs['history']['requirements']['reference_calendar'],'Full calendar context');exact(index['union_session_dates'],args['session_dates'],'Union exact')
    require(type(index['nav_row_count']) is int and index['nav_row_count']==len(args['nav_rows']) and type(index['fx_row_count']) is int and index['fx_row_count']==len(args['fx_rows']),'All source rows')
    for key,expected in [('original_requirements_source_hashes_preserved',docs['requirements']['source_hashes']),('original_history_source_hashes_preserved',docs['history']['source_hashes']),('nav_manifest_preserved',docs['nav_manifest']),('nav_snapshot_preserved',docs['nav_snapshot']),('fx_manifest_preserved',docs['fx_manifest'])]:exact(index[key],expected,'Preserved '+key)
    require(started['schema']=='MULTIDECISION_TARGET_INPUTS_STARTED_V1' and started['retry_allowed'] is False,'Started scope')
    for k in FLAGS:require(started[k] is False,'Started permission')
    stamp=datetime.fromisoformat(started['started_at_utc']);require(stamp.tzinfo is not None and stamp.utcoffset().total_seconds()==0,'Started UTC')
    exact(started['source_hashes'],expected_sources,'Started source closure');exact(started['input_references'],refs,'Started inputs')


def parent_namespace():
    require({p.name for p in PARENT.iterdir()}=={'started.json','alignment.json','target_inputs.json','index.json','publication.json'},'Exact successful source namespace')


def load_inputs():
    require(all(type(h) is str and len(h)==64 for h in (INDEX_SHA,PUBLICATION_SHA,PRODUCER_SHA,INSPECTOR_SHA,TARGET_CORE_SHA)),'Pending readback anchor')
    docs,refs,sources=read_sources();args=project_inputs(docs,refs)
    take(reference(PRODUCER,PRODUCER_SHA),sources);take(reference(TARGET_CORE,TARGET_CORE_SHA),sources)
    expected={p:h for p,h in sources.items() if p!=str(SOURCE)}
    ir=reference(PARENT/'index.json',INDEX_SHA);pr=reference(PARENT/'publication.json',PUBLICATION_SHA)
    index=loads(take(ir,sources));pub=loads(take(pr,sources));parent_namespace()
    ar=index['alignment_reference'];tr=index['target_inputs_reference']
    require(ar['path']==str(PARENT/'alignment.json') and tr['path']==str(PARENT/'target_inputs.json'),'Fixed saved numeric paths')
    alignment=loads(take(ar,sources));target=loads(take(tr,sources))
    b=(PARENT/'started.json').read_bytes();sr=reference(PARENT/'started.json',sha(b));sources[sr['path']]=sr['sha256'];started=loads(b)
    inspect_saved_metadata(index,pub,started,docs,refs,expected,ir,ar,tr,args)
    coverage=[dict(mode=m['mode'],decisions=[dict(cutoff=d['cutoff'],status=d['status'],blocked_window_count=sum(w['status']=='BLOCKED_WINDOW' for w in d['windows'])) for d in m['decisions']]) for m in target['modes']]
    exact(index['mode_coverage'],coverage,'Saved per-mode78-window coverage')
    blob=take(reference(INSPECTOR,INSPECTOR_SHA),sources)
    oracle=types.ModuleType('_private_target_independent');oracle.__file__=str(INSPECTOR);exec(compile(blob,str(INSPECTOR),'exec'),oracle.__dict__)
    guard(sources);parent_namespace()
    args.pop('session_dates')
    args.update(alignment=alignment,target=target,alignment_reference=ar,reference_calendar=full_calendar(docs,refs))
    return args,sources,oracle,ir,pr,expected


def save(path,value,failure=False):
    b=encode(value)
    if not failure:require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3+len(b),'5GiB plus report bytes')
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Report write readback');return reference(path,sha(b))


def readback(*,execute=False):
    require(execute is True,'Explicit execute required')
    require(all(type(h) is str and len(h)==64 for h in (INDEX_SHA,PUBLICATION_SHA,PRODUCER_SHA)),'Pending actual anchors')
    require(not OUTPUT.exists(),'Independent namespace exists; no retry')
    args,sources,oracle,ir,pr,expected=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        sr=save(OUTPUT/'started.json',dict(schema='MULTIDECISION_TARGET_READBACK_STARTED_V1',index_reference=ir,publication_reference=pr,reader_sha256=LOADED_SHA,retry_allowed=False))
        result=oracle.inspect_target_inputs(**args);require(result['status']=='PASS','Independent arithmetic result');guard(sources);parent_namespace()
        out=save(OUTPUT/'independent_readback.json',dict(schema='MULTIDECISION_TARGET_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',index_reference=ir,publication_reference=pr,reader_sha256=LOADED_SHA,inspector_reference=reference(INSPECTOR,INSPECTOR_SHA),producer_reference=reference(PRODUCER,PRODUCER_SHA),producer_source_hashes_verified=expected,source_hashes=sources,inspection=result,html_reparsed=False,old_audit_called=False,alignment_producer_called=False,target_producer_called=False,score_computed=False,fit_performed=False,account_executed=False,point_in_time_verified=False,benchmark_qualified=False,mode_selected_using_results=False,started_bytes_externally_anchored=False,started_time_attested=False))
        guard(sources);parent_namespace();require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact independent namespace')
        for r in (sr,out):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final report drift')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),retry_allowed=False),failure=True);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');a=parser.parse_args();print(json.dumps(readback(execute=a.execute)))
