"""Pending source-bound candidate diagnostic publisher; never calls accounts."""
import argparse,builtins,hashlib,json,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/candidate_saved_risk_diagnostic_20261008_v1'
IO=ROOT/'scripts/ndx_candidate_saved_risk_sources_20261008.py';IO_SHA='5636c4704906e0b74d8b9400627de1d9b2ab74f2808550cdb0ccf24c08c86a75'
DIAGNOSTIC=ROOT/'backtest/ndx_saved_holdings_risk_diagnostic_research.py';DIAGNOSTIC_SHA='34dd4482b1480881faa06f45850d348d893d2f9031285ee5ec24ddabfd7f361e'
PROJECTION=ROOT/'backtest/ndx_candidate_daily_risk_projection_research.py';PROJECTION_SHA='ed5e6eeb72b5f68d02a2712224d9816b430d82c090d60e8fc91fa4891eb6aa97'
BOUND={'inputs': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_20261003_v1\\inputs.json', 'c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'), 'inputs_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_20261003_v1\\publication.json', '64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940'), 'inputs_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_independent_readback_20261003_v1\\independent_readback.json', '8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb'), 'inputs_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_account_inputs_independent_readback_20261003.py', '85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d'), 'execution': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_20261003_v1\\result.json', 'c79aafa533d78be14f888cd109d9942702c829c39d5ce0d09904501b5c812870'), 'execution_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_20261003_v1\\publication.json', 'e1b00c1c1f8e4b4d31893e77ba46bc12009ba3e5fd452fdca1b1b01266ab68c7'), 'execution_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_independent_readback_20261003_v1\\independent_readback.json', '33ebcb571c81793f92070c8db789b409b98eca139778c0c192c80fa6abcc74bb'), 'execution_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_account_execution_independent_readback_20261003.py', '69c54a144ca582a8537a4c52b0fbb6fdf61a0f2ece0d4233206cc87f6f729ca2')}
FLAGS=dict.fromkeys(('original_saved_risk','order_gate_evaluated','account_executed','point_in_time_verified','promotion_allowed','historical_label_validity_verified','source_bytes_authenticated','automatic_retry_allowed'),False)


def module(path,sha,dependencies=None):
    if type(sha)is not str or len(sha)!=64 or set(sha)-set('0123456789abcdef'):raise ValueError('Pending immutable source pin')
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Original code SHA')
    original=builtins.__import__;dependencies=dependencies or {}
    def imports(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='backtest':
            if level or set(fromlist)-set(dependencies):raise ValueError('No unbound projection dependencies')
            return types.SimpleNamespace(**{key:dependencies[key]for key in fromlist})
        return original(name,globals,locals,fromlist,level)
    result=types.ModuleType('_saved_diagnostic_'+Path(path).stem);result.__file__=str(path)
    result.__dict__['__builtins__']={**vars(builtins),'__import__':imports}
    exec(compile(raw,str(path),'exec'),result.__dict__);return result


def run(*,execute=False):
    if execute is not True:raise ValueError('Explicit derived diagnostic publication')
    for sha in (IO_SHA,DIAGNOSTIC_SHA,PROJECTION_SHA,*(item[1]for item in BOUND.values())):
        if type(sha)is not str or len(sha)!=64 or set(sha)-set('0123456789abcdef'):raise ValueError('Pending immutable source pin')
    io=module(IO,IO_SHA);io.safe(OUTPUT);io.require(not OUTPUT.exists(),'Create-only diagnostic namespace')
    refs={key:io.reference(*value)for key,value in BOUND.items()};prepared=io.prepare(refs)
    sources=prepared['sources']
    for path,sha in ((SOURCE,LOADED),(DIAGNOSTIC,DIAGNOSTIC_SHA),(PROJECTION,PROJECTION_SHA)):
        io.load(io.reference(str(path),sha),sources,body=False)
    diagnostic=module(DIAGNOSTIC,DIAGNOSTIC_SHA)
    projection=module(PROJECTION,PROJECTION_SHA,{'ndx_saved_holdings_risk_diagnostic_research':diagnostic})
    guard=lambda:io.guard(sources,prepared['inventories'],prepared['lineage_helper'])
    guard();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        start=io.save(OUTPUT/'started.json',dict(schema='CANDIDATE_SAVED_RISK_DIAGNOSTIC_STARTED_V1',input_references=refs,source_hashes=sources,**FLAGS))
        paths=[]
        for path in prepared['paths']:
            result={key:value for key,value in path.items()if key not in ('stateful_input','daily')}
            result['projection']=projection.project_path(stateful_input=path['stateful_input'],daily=path['daily']);paths.append(result)
        numeric=sum(row['diagnostic']['metrics']is not None for path in paths for row in path['projection']['rows'])
        undefined=sum(row['diagnostic']['metrics']is None for path in paths for row in path['projection']['rows'])
        io.require(numeric==476 and undefined==4,'All 480 observed positions, four all-cash nulls')
        guard()
        result=io.save(OUTPUT/'diagnostics.json',dict(schema='CANDIDATE_SAVED_RISK_DIAGNOSTIC_DOCUMENT_V1',paths=paths,path_count=4,path_day_count=480,numeric_day_count=numeric,undefined_all_cash_day_count=undefined,
            blocked_track_indices=prepared['blocked_track_indices'],input_references=refs,source_hashes=sources,source_inventories=prepared['inventories'],started_reference=start,
            original_audit_started_references=prepared['observed_audit_started_references'],original_audit_starts_externally_anchored=False,
            derived_diagnostic_computed=True,independent_readback_status='PENDING',**FLAGS))
        guard()
        publication=io.save(OUTPUT/'publication.json',dict(schema='CANDIDATE_SAVED_RISK_DIAGNOSTIC_PUBLICATION_V1',status='PUBLISHED_DERIVED_DIAGNOSTIC_NOT_ORIGINAL_RISK_PENDING_READBACK',diagnostics_reference=result,started_reference=start,input_references=refs,source_hashes=sources,**FLAGS))
        guard()
        io.require({p.name for p in OUTPUT.iterdir()}=={'started.json','diagnostics.json','publication.json'},'Exact new diagnostic namespace')
        for item in (start,result,publication):io.require(io.sha(Path(item['path']).read_bytes())==item['sha256'],'Final saved output SHA')
        return result
    except BaseException as error:
        io.save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    print(json.dumps(run(execute=parser.parse_args().execute)))
