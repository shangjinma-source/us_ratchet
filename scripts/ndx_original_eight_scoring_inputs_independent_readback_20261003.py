"""Reuse eight sealed channels for fixed daily-weight scoring; no raw reconstruction."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,os,types,shutil
import pandas as pd
import numpy as np
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_original_eight_scoring_inputs_research.py';CORE_SHA='ebc087446b6262a2178cb938925d9903d4aac217338242d25857c598d5396a33'
PARENT=ROOT/'data/cache/research/original_eight_scoring_inputs_20261003_v1'
OUTPUT=ROOT/'data/cache/research/original_eight_scoring_inputs_independent_readback_20261003_v1'
INPUTS_SHA='92d3fef00a69028caaeaecf3ded659d81b0c081e4537ba1da6fa24afb8f77d51'
PUBLICATION_SHA='1df61b4b66705ce783e1066a3a924a36c9a7c5348caa516f9677668d4c278de4'
PRODUCER=ROOT/'scripts/ndx_original_eight_scoring_inputs_20261003.py'
PRODUCER_SHA='1b6a2f5c8ab0ca14677c304d3ab2f72112bbcb49dd56c8a4a522405967b95d83'
INSPECTOR=ROOT/'backtest/ndx_original_eight_scoring_inspection_research.py'
INSPECTOR_SHA='786565451fc3124953ea5f1e70f761fdc82848cdb110a3facdea2f62a67cbbdb'
BOUND={
'control':('data/cache/research/ndx_original_8_control_v1/manifest.json','2ca955ce951061a2aa89242c53c645775f36a658e2f51db1dc3732582317a260'),
'index':('data/cache/research/multidecision_scoring_history_20261003_v1/index.json','ce4fd8a1a8f7f0c9c1ddd20cd4136c1c078e4aae81b37e61c9a1b0aae981ff2d'),
'index_publication':('data/cache/research/multidecision_scoring_history_20261003_v1/publication.json','e413e1cb7c10b543042fb7cbc34eafda48c93cfab3f25cd4e5b9f798249e88b9'),
'index_audit':('data/cache/research/multidecision_scoring_history_independent_readback_20261003_v2/independent_readback.json','a338dbbdfa4bc7ffdc6e83ee93bc6e55802201dd7f18049d398ae394029a5b1a'),
'index_reader':('scripts/ndx_multidecision_scoring_history_independent_readback_v2_20261003.py','6ae5ca2c757badd0ebfa2fa35bf3550584b4a989155e44e7d7fd120ca61f6703')}
BOUND.update(tsm=('data/cache/research/original_eight_tsm_scoring_history_20261003_v1/channel.json','85779cc0bdca5ed70a496626c697d157089064a314e51b27b74b5e412c021a93'),tsm_publication=('data/cache/research/original_eight_tsm_scoring_history_20261003_v1/publication.json','6011dd0df112123c81c3c17e6db9437c08ac68d04853a157f9a451430785e033'),tsm_audit=('data/cache/research/tsm_scoring_history_independent_readback_20261003_v1/independent_readback.json','07058ef1bcd6636e9ab130f542ad375b1ffd527d816dd5dc6034078c9b0301a9'),tsm_reader=('scripts/ndx_tsm_scoring_history_independent_readback_20261003.py','469b2c7773c4adc9231c1df67338222ef5ba293e8631cd95a65dc8b74f5df6e9'))
ORDER=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
FLAGS=('fit_performed','score_computed','account_simulation_performed','raw_reconstructed','old_audit_repeated','point_in_time_verified','historical_identity_verified','historical_risk_verified','execution_authorized','promotion_allowed','benchmark_qualified','full_transitive_source_closure_reverified')

def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,msg):require(encoded(a)==encoded(b),msg)
def loads(b):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'Duplicate key');d[k]=v
        return d
    def reject(x):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=reject)
def merge(s,p,h):require(p not in s or s[p]==h,'Source hash conflict');s[p]=h


def inspect_parent_bindings(docs,refs):
    index=docs['index'];audit=docs['index_audit'];tsm=docs['tsm'];ta=docs['tsm_audit']
    require(index['schema']=='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1' and tsm['schema']=='TSM_CONTROL_SCORING_HISTORY_DOCUMENT_V1','Saved numeric schemas')
    for role,schema,status,key in [('index','MULTIDECISION_SCORING_HISTORY_PUBLICATION_V1','PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK','index_reference'),('tsm','TSM_CONTROL_SCORING_HISTORY_PUBLICATION_V1','PUBLISHED_CONTROL_NUMBERS_PENDING_INDEPENDENT_READBACK','channel_reference')]:
        pub=docs[role+'_publication'];require(pub['schema']==schema and pub['status']==status,'Successful saved publication');exact(pub[key],refs[role],'Publication binding');exact(pub['source_hashes'],docs[role]['source_hashes'],'Publication source claims')
    for role,a,key in [('index',audit,'index_reference'),('tsm',ta,'channel_reference')]:
        require(a['status']=='PASS' and a['reader_sha256']==refs[role+'_reader']['sha256'],'Independent reader status');exact(a[key],refs[role],'Independent channel/index');exact(a['publication_reference'],refs[role+'_publication'],'Independent publication')
        require(all(a[k] is False for k in ('point_in_time_verified','fit_performed','execution_authorized','promotion_allowed')),'Audit scope')
    require(audit['schema']=='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2' and ta['schema']=='TSM_CONTROL_SCORING_HISTORY_INDEPENDENT_READBACK_V1','Independent schemas')
    require(type(index['security_count']) is int and index['security_count']==77 and len(index['rows'])==len(audit['rows'])==77,'Full77 source denominator')
    control=tsm['original_control_preserved'];exact(control['complete_original_manifest'],docs['control'],'Original manifest');exact(control['complete_original_definition'],docs['control']['definition'],'Original definition');exact(control['securities'],docs['control']['definition']['securities'],'Original targets')
    require([s['ticker'] for s in control['securities']]==ORDER,'Original eight order')
    by={r['coordinate']['ticker']:(i,r) for i,r in enumerate(index['rows'])};require(len(by)==77 and 'TSM' not in by,'Original candidate scope')
    bindings=[]
    for s in control['securities']:
        if s['ticker']=='TSM':
            require(ta['arithmetic']['ticker']=='TSM' and ta['arithmetic']['status']=='PASS' and type(ta['arithmetic']['window_count']) is int and ta['arithmetic']['window_count']==78,'TSM complete arithmetic audit')
            exact(tsm['channel']['original_control_contract']['securities'],control['securities'],'TSM original targets')
            bindings.append(dict(coordinate=deepcopy(s),channel=deepcopy(tsm['channel']),channel_reference=dict(refs['tsm'],json_pointer='/channel'),independent_readback_reference=dict(refs['tsm_audit'],json_pointer='/arithmetic')))
        else:
            i,row=by[s['ticker']];a=audit['rows'][i]
            require(type(row['index']) is int and row['index']==i and type(a['index']) is int and a['index']==i,'Original index location')
            exact(a['coordinate'],row['coordinate'],'Audited coordinate');exact(a['channel_reference'],row['channel_reference'],'Audited channel')
            for k in ('ticker','security_id','issuer_id','risk_chain'):require(row['coordinate'][k]==s[k],'Original control/SID mapping')
            require(a['inspection']['status']=='PASS' and a['inspection']['ticker']==s['ticker'] and type(a['inspection']['window_count']) is int and a['inspection']['window_count']==78,'Per-ticker78 audit')
            bindings.append(dict(coordinate=deepcopy(s),channel=None,channel_reference=deepcopy(row['channel_reference']),independent_readback_reference=dict(refs['index_audit'],json_pointer=f'/rows/{i}/inspection')))
    return dict(original_control=deepcopy(control),control_reference=deepcopy(refs['control']),channel_bindings=bindings)


def take(p,h,sources):
    require(not (p.parent/'failure.json').exists(),'Source failure marker');b=p.read_bytes();require(sha(b)==h,'Source bytes '+str(p));merge(sources,str(p),h);return b

def guard(sources):
    require({p.name for p in PARENT.iterdir()}=={'started.json','inputs.json','publication.json'},'Exact successful parent namespace')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift')
    for p,h in sources.items():take(Path(p),h,{})



def inspect_document(document,publication,started,docs,refs,producer_sources,args):
    require(document['schema']=='ORIGINAL_EIGHT_SCORING_INPUTS_DOCUMENT_V1' and publication['schema']=='ORIGINAL_EIGHT_SCORING_INPUTS_PUBLICATION_V1' and started['schema']=='ORIGINAL_EIGHT_SCORING_INPUTS_STARTED_V1','Output schemas')
    for d in (document,publication):
        require(d['status']=='PUBLISHED_FIXED_DAILY_WEIGHT_RETURNS_PENDING_INDEPENDENT_READBACK','Pending numeric audit status')
        require(all(d[k] is False for k in FLAGS),'Authority fields')
        exact(d['input_references'],refs,'All direct parent references');exact(d['source_hashes'],producer_sources,'Independent source closure')
    exact(started['input_references'],refs,'Started references');exact(started['source_hashes'],producer_sources,'Started exact sources');require(started['retry_allowed'] is False,'No retry')
    require(type(document['raw_channel_reconstruction_count']) is int and document['raw_channel_reconstruction_count']==0 and document['new_numeric_readback_completed'] is False,'No raw/new audit claims')
    exact(document['shared_source_provenance'],dict(original101=docs['index']['original_provenance_and_missing'],seven_sidecars=docs['index']['preserved_evidence_sidecars'],tsm_metadata=docs['tsm']['complete_tsm_metadata']),'All original source evidence')
    exact(document['runtime'],dict(pandas=pd.__version__,numpy=np.__version__),'Matching numerical runtime versions')
    exact(document['scoring_inputs']['original_control_preserved'],args['original_control'],'Original control')


def save(p,v):
    b=encoded(v)
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved audit bytes');return dict(path=str(p),sha256=sha(b))


def readback(*,execute=False):
    require(execute is True,'Explicit execute')
    require(all(type(h) is str and len(h)==64 for h in (INPUTS_SHA,PUBLICATION_SHA,PRODUCER_SHA,INSPECTOR_SHA)),'Pending external anchors before IO')
    require(not OUTPUT.exists(),'Immutable audit namespace');require({p.name for p in PARENT.iterdir()}=={'started.json','inputs.json','publication.json'},'Successful exact parent namespace')
    sources={};base={str(PRODUCER):PRODUCER_SHA,str(CORE):CORE_SHA};docs={};refs={}
    for role,(relative,h) in BOUND.items():
        path=ROOT/relative;b=take(path,h,sources);base[str(path)]=h;refs[role]=dict(path=str(path),sha256=h)
        if not role.endswith('_reader'):docs[role]=loads(b)
    args=inspect_parent_bindings(docs,refs)
    for binding in args['channel_bindings']:
        if binding['channel'] is None:
            r=binding['channel_reference'];binding['channel']=loads(take(Path(r['path']),r['sha256'],sources));merge(base,r['path'],r['sha256'])
        require(binding['channel']['ticker']==binding['coordinate']['ticker'],'Consumed channel ticker')
    for p,h in ((PRODUCER,PRODUCER_SHA),(CORE,CORE_SHA)):take(p,h,sources)
    for module in (pd,np):
        p=Path(module.__file__).resolve();b=p.read_bytes();h=sha(b);merge(base,str(p),h);merge(sources,str(p),h)
    document=loads(take(PARENT/'inputs.json',INPUTS_SHA,sources));publication=loads(take(PARENT/'publication.json',PUBLICATION_SHA,sources))
    raw=(PARENT/'started.json').read_bytes();merge(sources,str(PARENT/'started.json'),sha(raw));started=loads(raw)
    exact(publication['inputs_reference'],dict(path=str(PARENT/'inputs.json'),sha256=INPUTS_SHA),'Publication binds input bytes')
    inspect_document(document,publication,started,docs,refs,base,args)
    code=take(INSPECTOR,INSPECTOR_SHA,sources);merge(sources,str(SOURCE),LOADED_SHA);guard(sources)
    private=types.ModuleType('_private_original8_inspector');exec(compile(code,str(INSPECTOR),'exec'),private.__dict__)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        begun=save(OUTPUT/'started.json',dict(schema='ORIGINAL_EIGHT_SCORING_READBACK_STARTED_V1',source_hashes=sources))
        result=private.inspect_original_eight_scoring_inputs(saved_inputs=document['scoring_inputs'],**args)
        guard(sources)
        out=save(OUTPUT/'independent_readback.json',dict(schema='ORIGINAL_EIGHT_SCORING_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',inputs_reference=dict(path=str(PARENT/'inputs.json'),sha256=INPUTS_SHA),publication_reference=dict(path=str(PARENT/'publication.json'),sha256=PUBLICATION_SHA),reader_sha256=LOADED_SHA,arithmetic=result,source_hashes=sources,started_external_anchor_available=False,**dict.fromkeys(FLAGS,False)))
        guard(sources);require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact audit namespace')
        for r in (begun,out):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Audit output drift')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),retry_allowed=False));raise


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
