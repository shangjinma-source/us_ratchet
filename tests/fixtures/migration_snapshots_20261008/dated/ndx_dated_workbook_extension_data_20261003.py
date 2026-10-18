"""Stream display data only; no workbook/chart delivery or economic replay."""
import shutil
import argparse
from collections import Counter
from copy import deepcopy
import hashlib,json,os
from pathlib import Path
import types
STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=STORAGE/'dated_workbook_extension_data_20261003_v1'
CORE=ROOT/'backtest/ndx_dated_workbook_extension_tables_research.py';CORE_SHA='b5cdee3e425a68bbaf14c509e194ad75517fd966d547241d50c38e90d3892e0d'
BOUND={
 'path_index':(str(STORAGE/'dated_path_risk_display_20261003_v1/index.json'),None),
 'path_publication':(str(STORAGE/'dated_path_risk_display_20261003_v1/publication.json'),None),
 'path_audit':(str(STORAGE/'dated_path_risk_display_independent_readback_20261003_v1/independent_readback.json'),None),
 'path_producer':('scripts/ndx_dated_path_risk_display_20261003.py','3be3038e860890b8b33ca24d8a1dd77e0654335b9fb47f6a7aa6f02a9428abab'),
 'path_core':('backtest/ndx_dated_path_risk_display_research.py','afb909618ba50ce22d9491587957e350b7f37675dd14be046f97a502f18a26b3'),
 'path_reader':('scripts/ndx_dated_path_risk_display_independent_readback_20261003.py',None),
 'chain_index':(str(STORAGE/'dated_risk_chain_display_20261003_v1/index.json'),None),
 'chain_publication':(str(STORAGE/'dated_risk_chain_display_20261003_v1/publication.json'),None),
 'chain_audit':(str(STORAGE/'dated_risk_chain_display_independent_readback_20261003_v1/independent_readback.json'),None),
 'chain_producer':('scripts/ndx_dated_risk_chain_display_20261003.py','92a1e84d0c1077d8dd949851f427c47d366bce42aac19ca0d5396ae8fe4f790d'),
 'chain_core':('backtest/ndx_saved_risk_chain_display_research.py','428a1b1f2d391dcc24694b02df9213ae08dc9e61459a47c229bf9d1ba90df9bc'),
 'chain_reader':('scripts/ndx_dated_risk_chain_display_independent_readback_20261003.py',None),
 'classification':('data/cache/research/saved_classification_coverage_20261003_v1/coverage.json','a9c26a95e01846cb20993d435ee2a7f690d111729f825d7551bde1ed404f555f'),
 'classification_publication':('data/cache/research/saved_classification_coverage_20261003_v1/publication.json','ac87e53e42ed5c018ad64f26fc44a743deef0c25b37dd1f80c2a1e98dd897607'),
 'classification_audit':('data/cache/research/saved_classification_coverage_independent_readback_20261003_v1/independent_readback.json','bb51a2efb108a157555bf368a6f09857ceaf5a7d338a3f08d892294ba568fbd9'),
 'classification_producer':('scripts/ndx_saved_classification_coverage_20261003.py','1a2ae65457e4f03f4e6e94bac66ecbb7b0ea04d033d6b07f5de0fe3486c5459d'),
 'classification_core':('backtest/ndx_saved_risk_classification_coverage_research.py','116b6eaff2621216490ab77cdc96d0b7af6b5d38a70345e42197f7c61f79486e'),
 'classification_reader':('scripts/ndx_saved_classification_coverage_independent_readback_20261003.py','e5a45ba77a58879865e1149ab00f33f3036e17d5b9fadef33f1534411aa6fe51')}
FLAGS=dict.fromkeys(('source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified'),False)
SHARED_ROLES=('incumbent_integer','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
MAX_LINE=64*1024*1024

def require(ok,message):
    if not ok:raise ValueError(message)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b):require(enc(a)==enc(b),'Exact saved cross-reference')
def integer(x):require(type(x) is int and x>=0,'Exact nonnegative integer');return x
def pairs(items):
    d={}
    for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
    return d
