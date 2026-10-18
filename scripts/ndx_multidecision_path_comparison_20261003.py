"""Create-only saved-path comparison publisher. No account, fitter or ledger replay.

A private authenticated adapter receives only this publisher's static 20-role
configuration. Its frozen on-disk defaults remain None; no caller callback or
runtime path discovery is an execution interface.
"""
from pathlib import Path
import builtins
import hashlib
import json
import os
import re
import shutil
import traceback
import types

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/multidecision_path_comparison_20261003_v1'
ADAPTER=('scripts/ndx_multidecision_path_comparison_source_adapter_20261003.py','3e9690118f50248dbf939f613cc7cf0fc5dabbb7ee2db5a4d3be79b33285d32b')
BOUND={}
for role,prefix in (('candidate','account'),('control','incumbent')):
    for name,file in (('inputs','inputs.json'),('inputs_publication','publication.json')):BOUND[role+'_'+name]=(f'data/cache/research/multidecision_{prefix}_inputs_20261003_v1/{file}',None)
    BOUND[role+'_inputs_audit']=(f'data/cache/research/multidecision_{prefix}_inputs_independent_readback_20261003_v1/independent_readback.json',None)
    BOUND[role+'_inputs_reader']=(f'scripts/ndx_multidecision_{prefix}_inputs_independent_readback_20261003.py',None)
    for name,file in (('execution','result.json'),('execution_publication','publication.json')):BOUND[role+'_'+name]=(f'data/cache/research/multidecision_{prefix}_execution_20261003_v1/{file}',None)
    BOUND[role+'_audit']=(f'data/cache/research/multidecision_{prefix}_execution_independent_readback_20261003_v1/independent_readback.json',None)
    BOUND[role+'_reader']=(f'scripts/ndx_multidecision_{prefix}_execution_independent_readback_20261003.py',None)
BOUND.update(nav_metrics=('data/cache/research/multidecision_nav_reference_metrics_20261003_v1/metrics.json',None),nav_publication=('data/cache/research/multidecision_nav_reference_metrics_20261003_v1/publication.json',None),nav_audit=('data/cache/research/multidecision_nav_reference_metrics_independent_readback_20261003_v1/independent_readback.json',None),nav_reader=('scripts/ndx_multidecision_nav_reference_metrics_independent_readback_20261003.py',None))
ACTUAL_SOURCE_HASHES={'candidate_inputs': 'c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9', 'candidate_inputs_publication': '64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940', 'candidate_inputs_audit': '8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb', 'candidate_inputs_reader': '85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d', 'candidate_execution': 'c79aafa533d78be14f888cd109d9942702c829c39d5ce0d09904501b5c812870', 'candidate_execution_publication': 'e1b00c1c1f8e4b4d31893e77ba46bc12009ba3e5fd452fdca1b1b01266ab68c7', 'candidate_audit': '33ebcb571c81793f92070c8db789b409b98eca139778c0c192c80fa6abcc74bb', 'candidate_reader': '69c54a144ca582a8537a4c52b0fbb6fdf61a0f2ece0d4233206cc87f6f729ca2', 'control_inputs': '9705b1ed2e42351050a5e413dcbe73fdc5d42efc16a03a79b560fe0c69f68aa4', 'control_inputs_publication': '5b8da9d3440422ec8899d5ad73abf589ea43a1869aa4aa84b6227ce480958fe9', 'control_inputs_audit': '48aac644a66b2832d48ff6ea7100e3aa720c68da2e6d1a3bc35e1f5ae95d02f1', 'control_inputs_reader': 'de6b6a6da0c3aa327855e029e937a25d66069d98b01598b69818534984f8ffc9', 'control_execution': 'f837b2a71c7a0d9a08610e211d2c7b1a799902aa38ae1e92d661906a806c2eb4', 'control_execution_publication': 'c56230fca7cc7de0c7ef79604a4588eb7afa3202f61c0baaeae8b5609d5c4afd', 'control_audit': '8b8e318426c94b6a70389a724f50c30df68c807204ad789f2159185cd943e975', 'control_reader': '35cd3824d935f75eb00c05161f89291f287587122fce0b63f7dd8a8fa1fff730', 'nav_metrics': '2dc029413e03a8721c0c9baf6494115244f9d96b57640849090fb36be4d69a59', 'nav_publication': 'eda71707860dc127c43e343d568b6cfdb781060576b2d649546e90797e8866db', 'nav_audit': '7d93d12d18059d5806ce9059e376b2beb0f3995dd3b0d3f12f61892b25cf1372', 'nav_reader': 'c3a0a7ad28f6e8eb46c172ab000e520fe17c7744e679f9834fcf776fda83f6f6'}
BOUND={role:(path,ACTUAL_SOURCE_HASHES[role]) for role,(path,_) in BOUND.items()}
ROLE_KEYS=frozenset(BOUND)
CODE={
'ndx_multidecision_path_comparison_research':'741cfa727b30949dff60983ece89a8a734df98b988c1c0a484b1c650d80278d1',
'ndx_multidecision_reference_metrics_research':'0a1ef7ff8590538fdb29ce013027bd2ebd0ed17a816f405bc43bb0eef9489e62',
'ndx_same_window_nav_reference_metrics_research':'bfb582e72dd3a23da5da4898d633d5afa310af0132aa16bb6896ebcac0d82a4f',
'ndx_cash_fork_reference_window_research':'0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163'}
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_engine_called','account_ledger_replayed','fit_performed','selection_performed','actual_orders_executed','execution_authorized','promotion_allowed','point_in_time_verified','formal_comparison_passed','formal_noninferiority_passed','cohort_statistics_computed','future_independent_oos','automatic_retry_allowed'),False)


