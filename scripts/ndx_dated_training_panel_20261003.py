"""Source-bound 2026-03-20 typed preparation only; no fitter or raw audit."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_training_panel_research.py';CORE_SHA='67c2c2a950d56bc3238f77479b08909077613bca8a6809963470302eba9f616b'
OUTPUT=ROOT/'data/cache/research/dated_training_panel_20261003_v1'
BOUND={
'channels':('data/cache/research/bulk_long_window_channels_20261003_v1/channels.json','0f13e2cca5979608d742bfe1bf7a04c46ee9ca4396e5f45f22741420ee540516'),
'channels_publication':('data/cache/research/bulk_long_window_channels_20261003_v1/publication.json','b6c172eb6916361e9a701b8aed31f0caacb7161d6fdf1056d6c6127183343731'),
'channels_readback':('DYNAMIC_BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_20261003.json','3b7b35a3574757c9cdd12c74e701366979e490f5aadebcf0019da97349f4da65'),
'channels_reader':('scripts/ndx_bulk_long_window_channels_independent_review_20261003.py','7227e3705b12782c9514d39df7b23f12b1ae10e8da775f7364796d7c83ddcc99'),
'parent_panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
}
FLAGS=dict.fromkeys(('fit_performed','old_audit_repeated','raw_prices_reconstructed','point_in_time_verified','promotion_allowed','execution_authorized','legal_training_input_admitted','historical_liquidity_qualified','historical_pool_eligibility_verified','identity_interval_extended','evaluation_values_in_fit_payload','old_task_weights_reused','future_independent_oos','untouched_holdout','full_transitive_source_closure_reverified','runtime_binary_closure_verified'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def exact(a,b,message):require(encode(a)==encode(b),message)


def loads(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def reject(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=reject)


def runtime():return dict(python=sys.version,executable=str(Path(sys.executable).resolve()),implementation=platform.python_implementation(),platform=platform.platform(),float_mantissa_bits=sys.float_info.mant_dig)


def project_inputs(docs,refs):
    source=docs['channels'];pub=docs['channels_publication'];audit=docs['channels_readback'];parent=docs['parent_panel']
    require(pub['schema']=='BULK_LONG_WINDOW_CHANNELS_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_INDEPENDENT_READBACK','Source publication status')
    exact(pub['channels_reference'],refs['channels'],'Source publication reference');exact(pub['source_hashes'],source['source_hashes'],'Source publication hashes')
    require(audit['schema']=='BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['channels_sha256']==refs['channels']['sha256'] and audit['publication_sha256']==refs['channels_publication']['sha256'] and audit['reader_sha256']==refs['channels_reader']['sha256'],'Independent readback references')
    for key,value in dict(security_count=77,issuer_count=76,training_return_rows=9702,evaluation_return_rows=9702,original_provenance_count=101,preserved_sidecar_count=7).items():require(type(audit[key]) is int and audit[key]==value,'Full readback scope')
    for item in (source,pub,audit):
        require(item['point_in_time_verified'] is False and item['legal_training_input_admitted'] is False and item['fit_performed'] is False,'No source admission')
    require(parent['schema']=='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and parent['panel']['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1','Parent panel schema')
    universe=parent['panel']['universe'];coordinates=[dict(zip(universe['columns'],r)) for r in universe['data']]
    exact([r['coordinate'] for r in source['rows']],coordinates,'Original77 coordinates, including excluded late MDV')
    exact(source['original_provenance_and_missing'],parent['panel']['observed_provenance_and_missing'],'Original101 gaps')
    for name,value in source['preserved_evidence_sidecars'].items():exact(value,parent[name],'Original sidecar unchanged')
    audits={r['ticker']:r for r in audit['per_channel']};require(len(audit['per_channel'])==len(audits)==77,'Unique77 independent rows')
    for row in source['rows']:
        channel=row['channel'];proof=audits[channel['ticker']]
        for key in ('raw_reference','receipt_reference','quote_rows_sha256','training_returns_sha256','evaluation_returns_sha256'):exact(channel[key],proof[key],'Independently read numeric payload binding')
    return dict(channels_document=source,channels_reference=deepcopy(refs['channels']),independent_readback_reference=deepcopy(refs['channels_readback']),parent_panel_reference=deepcopy(refs['parent_panel']))


def guard(sources,expected_runtime):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift');exact(runtime(),expected_runtime,'Runtime drift')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Direct source drift: '+path)


def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64,'Reviewed core pin required')
    docs={};refs={};sources={str(SOURCE):LOADED_SHA};run=runtime()
    for role,(relative,h) in BOUND.items():
        p=(ROOT/relative).resolve();raw=p.read_bytes();require(sha(raw)==h,'Hard source bytes differ');require(str(p) not in sources or sources[str(p)]==h,'Source hash conflict');sources[str(p)]=h;refs[role]=dict(path=str(p),sha256=h)
        if role!='channels_reader':docs[role]=loads(raw)
    folder=Path(refs['channels']['path']).parent;require({p.name for p in folder.iterdir()}=={'started.json','channels.json','publication.json'},'Source namespace incomplete/failed/unexpected')
    corebytes=CORE.read_bytes();require(sha(corebytes)==CORE_SHA,'Pure source pin');sources[str(CORE)]=CORE_SHA;guard(sources,run)
    core=types.ModuleType('_fresh_dated_training_core');core.__file__=str(CORE);exec(compile(corebytes,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,run,core


def validate_result(panel,args):
    require(panel['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_V1' and panel['fit_payload']['cutoff']=='2026-03-20','New dated payload')
    frame=panel['fit_payload']['returns'];require(len(frame['data'])==len(frame['index'])==126 and frame['index'][-1]=='2026-03-20T00:00:00' and len(frame['columns'])==77,'Strict126x77 fit payload')
    require(all(panel[k] is False for k in ('point_in_time_verified','execution_authorized','legal_training_input_admitted','fit_performed','evaluation_values_in_fit_payload','old_task_weights_reused','liquidity_qualification_at_training_cutoff_verified')),'Typed authority')
    exact(panel['original_coordinate_evidence'],[r['coordinate'] for r in args['channels_document']['rows']],'All original coordinates');exact(panel['preserved_evidence_sidecars'],args['channels_document']['preserved_evidence_sidecars'],'All seven sidecars')
    require(panel['content_sha256']==sha(encode({k:v for k,v in panel.items() if k!='content_sha256'})),'Panel content digest')


def save(path,value):
    blob=encode(value)
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Written bytes differ');return dict(path=str(path),sha256=sha(blob))


def run(*,execute=False):
    require(type(execute) is bool,'Exact execute boolean');require(not OUTPUT.exists(),'Immutable output already exists')
    if not execute:return dict(status='NOT_EXECUTED',output=str(OUTPUT))
    docs,refs,sources,run_runtime,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,runtime=run_runtime,retry_allowed=False,**FLAGS))
        args=project_inputs(docs,refs);panel=core.prepare_dated_training_panel(**args);validate_result(panel,args)
        value=dict(schema='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1',panel=panel,input_references=refs,source_hashes=sources,runtime=run_runtime,parent_source_hashes_preserved=deepcopy(docs['channels']['source_hashes']),historical_retrospective_only=True,**FLAGS)
        guard(sources,run_runtime);out=save(OUTPUT/'panel.json',value);guard(sources,run_runtime)
        pub=save(OUTPUT/'publication.json',dict(schema='DATED_CONDITIONAL_TRAINING_PANEL_PUBLICATION_V1',status='PUBLISHED_TRAINING_PAYLOAD_NOT_FITTED',panel_reference=out,source_hashes=sources,runtime=run_runtime,**FLAGS));guard(sources,run_runtime)
        require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(pub['path']).read_bytes())==pub['sha256'],'Final byte readback');require({p.name for p in OUTPUT.iterdir()}=={'started.json','panel.json','publication.json'},'Unexpected output entry')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),retry_allowed=False));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
