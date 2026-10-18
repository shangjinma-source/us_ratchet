"""Independent saved display projection verification; no producer/core calls or XLSX claims."""
import argparse,hashlib,json,math,os,re
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
STORAGE=Path('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714')
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=STORAGE/'dated_workbook_extension_data_20261003_v1'
OUTPUT=STORAGE/'dated_workbook_extension_data_independent_readback_20261003_v1'
INDEX_SHA=None
PUBLICATION_SHA=None
PRODUCER=ROOT/'scripts/ndx_dated_workbook_extension_data_20261003.py'
PRODUCER_SHA=None
CORE=ROOT/'backtest/ndx_dated_workbook_extension_tables_research.py'
CORE_SHA='b5cdee3e425a68bbaf14c509e194ad75517fd966d547241d50c38e90d3892e0d'
BOUND={'path_index': (str(STORAGE/'dated_path_risk_display_20261003_v1/index.json'), None), 'path_publication': (str(STORAGE/'dated_path_risk_display_20261003_v1/publication.json'), None), 'path_audit': (str(STORAGE/'dated_path_risk_display_independent_readback_20261003_v1/independent_readback.json'), None), 'path_producer': ('scripts/ndx_dated_path_risk_display_20261003.py', '3be3038e860890b8b33ca24d8a1dd77e0654335b9fb47f6a7aa6f02a9428abab'), 'path_core': ('backtest/ndx_dated_path_risk_display_research.py', 'afb909618ba50ce22d9491587957e350b7f37675dd14be046f97a502f18a26b3'), 'path_reader': ('scripts/ndx_dated_path_risk_display_independent_readback_20261003.py', None), 'chain_index': (str(STORAGE/'dated_risk_chain_display_20261003_v1/index.json'), None), 'chain_publication': (str(STORAGE/'dated_risk_chain_display_20261003_v1/publication.json'), None), 'chain_audit': (str(STORAGE/'dated_risk_chain_display_independent_readback_20261003_v1/independent_readback.json'), None), 'chain_producer': ('scripts/ndx_dated_risk_chain_display_20261003.py', '92a1e84d0c1077d8dd949851f427c47d366bce42aac19ca0d5396ae8fe4f790d'), 'chain_core': ('backtest/ndx_saved_risk_chain_display_research.py', '428a1b1f2d391dcc24694b02df9213ae08dc9e61459a47c229bf9d1ba90df9bc'), 'chain_reader': ('scripts/ndx_dated_risk_chain_display_independent_readback_20261003.py', None), 'classification': ('data/cache/research/saved_classification_coverage_20261003_v1/coverage.json', 'a9c26a95e01846cb20993d435ee2a7f690d111729f825d7551bde1ed404f555f'), 'classification_publication': ('data/cache/research/saved_classification_coverage_20261003_v1/publication.json', 'ac87e53e42ed5c018ad64f26fc44a743deef0c25b37dd1f80c2a1e98dd897607'), 'classification_audit': ('data/cache/research/saved_classification_coverage_independent_readback_20261003_v1/independent_readback.json', 'bb51a2efb108a157555bf368a6f09857ceaf5a7d338a3f08d892294ba568fbd9'), 'classification_producer': ('scripts/ndx_saved_classification_coverage_20261003.py', '1a2ae65457e4f03f4e6e94bac66ecbb7b0ea04d033d6b07f5de0fe3486c5459d'), 'classification_core': ('backtest/ndx_saved_risk_classification_coverage_research.py', '116b6eaff2621216490ab77cdc96d0b7af6b5d38a70345e42197f7c61f79486e'), 'classification_reader': ('scripts/ndx_saved_classification_coverage_independent_readback_20261003.py', 'e5a45ba77a58879865e1149ab00f33f3036e17d5b9fadef33f1534411aa6fe51')}
OUT_FLAGS=dict.fromkeys(('source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified'),False)
PURE_FLAGS=dict.fromkeys(('source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','risk_chains_reaggregated','account_executed','winner_selected'),False)
ROLES=('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous')
SHARED=('incumbent_integer','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
MODES=SHARED[2:]

def require(v,m):
    if not v:raise ValueError(m)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,m='Exact source projection'):require(enc(a)==enc(b),m)