def loads(b):return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def reference(r):
    require(type(r) is dict and {'path','sha256'}<=set(r),'Reference fields')
    require(type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Fixed path/SHA')
def merge(s,p,h):require(p not in s or s[p]==h,'Conflicting source SHA');s[p]=h
def read(r,sources):
    reference(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed bytes');merge(sources,r['path'],r['sha256']);return b
def guard(sources):
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift')
MIN_FREE_BYTES=5*1024**3

def resource_gate(reserve_bytes=0):
    require(type(reserve_bytes) is int and reserve_bytes>=0,'Exact output byte reserve')
    # OUTPUT may not exist yet; its volume root does. Never check the source ROOT.
    require(shutil.disk_usage(Path(OUTPUT.anchor)).free>=MIN_FREE_BYTES+reserve_bytes,'RESOURCE_STOP_BEFORE_WRITE: preserve five GiB on output volume')

def save(path,value):
    b=enc(value)
    if path.name!='failure.json':resource_gate(len(b))
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved bytes changed');return dict(path=str(path),sha256=sha(b))

def validate_parents(d,refs):
    expected={
      'path':('SOURCE_BOUND_DATED_PATH_RISK_DISPLAY_V1','DATED_PATH_RISK_DISPLAY_PUBLICATION_V1','PUBLISHED_SAVED_PATH_DISPLAY_ONLY','DATED_PATH_RISK_DISPLAY_INDEPENDENT_READBACK_V1'),
      'chain':('SOURCE_BOUND_DATED_CHAIN_DISPLAY_V1','DATED_CHAIN_DISPLAY_PUBLICATION_V1','PUBLISHED_DISPLAY_ADDITION_NOT_RISK_REEVALUATION','DATED_RISK_CHAIN_DISPLAY_INDEPENDENT_READBACK_V1'),
      'classification':('SOURCE_BOUND_SAVED_CLASSIFICATION_COVERAGE_V1','SAVED_CLASSIFICATION_COVERAGE_PUBLICATION_V1','PUBLISHED_CONDITIONAL_SAVED_LABEL_COVERAGE','SAVED_CLASSIFICATION_COVERAGE_INDEPENDENT_READBACK_V1')}
    for role,(schema,ps,st,aus) in expected.items():
        index_role=role if role=='classification' else role+'_index';index=d[index_role];pub=d[role+'_publication'];audit=d[role+'_audit'];rk='coverage_reference' if role=='classification' else 'index_reference'
        require(index['schema']==schema and pub['schema']==ps and pub['status']==st and audit['schema']==aus and audit['status']=='PASS','Audited source schema/status')
        exact(pub[rk],refs[index_role]);exact(audit[rk],refs[index_role]);exact(audit['publication_reference'],refs[role+'_publication']);exact(pub['source_hashes'],index['source_hashes'])
        require(audit['reader_sha256']==refs[role+'_reader']['sha256'],'Fixed reader source')
        for key in ('producer','core'):
            r=refs[role+'_'+key];require(index['source_hashes'].get(r['path'])==r['sha256'],'Producer code closure')
        for key in (index_role,role+'_publication',role+'_reader',role+'_producer',role+'_core'):
            r=refs[key];require(audit['source_hashes'].get(r['path'])==r['sha256'],'Audit direct closure')
        for obj in (index,pub,audit):
            for key in ('point_in_time_verified','promotion_allowed'):require(obj[key] is False,'Conditional source authority')
        require(audit['producer_called'] is False,'No audit producer replay')
    p,c=d['path_index'],d['chain_index'];exact(c['original_projection_index_reference'],refs['path_index']);exact(c['original_projection_source_hashes_preserved'],p['source_hashes'])
    for role in ('index','publication','audit','reader','producer'):
        exact(c['input_references'][role],refs['path_'+role])
    exact(c['input_references']['projection_core'],refs['path_core'])
    require(integer(p['planned_task_count'])==integer(c['planned_task_count'])==1632,'Full1632 denominator')
    for key in ('projected_task_count','not_supplied_task_count'):exact(c[key],p[key])
    for role,key in (('path','shared_paths_reference'),('chain','shared_control_aggregates_reference')):
        index=d[role+'_index'];pub=d[role+'_publication'];exact(pub[key],index[key]);exact(pub['task_jsonl_reference'],index['task_jsonl_reference'])
    exact(d['path_audit']['verified_jsonl_sha256'],p['task_jsonl_reference']['sha256']);exact(d['path_audit']['verified_jsonl_bytes'],p['task_jsonl_reference']['byte_count'])
    detail=d['chain_audit']['detail'];exact(detail['original_jsonl_sha256'],p['task_jsonl_reference']['sha256']);exact(detail['output_jsonl_sha256'],c['task_jsonl_reference']['sha256'])
    exact(detail['planned_tasks'],1632);exact(detail['projected_tasks'],c['projected_task_count'])

def load():
    require(all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Pending parents: no output permitted')
    refs={k:dict(path=str(ROOT/p),sha256=h) for k,(p,h) in BOUND.items()};sources={str(SOURCE):LOADED,str(CORE):CORE_SHA};docs={}
    for k,r in refs.items():
        b=read(r,sources)
        if not k.endswith(('_producer','_core','_reader')):docs[k]=loads(b)
    for role,names in (('path_index',{'started.json','tasks.jsonl','shared_paths.json','index.json','publication.json'}),('chain_index',{'started.json','tasks.jsonl','shared_control_aggregates.json','index.json','publication.json'}),('classification',{'started.json','coverage.json','publication.json'})):
        require({p.name for p in Path(refs[role]['path']).parent.iterdir()}==names,'Exact successful parent namespace')
    for role in ('path_audit','chain_audit','classification_audit'):
        require(not (Path(refs[role]['path']).parent/'failure.json').exists(),'Failed parent audit namespace')
    validate_parents(docs,refs)
    for role,name,key in (('path','shared_paths.json','shared_paths_reference'),('chain','shared_control_aggregates.json','shared_control_aggregates_reference')):
        parent=Path(refs[role+'_index']['path']).parent;r=docs[role+'_index'][key]
        require(Path(r['path'])==parent/name,'Fixed shared file');docs[role+'_shared']=loads(read(r,sources))
        jr=docs[role+'_index']['task_jsonl_reference'];reference(jr);require(Path(jr['path'])==parent/'tasks.jsonl','Fixed JSONL path')
    require(docs['path_shared']['schema']=='DATED_PATH_RISK_SHARED_PATHS_V1' and docs['chain_shared']['schema']=='DATED_CHAIN_SHARED_CONTROL_AGGREGATES_V1','Shared envelope schemas')
    guard(sources);b=CORE.read_bytes();require(sha(b)==CORE_SHA,'Fresh private display core')
    core=types.ModuleType('_private_extension_tables');core.__file__=str(CORE);exec(compile(b,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,core

class IndexedStream:
    def __init__(self,stream,descriptor):self.stream=stream;self.descriptor=descriptor;self.offset=0;self.count=0;self.digest=hashlib.sha256()
    def read(self,location):
        b=self.stream.readline(MAX_LINE+1);require(b.endswith(b'\n') and len(b)<=MAX_LINE,'Bounded complete JSONL row')
        exact(location,dict(record_index=self.count,byte_start=self.offset,byte_stop=self.offset+len(b),row_sha256=sha(b)))
        row=loads(b);require(enc(row)+b'\n'==b,'Canonical saved JSONL');self.digest.update(b);self.count+=1;self.offset+=len(b);return row
    def finish(self):
        require(self.stream.read(1)==b'','No extra source rows');exact(self.offset,self.descriptor['byte_count']);exact(self.count,self.descriptor['record_count']);exact(self.digest.hexdigest(),self.descriptor['sha256'])

def display_rows_count(row):
    count=sum(len(v['slots']) for v in row['series'].values() if 'slots' in v)
    for track in row['risk_tracks'].values():
        if 'rows' in track and track['rows'] is not None:count+=sum(len(day['aggregation']['rows'])+1 for day in track['rows'])
    count+=sum(len(v['aggregation']['rows']) for v in row['original_target_chain_evidence'].values())
    return count

def stream_display(path_stream,chain_stream,pindex,cindex,shared,aggregates,core,emit):
    for index in (pindex,cindex):
        require(integer(index['planned_task_count'])==1632,'Full exact planned count')
        present_count=integer(index['projected_task_count']);missing_count=integer(index['not_supplied_task_count'])
        require(present_count+missing_count==1632,'Complete present/missing partition')
    exact(pindex['calendar'],cindex['calendar'])
    entries=pindex['task_index'];centries=cindex['task_index'];require(len(entries)==len(centries)==1632,'Full indexed queue')
    ids=[r['numerical_task_id'] for r in entries];require(len(set(ids))==1632,'Unique full task IDs')
    strata=Counter((r['k'],enc(r['weight_spec'])) for r in entries);require(len(strata)==51 and set(strata.values())=={32} and {k for k,_ in strata}==set(range(4,21)),'Original51 strata')
    specs={k:{spec for kk,spec in strata if kk==k} for k in range(4,21)};require(all(len(v)==3 and v==specs[4] for v in specs.values()),'Same three specs across all cardinalities')
    ps=IndexedStream(path_stream,pindex['task_jsonl_reference']);cs=IndexedStream(chain_stream,cindex['task_jsonl_reference']);output=[];descriptors=[];common_series={};common_risk={};present=0
    for ordinal,(entry,ce) in enumerate(zip(entries,centries)):
        for key in ('numerical_task_id','task_ordinal','k','weight_spec'):exact(entry[key],ce[key])
        require(integer(entry['task_ordinal'])==ordinal,'Complete original index order');tid=entry['numerical_task_id']
        if entry['status']=='COMPARISON_NOT_SUPPLIED':
            require(ce['status']=='COMPARISON_NOT_SUPPLIED' and entry['jsonl_record'] is None and ce['jsonl_record'] is None,'Missing remains explicit')
            row=dict(schema='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1',numerical_task_id=tid,task_ordinal=ordinal,status='COMPARISON_NOT_SUPPLIED',original_path_index_row=deepcopy(entry),original_chain_index_row=deepcopy(ce),**FLAGS);nrows=1
        else:
            require(entry['status']=='AUDITED_SAVED_PATHS_PROJECTED' and ce['status']=='SAVED_CHAIN_DISPLAY_ADDED','Audited paired rows')
            p=ps.read(entry['jsonl_record']);c=cs.read(ce['jsonl_record'])
            require(p['numerical_task_id']==c['numerical_task_id']==tid,'Indexed task identity')
            for key in ('numerical_task_id','k','weight_spec'):exact(p['original_task_summary_row'][key],entry[key]);exact(c['original_task_summary_row'][key],entry[key])
            exact(p['calendar'],pindex['calendar']);row=core.project_task_display(p,c,shared,aggregates)
            for role in SHARED_ROLES:
                key=(p['tracks'] if role.startswith('incumbent') else p['nav_modes'])[role]['shared_path_id'];value=dict(identity=deepcopy(shared[key]['identity']),series=row['series'][role])
                if key in common_series:exact(common_series[key],value)
                else:common_series[key]=deepcopy(value)
                row['series'][role]=dict(shared_series_id=key)
                if role.startswith('incumbent'):
                    value=dict(identity=deepcopy(shared[key]['identity']),risk=row['risk_tracks'][role])
                    if key in common_risk:exact(common_risk[key],value)
                    else:common_risk[key]=deepcopy(value)
                    row['risk_tracks'][role]=dict(shared_risk_id=key)
            nrows=display_rows_count(row);present+=1
        row['source_jsonl_records']=dict(path=deepcopy(entry['jsonl_record']),chain=deepcopy(ce['jsonl_record']));row['task_ordinal']=ordinal
        b=enc(row)+b'\n';location=emit(b)
        output.append(dict(numerical_task_id=tid,task_ordinal=ordinal,k=entry['k'],weight_spec=deepcopy(entry['weight_spec']),status=row.get('status','DISPLAY_PROJECTED'),jsonl_record=location))
        descriptors.append(dict(numerical_task_id=tid,task_ordinal=ordinal,data_row_count=nrows,estimated_bytes=len(b),jsonl_record=deepcopy(location),status=row.get('status','DISPLAY_PROJECTED')))
    ps.finish();cs.finish();require(present==integer(pindex['projected_task_count'])==integer(cindex['projected_task_count']),'Saved present count');require(1632-present==integer(pindex['not_supplied_task_count'])==integer(cindex['not_supplied_task_count']),'Saved missing count')
    require(len(common_series)==(4 if present else 0) and len(common_risk)==(2 if present else 0),'Shared4series/2risk once')
    packages=core.plan_display_packages(descriptors,expected_task_ids=ids)
    return dict(task_index=output,planned_task_count=1632,projected_task_count=present,not_supplied_task_count=1632-present,shared_series=common_series,shared_risk=common_risk,package_plan=packages,full_new_cutoff_task_denominator=pindex['full_new_cutoff_task_denominator'],shared_series_slot_count=sum(len(v['series']['slots']) for v in common_series.values()),shared_risk_group_and_context_row_count=sum(sum(len(d['aggregation']['rows'])+1 for d in v['risk']['rows']) for v in common_risk.values()),original_stream_references=dict(path=deepcopy(pindex['task_jsonl_reference']),chain=deepcopy(cindex['task_jsonl_reference'])),byte_estimate_basis='ACTUAL_COMPACT_DISPLAY_JSONL_BYTES_NOT_XLSX_ZIP_OR_RENDER_MEMORY',data_row_count_basis='CANDIDATE_PATH_SLOTS_PLUS_ALL_CHAIN_GROUP_ROWS_AND_CASH_CONTEXT_PLUS_ORIGINAL_TARGET_GROUPS;SHARED_ROWS_ONCE_SEPARATE')

def run(*,execute=False):
    require(type(execute) is bool,'Explicit execute')
    if not execute:return dict(status='NOT_EXECUTED',**FLAGS)
    require(not OUTPUT.exists(),'Create-only; no retry');docs,refs,sources,core=load();resource_gate();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started=save(OUTPUT/'started.json',dict(schema='DATED_WORKBOOK_EXTENSION_DATA_STARTED_V1',input_references=refs,source_hashes=sources,**FLAGS))
        classification=core.project_classification(docs['classification']['coverage']);classification_ref=save(OUTPUT/'classification.json',classification)
        offset=count=0;digest=hashlib.sha256()
        with Path(docs['path_index']['task_jsonl_reference']['path']).open('rb') as ps,Path(docs['chain_index']['task_jsonl_reference']['path']).open('rb') as cs,(OUTPUT/'tasks.jsonl').open('xb') as target:
            def emit(b):
                nonlocal offset,count
                resource_gate(len(b));loc=dict(record_index=count,byte_start=offset,byte_stop=offset+len(b),row_sha256=sha(b));target.write(b);digest.update(b);offset+=len(b);count+=1;return loc
            result=stream_display(ps,cs,docs['path_index'],docs['chain_index'],docs['path_shared']['shared_paths'],docs['chain_shared']['aggregates'],core,emit);target.flush();os.fsync(target.fileno())
        guard(sources)
        shared=save(OUTPUT/'shared_display.json',dict(schema='DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1',series=result.pop('shared_series'),risk=result.pop('shared_risk'),**FLAGS))
        jr=dict(path=str(OUTPUT/'tasks.jsonl'),sha256=digest.hexdigest(),record_count=count,byte_count=offset)
        claims=dict(sources)
        for role in ('path','chain'):
            r=docs[role+'_index']['task_jsonl_reference'];merge(claims,r['path'],r['sha256'])
        index=save(OUTPUT/'index.json',dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1',**result,task_jsonl_reference=jr,shared_display_reference=shared,classification_reference=classification_ref,input_references=refs,source_hashes=claims,parent_source_hashes_preserved={k:docs[k]['source_hashes'] for k in ('path_index','chain_index','classification')},source_verification_scope='TWO_INPUT_STREAMS_HASHED_ONCE_DURING_CONSUMPTION;FIXED_METADATA_RECHECKED;NO_TRANSITIVE_REPLAY',delivery_status='DISPLAY_DATA_ONLY_NOT_H_WORKBOOK_DELIVERY',**FLAGS))
        pub=save(OUTPUT/'publication.json',dict(schema='DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1',status='PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY',index_reference=index,task_jsonl_reference=jr,shared_display_reference=shared,classification_reference=classification_ref,source_hashes=claims,**FLAGS));guard(sources)
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','tasks.jsonl','shared_display.json','classification.json','index.json','publication.json'},'Exact successful files')
        check=hashlib.sha256()
        with (OUTPUT/'tasks.jsonl').open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):check.update(b)
        require(check.hexdigest()==jr['sha256'],'Final output stream hash')
        for r in (started,shared,classification_ref,index,pub):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final metadata bytes')
        return index
    except Exception as error:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False));raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