def require(x,message):
    if not x:raise ValueError(message)


def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)


def preflight():
    require(set(BOUND)==ROLE_KEYS and len(BOUND)==20,'All20 exact fixed roles')
    for p,h in list(BOUND.values())+[ADAPTER]:
        require(type(p)is str and p and type(h)is str and re.fullmatch('[a-f0-9]{64}',h),'Future source anchors pending; no IO')


def load_code(path,digest,sources):
    p=(ROOT/path).resolve();raw=p.read_bytes();require(sha(raw)==digest,'Same authenticated code bytes')
    require(str(p) not in sources or sources[str(p)]==digest,'Source conflict');sources[str(p)]=digest;return p,raw


def private_adapter(sources):
    path,raw=load_code(*ADAPTER,sources);module=types.ModuleType('_comparison_source_adapter');module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    require(set(module.BOUND)==ROLE_KEYS and module.LOADED==ADAPTER[1],'Fixed original adapter identity')
    module.BOUND=dict(BOUND)
    return module


def private_core(sources):
    blobs={k:load_code('backtest/'+k+'.py',h,sources) for k,h in CODE.items()};cache={}
    def importer(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='backtest':
            require(level==0,'Absolute helper imports');return types.SimpleNamespace(**{k:module(k) for k in fromlist})
        if name.startswith('backtest.'):
            require(level==0 and fromlist,'Explicit registered helper import');return module(name.split('.',1)[1])
        return builtins.__import__(name,globals,locals,fromlist,level)
    def module(name):
        require(name in blobs,'Only frozen numerical dependency closure')
        if name not in cache:
            path,raw=blobs[name];m=types.ModuleType('_comparison_'+name);m.__file__=str(path);m.__dict__['__builtins__']=dict(vars(builtins),__import__=importer);cache[name]=m;exec(compile(raw,str(path),'exec'),m.__dict__)
        return cache[name]
    return module('ndx_multidecision_path_comparison_research')


def guard(c):
    require(sha(SOURCE.read_bytes())==LOADED,'Publisher source drift')
    c['adapter'].guard(c['source_hashes'],c['source_inventories'])


def load_inputs():
    preflight();sources={str(SOURCE):LOADED};adapter=private_adapter(sources);c=adapter.read_inputs()
    for p,h in c['source_hashes'].items():require(p not in sources or sources[p]==h,'Source union conflict');sources[p]=h
    c['source_hashes']=sources;c['adapter']=adapter;c['core']=private_core(sources);guard(c);return c


def save(name,value,*,emergency=False):
    raw=enc(value);folder=OUTPUT
    if not emergency:require(shutil.disk_usage(folder).free>=5*1024**3+len(raw),'5GiB plus encoded output reserve')
    p=folder/name
    with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    return ref(p,sha(raw))


def validate_result(result):
    require(type(result)is dict and result.get('schema')=='MULTIDECISION_SAME_WINDOW_PATH_DIAGNOSTIC_V1','Returned comparison object required')
    require(type(result['track_count'])is int and result['track_count']==16 and len(result['rows'])==16 and result['coordinate_count']==48 and result['lane_count']==8,'Complete comparison domain')
    for key in ('source_bytes_authenticated','account_executed','fit_performed','formal_comparison_passed','formal_noninferiority_passed','cohort_statistics_computed','promotion_allowed','future_independent_oos','point_in_time_verified','winner_selected','fx_mode_selected_using_results'):require(result[key]is False,'No result authority upgrade')


def output_guard(refs):
    require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in refs},'Exact output inventory')
    for r in refs:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final output bytes drift')