def integer(v):require(type(v) is int and v>=0,'Exact nonnegative integer');return v
def pairs(items):
    d={}
    for k,v in items:require(k not in d,'Duplicate key');d[k]=v
    return d
def loads(b):return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def reference(p,h):return dict(path=str(p),sha256=h)
def checkref(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'].strip() and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Fixed source ref required')
def merge(s,r):
    checkref(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def read(r,s):
    merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Source bytes');return b
def simple(r):return reference(r['path'],r['sha256'])
def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED,'Loaded reader drift')
    for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift')
def flags(d,keys):
    for k in keys:require(d[k] is False,'False permission '+k)
def save(p,v):
    b=enc(v)
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved audit bytes');return reference(p,sha(b))

class Stream:
    def __init__(self,f,ref):self.f=f;self.ref=ref;self.count=0;self.offset=0;self.hash=hashlib.sha256()
    def take(self,loc):
        b=self.f.readline(64*1024**2+1);require(b.endswith(b'\n') and len(b)<=64*1024**2,'Complete bounded JSONL')
        exact(loc,dict(record_index=self.count,byte_start=self.offset,byte_stop=self.offset+len(b),row_sha256=sha(b)),'Byte locator')
        v=loads(b);require(enc(v)+b'\n'==b,'Canonical saved row');self.hash.update(b);self.offset+=len(b);self.count+=1
        return v,len(b)
    def finish(self):
        require(self.f.read(1)==b'','Extra trailing rows');exact(self.count,self.ref['record_count']);exact(self.offset,self.ref['byte_count']);exact(self.hash.hexdigest(),self.ref['sha256'])

def number(v):
    if v is None:return dict(exact_value=None,display_value=None,display_status='MISSING_SAVED_VALUE')
    require(type(v) in (dict,str,int,float),'Number without bool')
    if type(v) is dict:
        require(set(v)=={'numerator','denominator'} and all(type(x) is str for x in v.values()),'Saved exact ratio');q=Fraction(int(v['numerator']),int(v['denominator']))
    else:
        require(type(v) is not float or math.isfinite(v),'Finite saved number');q=Fraction(str(v))
    try:n=float(q)
    except OverflowError:n=math.inf
    outside=not math.isfinite(n) or (n==0 and q!=0)
    return dict(exact_value=deepcopy(v),display_value=None if outside else n,display_status='OUTSIDE_DISPLAY_PRECISION' if outside else 'FINITE_BINARY_FLOAT_DISPLAY')

def series_from(payload,role,calendar):
    if role in MODES:
        require(payload['mode']==role,'Exact FX role');exact([x['session'] for x in payload['observations']],calendar)
        values=[x['normalized_value_exact'] for x in payload['observations']];status='SAVED_NAV_REFERENCE';source=payload['source_reference']
        if payload['metrics'] is not None:exact(values,payload['metrics']['normalized_values_exact'])
    elif payload['status']=='AVAILABLE':
        exact([x['session'] for x in payload['path']],calendar);values=payload['saved_normalized_values_exact'];exact(values,payload['metrics']['normalized_values_exact']);status='AVAILABLE';source=payload['source_reference']
    else:
        require(role=='candidate_integer' and payload['status'] in ('NOT_EXECUTED_NONPOSITIVE_TARGET','TECHNICAL_MISSING') and payload['path'] is None,'Missing integer stays missing');exact(payload['calendar_slots'],[dict(session=d,value=None) for d in calendar]);values=[None]*len(calendar);status=payload['status'];source=None
    require(type(values) is list and len(values)==127,'Full slots')
    return dict(status=status,source_reference=deepcopy(source),slots=[dict(session=d,**number(v)) for d,v in zip(calendar,values)],missing_evidence=deepcopy(payload.get('missing_evidence')),transformation='COPY_SAVED_NORMALIZED_VALUES_NO_RETURN_RECALCULATION')

