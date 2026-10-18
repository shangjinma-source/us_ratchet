"""New dated task inputs only; fixed previous compositions, never old weights."""
import argparse
from copy import deepcopy
import hashlib,json,os,platform,sys,types
from pathlib import Path

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_fixed_task_preparation_research.py';CORE_SHA='eb081835d37825688fdf2eb0cb8b90b36d693d15b8f9cc6f6b8659258a8e87e6'
OUTPUT=ROOT/'data/cache/research/dated_fixed_task_preparation_20261003_v1'
AUDIT_SCHEMA='DATED_TRAINING_PANEL_INDEPENDENT_READBACK_V1'
BOUND={
 'training':('data/cache/research/dated_training_panel_20261003_v1/panel.json','895f31e30647e1422bcd2feab3025f8e9103c745f9d176549d59a069a30b9d96'),
 'training_publication':('data/cache/research/dated_training_panel_20261003_v1/publication.json','2b64693fd54c1358429ca9df8ac5c9b685882d419a275a7b4384e878c5c1a2a5'),
 'training_readback':('DYNAMIC_DATED_TRAINING_PANEL_INDEPENDENT_READBACK_20261003.json','38b5a61dbfae53264c8691e421d1bbb00140f567d437b5692543c9313a0d95bd'),
 'prior_preparation':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/preparation.json','03d60c666e06a00fa44b19b16cda9609b4e2a75d411dff7ac6cd0e0c08915da1'),
 'prior_publication':('data/cache/research/bulk_budgeted_search_prepare_20261003_v1/publication.json','2471685a55d652a9e732b2a6cdf218232a192f07c3ed6e9e9824f95f5cb76212'),
 'original_plan':('data/cache/research/bulk_all_k_plan_20261003_v1/plan.json','77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'),
 'prior_audit':('DYNAMIC_BULK_BUDGETED_SEARCH_PREPARE_INDEPENDENT_READBACK_20261003.json','ea0f3793f4a47f3cb58eb7125e5685344891eb9bc955cdcd1295866d1c801c1f'),
}
FLAGS=dict.fromkeys(('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','old_fit_results_reused','old_weights_reused','old_raw_reaudited','full_transitive_source_closure_reverified','runtime_binary_closure_verified','all_plan_tasks_completed','future_independent_oos','untouched_holdout'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(b):return hashlib.sha256(b).hexdigest()


def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def exact(a,b,msg):require(encode(a)==encode(b),msg)


def loads(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def reject(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=reject)


def runtime():return dict(python=sys.version,executable=str(Path(sys.executable).resolve()),implementation=platform.python_implementation(),platform=platform.platform())


def project_inputs(docs,refs):
    typed=docs['training'];pub=docs['training_publication'];audit=docs['training_readback'];prior=docs['prior_preparation'];oldpub=docs['prior_publication']
    require(typed['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1' and pub['status']=='PUBLISHED_TRAINING_PAYLOAD_NOT_FITTED','New training publication')
    exact(pub['panel_reference'],refs['training'],'Training reference');exact(pub['source_hashes'],typed['source_hashes'],'Training publication sources')
    require(type(AUDIT_SCHEMA) is str and audit['schema']==AUDIT_SCHEMA and audit['status']=='PASS','New actual independent training readback required')
    require(audit['panel_sha256']==refs['training']['sha256'] and audit['publication_sha256']==refs['training_publication']['sha256'],'Training readback binding')
    for item in (typed,pub):require(all(item[k] is False for k in ('fit_performed','point_in_time_verified','execution_authorized','legal_training_input_admitted')),'Typed permission unchanged')
    # Older preparation is a constituent-selection source, not a dated completion.
    require(prior['schema']=='BULK_BUDGETED_SEARCH_PREPARATION_V1','Original composition source')
    require(docs['prior_audit']['status']=='PASS' and docs['prior_audit']['preparation_sha256']==refs['prior_preparation']['sha256'] and docs['prior_audit']['publication_sha256']==refs['prior_publication']['sha256'],'Saved prior input audit')
    require(oldpub['schema']=='BULK_BUDGETED_SEARCH_PREPARATION_PUBLICATION_V1' and oldpub['status']=='PREPARED_NOT_ATTEMPTED','Saved prior publication')
    exact(oldpub['source_hashes'],prior['source_hashes'],'Saved prior source map');exact(oldpub['preparation_reference'],refs['prior_preparation'],'Old publication reference')
    return dict(training_panel=typed['panel'],training_reference=deepcopy(refs['training']),training_readback_reference=deepcopy(refs['training_readback']),prior_preparation=prior,prior_preparation_reference=deepcopy(refs['prior_preparation']),original_lazy_plan=docs['original_plan']['plan'],original_plan_reference=deepcopy(refs['original_plan']))


def guard(sources,run_runtime):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift');exact(runtime(),run_runtime,'Runtime drift')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Bound source drift: '+p)


def load_inputs():
    require(type(AUDIT_SCHEMA) is str and all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Actual training audit anchor pending')
    docs={};refs={};sources={str(SOURCE):LOADED_SHA};run_runtime=runtime()
    def read(p,h):
        p=p.resolve();require(str(p) not in sources or sources[str(p)]==h,'Conflicting source closure');blob=p.read_bytes();require(sha(blob)==h,'Source bytes differ');sources[str(p)]=h;return blob
    for role,(relative,h) in BOUND.items():
        p=ROOT/relative;docs[role]=loads(read(p,h));refs[role]=dict(path=str(p.resolve()),sha256=h)
    for role,names in [('training',{'started.json','panel.json','publication.json'}),('prior_preparation',{'started.json','preparation.json','publication.json'})]:require({p.name for p in Path(refs[role]['path']).parent.iterdir()}==names,'Parent failed/incomplete namespace')
    fitter_sources=docs['original_plan']['plan']['fitter_source_hashes'];require(len(fitter_sources)==25,'Full frozen numerical source map')
    for p,h in fitter_sources.items():read(Path(p),h)
    corebytes=read(CORE,CORE_SHA);guard(sources,run_runtime)
    core=types.ModuleType('_fresh_dated_tasks');core.__file__=str(CORE);exec(compile(corebytes,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,run_runtime,core


def save(path,value):
    blob=encode(value)
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Output differs');return dict(path=str(path),sha256=sha(blob))


def run(*,execute=False):
    require(type(execute) is bool,'Exact boolean execute');require(not OUTPUT.exists(),'Immutable namespace already exists')
    if not execute:return dict(status='NOT_EXECUTED',output=str(OUTPUT))
    docs,refs,sources,run_runtime,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,runtime=run_runtime,retry_allowed=False,**FLAGS))
        args=project_inputs(docs,refs);result=core.prepare_dated_tasks(**args)
        require(result['schema']=='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_V1' and result['content_sha256']==sha(encode({k:v for k,v in result.items() if k!='content_sha256'})),'Dated materialization output')
        require(type(result['materialized_task_count']) is int and result['materialized_task_count']==1632 and result['new_fit_count']==0,'New full batch, no fits')
        value=dict(schema='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_DOCUMENT_V1',materialized=result,training_fit_payload=deepcopy(docs['training']['panel']['fit_payload']),complete_observed_provenance_and_missing=deepcopy(docs['training']['panel']['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(docs['training']['panel']['preserved_evidence_sidecars']),original_coordinate_evidence=deepcopy(docs['training']['panel']['original_coordinate_evidence']),evaluation_references=deepcopy(docs['training']['panel']['evaluation_references']),input_references=refs,source_hashes=sources,runtime=run_runtime,late_pool_and_composition_selection=True,**FLAGS)
        guard(sources,run_runtime);out=save(OUTPUT/'preparation.json',value);guard(sources,run_runtime)
        pub=save(OUTPUT/'publication.json',dict(schema='DATED_FIXED_CONSTITUENT_TASK_PREPARATION_PUBLICATION_V1',status='PUBLISHED_NEW_DATED_TASK_INPUTS_NOT_FITTED',preparation_reference=out,source_hashes=sources,runtime=run_runtime,**FLAGS));guard(sources,run_runtime)
        require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(pub['path']).read_bytes())==pub['sha256'],'Final sourcebound readback');require({p.name for p in OUTPUT.iterdir()}=={'started.json','preparation.json','publication.json'},'Unexpected output entry')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),retry_allowed=False));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