def run(*,execute=False):
    require(execute is True,'Explicit execution required');preflight();require(not OUTPUT.exists(),'Exclusive attempt; no retry')
    c=load_inputs();require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3,'5GiB startup reserve');OUTPUT.mkdir();written=[];invoked=False;returned=False
    common=dict(input_references=c['input_references'],source_hashes=c['source_hashes'],source_inventories=c['source_inventories'],adapter_reference=ref(ROOT/ADAPTER[0],ADAPTER[1]),adapter_configuration_source='AUTHENTICATED_PUBLISHER_STATIC20_BOUND_IN_PRIVATE_INSTANCE_ON_DISK_DEFAULTS_NOT_EXECUTED',all_original_audit_starts_externally_anchored=False,**FLAGS)
    try:
        written.append(save('started.json',dict(schema='MULTIDECISION_PATH_COMPARISON_STARTED_V1',**common)))
        guard(c);require(shutil.disk_usage(OUTPUT).free>=5*1024**3,'5GiB before numerical dispatch');invoked=True;result=None;error=None
        try:result=c['core'].compare_multidecision_paths(**c['kwargs']);returned=True
        except BaseException as e:error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
        raw=dict(schema='MULTIDECISION_PATH_COMPARISON_RAW_RETURN_V1',call_invoked=invoked,returned=returned,result=result,error=error,original_return_is_json=True,returned_type=type(result).__name__ if returned else None,started_reference=written[0],**common)
        try:enc(raw)
        except BaseException as serialization_error:
            try:diagnostic=repr(result);repr_error=None
            except BaseException as e:diagnostic=None;repr_error=dict(type=type(e).__name__,message=str(e))
            raw.update(result=None,original_return_is_json=False,return_diagnostic_repr=diagnostic,repr_error=repr_error,serialization_error=dict(type=type(serialization_error).__name__,message=str(serialization_error)))
        written.append(save('raw_result.json',raw,emergency=True));guard(c)
        require(error is None and returned and raw['original_return_is_json'],'Comparison exception/serialization failure preserved')
        validate_result(result)
        document=dict(schema='MULTIDECISION_PATH_COMPARISON_DOCUMENT_V1',comparison=result,raw_reference=written[-1],independent_readback_status='PENDING',**common)
        resultref=save('comparison.json',document);written.append(resultref);guard(c)
        written.append(save('publication.json',dict(schema='MULTIDECISION_PATH_COMPARISON_PUBLICATION_V1',status='PUBLISHED_SINGLE_PATH_DIAGNOSTICS_PENDING_INDEPENDENT_READBACK_NOT_FORMAL_GATE',comparison_reference=resultref,raw_reference=written[1],started_reference=written[0],**common)))
        guard(c);output_guard(written);return resultref
    except BaseException as e:
        if not(OUTPUT/'failure.json').exists():save('failure.json',dict(schema='MULTIDECISION_PATH_COMPARISON_FAILURE_V1',status='FAILED_NO_RETRY',call_invoked=invoked,returned=returned,saved_references=written,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),**common),emergency=True)
        raise

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(execute=args.execute)))