def expected_row(p,c,paths,chains,common_series,common_risk):
    require(p['schema']=='DATED_SAVED_PATH_RISK_DISPLAY_PROJECTION_V1' and c['schema']=='SAVED_RISK_CHAIN_DISPLAY_AGGREGATES_V1','Input row schemas');exact(p['numerical_task_id'],c['numerical_task_id']);exact(p['calendar'],c['calendar'])
    cal=p['calendar'];require(len(cal)==127 and cal==sorted(set(cal)) and cal[:2]==['2026-03-20','2026-03-23'] and cal[-1]=='2026-09-21','Original calendar')
    for d in (p,c):flags(d,('point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed'));require(d['evaluation_interval_previously_used_for_fitting'] is True,'Historical consumed interval')
    for a,b in [('preserved_evidence_sidecars','preserved_evidence_sidecars'),('input_limitations','limitations_preserved'),('original_provenance_and_missing','original_provenance_and_missing'),('original_task_summary_row','original_task_summary_row'),('candidate_normalization_evidence','candidate_engine_normalization_evidence'),('input_references','input_references')]:exact(p[a],c[b])
    exact(p['input_references'],c['projection_input_references']);source_index={};series={};risk={}
    for role in (*ROLES,*MODES):
        source=(p['tracks'] if role in ROLES else p['nav_modes'])[role];key=None
        if role in SHARED:
            require(set(source)=={'shared_path_id','value_encoding_preserved'},'Shared reference fields');key=source['shared_path_id'];item=paths[key];ident=item['identity'];require(sha(enc(ident))==key and ident['role']==role,'Shared identity');source=item['payload'];exact(ident['source_reference'],source['source_reference'])
        result=series_from(source,role,cal)
        if result['source_reference'] is not None:source_index[role]=deepcopy(result['source_reference'])
        if key is None:series[role]=result
        else:
            value=dict(identity=deepcopy(paths[key]['identity']),series=result)
            if key in common_series:exact(common_series[key],value,'Shared series cannot vary by candidate')
            common_series[key]=value;series[role]=dict(shared_series_id=key)
        if role in ROLES:
            ag=c['tracks'][role]
            if key is not None:
                exact(ag,dict(shared_aggregate_id=key));exact(chains[key]['identity'],paths[key]['identity']);ag=chains[key]['aggregation']
            exact(ag['status'],source['status'])
            if ag['status']=='AVAILABLE':exact([x['session'] for x in ag['rows']],cal);exact(ag['source_reference'],source_index[role])
            else:require(ag['rows'] is None,'No invented missing risk cash')
            if key is None:risk[role]=deepcopy(ag)
            else:
                value=dict(identity=deepcopy(paths[key]['identity']),risk=deepcopy(ag))
                if key in common_risk:exact(common_risk[key],value,'Shared risk cannot vary')
                common_risk[key]=value;risk[role]=dict(shared_risk_id=key)
    for role in ('candidate','incumbent'):exact(c['targets'][role]['source_evidence'],p['target_evidence'][role])
    return dict(schema='DATED_WORKBOOK_TASK_EXTENSION_TABLES_V1',numerical_task_id=p['numerical_task_id'],calendar=deepcopy(cal),original_task_summary_row=deepcopy(p['original_task_summary_row']),series=series,risk_tracks=risk,original_target_chain_evidence=deepcopy(c['targets']),engine_normalization_evidence=deepcopy(p['candidate_normalization_evidence']),original_target_evidence=deepcopy(p['target_evidence']),source_index=source_index,input_references=deepcopy(p['input_references']),original_provenance_and_missing=deepcopy(p['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(p['preserved_evidence_sidecars']),evaluation_interval_previously_used_for_fitting=True,risk_copy_semantics='ALL_SAVED_GROUPS_RAW_TARGET_ENGINE_AND_ACTUAL_KEPT_SEPARATE_NO_AGGREGATION',**PURE_FLAGS)

def row_count(row):
    return sum(len(s['slots']) for s in row['series'].values() if 'slots' in s)+sum(sum(len(d['aggregation']['rows'])+1 for d in t['rows']) for t in row['risk_tracks'].values() if t.get('rows') is not None)+sum(len(t['aggregation']['rows']) for t in row['original_target_chain_evidence'].values())

def packages(descriptors):
    rows_limit=250000;bytes_limit=50*1024*1024;groups=[]
    for item in descriptors:
        n=integer(item['data_row_count']);b=integer(item['estimated_bytes']);require(n<=rows_limit and b<=bytes_limit,'Single task engineering limit')
        if not groups or groups[-1]['data_row_count']+n>rows_limit or groups[-1]['estimated_bytes']+b>bytes_limit:groups.append(dict(package_index=len(groups),start_task_ordinal=item['task_ordinal'],stop_task_ordinal=item['task_ordinal'],data_row_count=0,estimated_bytes=0,tasks=[]))
        g=groups[-1];g['tasks'].append(item);g['stop_task_ordinal']=item['task_ordinal']+1;g['data_row_count']+=n;g['estimated_bytes']+=b
    for g in groups:
        q,r=divmod(g['data_row_count'],100000);g['data_page_row_counts']=[100000]*q+([r] if r else [])
    return dict(schema='DATED_WORKBOOK_EXTENSION_PACKAGE_PLAN_V1',packages=groups,task_count=len(descriptors),limits=dict(max_rows_per_sheet=100000,max_rows_per_package=250000,max_estimated_bytes_per_package=50*1024*1024),counts_are_engineering_not_pool_limits=True,exported_byte_limit_verified=False,unprocessed_task_count=0,**PURE_FLAGS)

def inspect_streams(pstream,cstream,ostream,pindex,cindex,index,paths,chains,shared):
    entries=pindex['task_index'];centries=cindex['task_index'];outentries=index['task_index']
    require(len(entries)==len(centries)==len(outentries)==1632 and len({r['numerical_task_id'] for r in entries})==1632,'Complete unique1632')
    strata=Counter()
    for e in entries:
        require(4<=integer(e['k'])<=20 and re.fullmatch('[a-f0-9]{64}',e['numerical_task_id']),'Exact k and taskID');strata[e['k'],enc(e['weight_spec'])]+=1
    require(len(strata)==51 and set(strata.values())=={32} and {k for k,_ in strata}==set(range(4,21)),'51 full strata');specs={s for k,s in strata if k==4};require(all({s for kk,s in strata if kk==k}==specs for k in range(4,21)),'Same3 spec definitions')
    exact(pindex['calendar'],cindex['calendar']);ps=Stream(pstream,pindex['task_jsonl_reference']);cs=Stream(cstream,cindex['task_jsonl_reference']);os_=Stream(ostream,index['task_jsonl_reference']);common_series={};common_risk={};desc=[];present=0
    for i,(pe,ce,oe) in enumerate(zip(entries,centries,outentries)):
        for k in ('numerical_task_id','task_ordinal','k','weight_spec'):exact(pe[k],ce[k]);exact(pe[k],oe[k])
        exact(integer(pe['task_ordinal']),i);tid=pe['numerical_task_id']
        if pe['status']=='COMPARISON_NOT_SUPPLIED':
            require(ce['status']==pe['status'] and pe['jsonl_record'] is None and ce['jsonl_record'] is None,'Missing remains explicit')
            expected=dict(schema='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1',numerical_task_id=tid,task_ordinal=i,status='COMPARISON_NOT_SUPPLIED',original_path_index_row=pe,original_chain_index_row=ce,**OUT_FLAGS);n=1;status='COMPARISON_NOT_SUPPLIED'
        else:
            require(pe['status']=='AUDITED_SAVED_PATHS_PROJECTED' and ce['status']=='SAVED_CHAIN_DISPLAY_ADDED','Source projected statuses');p,_=ps.take(pe['jsonl_record']);c,_=cs.take(ce['jsonl_record']);exact(p['numerical_task_id'],tid)
            for key in ('numerical_task_id','k','weight_spec'):exact(p['original_task_summary_row'][key],pe[key]);exact(c['original_task_summary_row'][key],pe[key])
            exact(p['calendar'],pindex['calendar']);expected=expected_row(p,c,paths,chains,common_series,common_risk);n=row_count(expected);present+=1;status='DISPLAY_PROJECTED'
        expected.update(task_ordinal=i,source_jsonl_records=dict(path=pe['jsonl_record'],chain=ce['jsonl_record']));got,size=os_.take(oe['jsonl_record']);exact(got,expected,'All saved display fields');exact(oe,dict(numerical_task_id=tid,task_ordinal=i,k=pe['k'],weight_spec=pe['weight_spec'],status=status,jsonl_record=oe['jsonl_record']))
        desc.append(dict(numerical_task_id=tid,task_ordinal=i,data_row_count=n,estimated_bytes=size,jsonl_record=oe['jsonl_record'],status=status))
    for stream in (ps,cs,os_):stream.finish()
    for parent in (pindex,cindex,index):
        exact(integer(parent['planned_task_count']),1632);exact(integer(parent['projected_task_count']),present);exact(integer(parent['not_supplied_task_count']),1632-present)
    require(len(common_series)==(4 if present else 0) and len(common_risk)==(2 if present else 0),'Shared4/2 exact once');exact(shared,dict(schema='DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1',series=common_series,risk=common_risk,**OUT_FLAGS));exact(index['package_plan'],packages(desc),'Complete package partition and bytes')
    exact(index['shared_series_slot_count'],sum(len(x['series']['slots']) for x in common_series.values()));exact(index['shared_risk_group_and_context_row_count'],sum(sum(len(d['aggregation']['rows'])+1 for d in x['risk']['rows']) for x in common_risk.values()))
    exact(index['original_stream_references'],dict(path=pindex['task_jsonl_reference'],chain=cindex['task_jsonl_reference']));exact(index['full_new_cutoff_task_denominator'],pindex['full_new_cutoff_task_denominator'])
    return dict(planned_tasks=1632,projected_tasks=present,missing_tasks=1632-present,strata_count=51,shared_series=len(common_series),shared_risk=len(common_risk),packages=len(index['package_plan']['packages']),output_rows=os_.count,output_bytes=os_.offset,input_path_rows=ps.count,input_chain_rows=cs.count)

def inspect_classification(got,coverage):
    require(coverage['schema']=='SAVED_CONDITIONAL_CLASSIFICATION_COVERAGE_V1','Original classification');rows=coverage['rows'];require(len(rows)==101 and len({r['ticker'] for r in rows})==101,'All101')
    require(sum(r['conditional_label_present'] is True for r in rows)==78 and sum(r['training_selected'] is True for r in rows)==77 and len({r['issuer_id'] for r in rows if r['training_selected'] is True})==76,'Original78/77/76')
    for r in rows:require(type(r['conditional_label_present']) is bool and type(r['training_selected']) is bool and r['formally_verified'] is False,'Classification flags')
    expected=dict(schema='DATED_WORKBOOK_CLASSIFICATION_TABLE_V1',rows=rows,counts=coverage['counts'],issuer_label_reviews=coverage['issuer_label_reviews'],source_index=coverage['input_references'],saved_wiring_scope=coverage['saved_wiring_scope'],saved_training_scope=coverage['saved_training_scope'],**PURE_FLAGS);exact(got,expected,'Full original classification/sidecars unchanged')

def parent_links(d,r):
    contracts={'path':('SOURCE_BOUND_DATED_PATH_RISK_DISPLAY_V1','DATED_PATH_RISK_DISPLAY_PUBLICATION_V1','PUBLISHED_SAVED_PATH_DISPLAY_ONLY','DATED_PATH_RISK_DISPLAY_INDEPENDENT_READBACK_V1'),'chain':('SOURCE_BOUND_DATED_CHAIN_DISPLAY_V1','DATED_CHAIN_DISPLAY_PUBLICATION_V1','PUBLISHED_DISPLAY_ADDITION_NOT_RISK_REEVALUATION','DATED_RISK_CHAIN_DISPLAY_INDEPENDENT_READBACK_V1'),'classification':('SOURCE_BOUND_SAVED_CLASSIFICATION_COVERAGE_V1','SAVED_CLASSIFICATION_COVERAGE_PUBLICATION_V1','PUBLISHED_CONDITIONAL_SAVED_LABEL_COVERAGE','SAVED_CLASSIFICATION_COVERAGE_INDEPENDENT_READBACK_V1')}
    for role,(schema,ps,status,aus) in contracts.items():
        key=role if role=='classification' else role+'_index';i=d[key];p=d[role+'_publication'];a=d[role+'_audit'];rk='coverage_reference' if role=='classification' else 'index_reference'
        require(i['schema']==schema and p['schema']==ps and p['status']==status and a['schema']==aus and a['status']=='PASS','Successful original parent');exact(p[rk],r[key]);exact(a[rk],r[key]);exact(a['publication_reference'],r[role+'_publication']);exact(p['source_hashes'],i['source_hashes']);exact(a['reader_sha256'],r[role+'_reader']['sha256'])
        for x in (i,p,a):flags(x,('point_in_time_verified','promotion_allowed'))
        require(a['producer_called'] is False,'No parent replay claim')
        for name in ('producer','core'):
            rr=r[role+'_'+name];require(i['source_hashes'].get(rr['path'])==rr['sha256'],'Parent code source')
        for name in (key,role+'_publication',role+'_reader',role+'_producer',role+'_core'):
            rr=r[name];require(a['source_hashes'].get(rr['path'])==rr['sha256'],'Original independent audit source')
    c=d['chain_index'];p=d['path_index'];exact(c['original_projection_index_reference'],r['path_index']);exact(c['original_projection_source_hashes_preserved'],p['source_hashes'])
    for name in ('index','publication','audit','reader','producer'):exact(c['input_references'][name],r['path_'+name])
    exact(c['input_references']['projection_core'],r['path_core'])
    for role,key in [('path','shared_paths_reference'),('chain','shared_control_aggregates_reference')]:
        exact(d[role+'_publication'][key],d[role+'_index'][key]);exact(d[role+'_publication']['task_jsonl_reference'],d[role+'_index']['task_jsonl_reference'])
    exact(d['path_audit']['verified_jsonl_sha256'],p['task_jsonl_reference']['sha256']);exact(d['path_audit']['verified_jsonl_bytes'],p['task_jsonl_reference']['byte_count']);detail=d['chain_audit']['detail'];exact(detail['original_jsonl_sha256'],p['task_jsonl_reference']['sha256']);exact(detail['output_jsonl_sha256'],c['task_jsonl_reference']['sha256']);exact(detail['planned_tasks'],1632);exact(detail['projected_tasks'],c['projected_task_count'])

def load():
    r={k:reference(ROOT/p,h) for k,(p,h) in BOUND.items()};ir=reference(PARENT/'index.json',INDEX_SHA);pr=reference(PARENT/'publication.json',PUBLICATION_SHA);producer=reference(PRODUCER,PRODUCER_SHA);core=reference(CORE,CORE_SHA)
    for v in [*r.values(),ir,pr,producer,core]:checkref(v)
    require({p.name for p in PARENT.iterdir()}=={'started.json','tasks.jsonl','shared_display.json','classification.json','index.json','publication.json'},'Exact successful display namespace')
    sources={str(SOURCE):LOADED};base={};d={}
    for x in (producer,core):read(x,sources);merge(base,x)
    for k,x in r.items():
        blob=read(x,sources);merge(base,x)
        if not k.endswith(('_core','_reader','_producer')):d[k]=loads(blob)
    parent_links(d,r)
    for role,names in [('path',{'started.json','tasks.jsonl','shared_paths.json','index.json','publication.json'}),('chain',{'started.json','tasks.jsonl','shared_control_aggregates.json','index.json','publication.json'}),('classification',{'started.json','coverage.json','publication.json'})]:
        key=role if role=='classification' else role+'_index';require({p.name for p in Path(r[key]['path']).parent.iterdir()}==names,'Exact parent namespace');require(not (Path(r[role+'_audit']['path']).parent/'failure.json').exists(),'No failed audit')
    for role,key,name in [('path','shared_paths_reference','shared_paths.json'),('chain','shared_control_aggregates_reference','shared_control_aggregates.json')]:
        rr=d[role+'_index'][key];checkref(rr);require(Path(rr['path'])==Path(r[role+'_index']['path']).parent/name,'Fixed original shared path');d[role+'_shared']=loads(read(rr,sources));merge(base,rr)
    index=loads(read(ir,sources));pub=loads(read(pr,sources));started_path=PARENT/'started.json';sb=started_path.read_bytes();started_ref=reference(started_path,sha(sb));merge(sources,started_ref);start=loads(sb)
    require(start['schema']=='DATED_WORKBOOK_EXTENSION_DATA_STARTED_V1','Started scope');exact(start['input_references'],r);exact(start['source_hashes'],base,'Independent fixed producer base');flags(start,OUT_FLAGS)
    require(index['schema']=='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1','Display index schema');exact(index['input_references'],r)
    expected=dict(base);streamrefs=[]
    for role in ('path','chain'):
        rr=d[role+'_index']['task_jsonl_reference'];require(Path(rr['path'])==Path(r[role+'_index']['path']).parent/'tasks.jsonl','Fixed source task path');merge(expected,simple(rr));streamrefs.append(simple(rr));merge(sources,simple(rr))
    exact(index['source_hashes'],expected,'Exact producer source union');exact(pub['source_hashes'],expected)
    exact(index['parent_source_hashes_preserved'],{k:d[k]['source_hashes'] for k in ('path_index','chain_index','classification')})
    require(pub['schema']=='DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1' and pub['status']=='PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY','Published display data only');exact(pub['index_reference'],ir)
    for obj in (index,pub):flags(obj,OUT_FLAGS)
    for key,name in [('task_jsonl_reference','tasks.jsonl'),('shared_display_reference','shared_display.json'),('classification_reference','classification.json')]:
        exact(pub[key],index[key]);require(Path(index[key]['path'])==PARENT/name,'Fixed output child path')
    shared=loads(read(index['shared_display_reference'],sources));classification=loads(read(index['classification_reference'],sources));outref=simple(index['task_jsonl_reference']);merge(sources,outref);streamrefs.append(outref)
    require(d['path_shared']['schema']=='DATED_PATH_RISK_SHARED_PATHS_V1' and d['chain_shared']['schema']=='DATED_CHAIN_SHARED_CONTROL_AGGREGATES_V1','Original shared schemas')
    exact(index['source_verification_scope'],'TWO_INPUT_STREAMS_HASHED_ONCE_DURING_CONSUMPTION;FIXED_METADATA_RECHECKED;NO_TRANSITIVE_REPLAY');exact(index['delivery_status'],'DISPLAY_DATA_ONLY_NOT_H_WORKBOOK_DELIVERY');exact(index['byte_estimate_basis'],'ACTUAL_COMPACT_DISPLAY_JSONL_BYTES_NOT_XLSX_ZIP_OR_RENDER_MEMORY');exact(index['data_row_count_basis'],'CANDIDATE_PATH_SLOTS_PLUS_ALL_CHAIN_GROUP_ROWS_AND_CASH_CONTEXT_PLUS_ORIGINAL_TARGET_GROUPS;SHARED_ROWS_ONCE_SEPARATE')
    expected_keys={'schema','task_index','planned_task_count','projected_task_count','not_supplied_task_count','package_plan','full_new_cutoff_task_denominator','shared_series_slot_count','shared_risk_group_and_context_row_count','original_stream_references','byte_estimate_basis','data_row_count_basis','task_jsonl_reference','shared_display_reference','classification_reference','input_references','source_hashes','parent_source_hashes_preserved','source_verification_scope','delivery_status'}|set(OUT_FLAGS);exact(sorted(index),sorted(expected_keys),'Exact index fields')
    nonstream={p:h for p,h in sources.items() if p not in {x['path'] for x in streamrefs}};guard(nonstream)
    return d,index,shared,classification,r,ir,pr,started_ref,sources,nonstream

def run(*,execute=False):
    require(execute is True,'Explicit readback');require(not OUTPUT.exists(),'Create-only readback; no retry');loaded=load();d,index,shared,classification,r,ir,pr,sr,sources,nonstream=loaded
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        inspect_classification(classification,d['classification']['coverage'])
        with Path(d['path_index']['task_jsonl_reference']['path']).open('rb') as p,Path(d['chain_index']['task_jsonl_reference']['path']).open('rb') as c,Path(index['task_jsonl_reference']['path']).open('rb') as o:
            detail=inspect_streams(p,c,o,d['path_index'],d['chain_index'],index,d['path_shared']['shared_paths'],d['chain_shared']['aggregates'],shared)
        guard(nonstream)
        result=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=LOADED,index_reference=ir,publication_reference=pr,started_reference=sr,started_has_separate_external_anchor=False,input_references=r,source_hashes=sources,detail=detail,classification_rows_verified=101,verified_jsonl_sha256=index['task_jsonl_reference']['sha256'],verified_jsonl_bytes=index['task_jsonl_reference']['byte_count'],producer_called=False,pure_projection_called=False,scope='SAVED_DISPLAY_PROJECTION_AND_BYTE_CLOSURE_NOT_XLSX_RENDER_OR_ECONOMIC_RECALCULATION',**OUT_FLAGS)
        answer=save(OUTPUT/'independent_readback.json',result);guard(nonstream);require({p.name for p in OUTPUT.iterdir()}=={'independent_readback.json'},'Exact singleton audit');require(sha(Path(answer['path']).read_bytes())==answer['sha256'],'Final report bytes');return answer
    except BaseException as error:
        if not (OUTPUT/'failure.json').exists():save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),retry_allowed=False))
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
