"""Create-only compact V4 publisher driven by an immutable external registration.

No real observation is created here. An independently read observation is required.
Registration kernel is pending review; this entrypoint is not executable until bound.
"""
import argparse
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH = ROOT / 'data/cache/research'
REGISTRATION_CORE = (ROOT / 'backtest/ndx_compact_history_runtime_registration_research_v1.py', 'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES = {
    'history_core': (ROOT / 'backtest/ndx_prospective_observation_parent_history_research_v4.py',
        '06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
    'compact_helpers': (ROOT / 'backtest/ndx_prospective_observation_parent_history_research.py',
        '1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
}
FLAGS = dict.fromkeys(('source_authenticity_verified','clock_authenticity_verified',
    'filesystem_attempt_inventory_authenticated','point_in_time_verified','candidate_seal_allowed',
    'cohort_registration_allowed','promotion_allowed','live_mutation_allowed','future_independent_oos',
    'observation_created','old_calendar_mutated','network_capture_performed',
    'full_transitive_source_closure_reverified'),False)


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def reference(path, digest):
    require(type(digest) is str and len(digest)==64 and set(digest)<=set('0123456789abcdef'),
        'Pending immutable anchor')
    return dict(path=str(path),sha256=digest)


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'Duplicate JSON key');result[key]=value
        return result
    def invalid(value): raise ValueError('Nonfinite JSON '+value)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def safe(path):
    path=Path(path)
    require(path.is_absolute(),'Absolute source/output path')
    for ancestor in (path,*path.parents):
        require(not ancestor.is_symlink() and not getattr(ancestor,'is_junction',lambda:False)(),
            'No linked source or output')
    return path


def consume(item,sources):
    require(type(item)is dict and set(item)=={'path','sha256'},'Exact source reference')
    reference(item['path'],item['sha256']);path=safe(item['path'])
    require(path.is_file() and path.stat().st_size<=64*1024**2,'Bounded regular source')
    require(not (path.parent/'failure.json').exists(),'Failed source namespace')
    require(path.resolve() not in {(ROOT/'data/cache'/f'{t}.csv').resolve() for t in ('QQQ','SPY')},
        'Immutable saved sources only')
    for old,digest in sources.items():
        if Path(old)==path: require(digest==item['sha256'],'Conflicting path alias')
    raw=path.read_bytes();require(sha(raw)==item['sha256'],'Source bytes changed')
    sources[str(path)]=item['sha256'];return raw


def guard(sources):
    for path,digest in list(sources.items()):consume(reference(path,digest),{})


def namespace(folder,expected,sources):
    folder=safe(folder);items=list(folder.iterdir())
    require({item.name for item in items}==set(expected),'Exact immutable namespace '+str(folder))
    for item in items:
        require(safe(item).is_file(),'Regular namespace file')
        consume(reference(item,sha(item.read_bytes())),sources)


def load_envelope(refs,roles,sources):
    result=deepcopy(refs)
    for key,role in roles:
        result[key]=decode(consume(refs[role],sources))
        claims=result[key]['source_hashes'];require(type(claims)is dict,'Complete source claim map')
        for path,digest in claims.items():consume(reference(path,digest),sources)
    consume(refs['reader_reference'],sources)
    return result


def compile_private(path,raw,injected=None,import_line=None):
    code=raw.decode('utf-8-sig');module=ModuleType('_registered_compact_'+Path(path).stem)
    module.__file__=str(path)
    if import_line is not None:
        require(code.count(import_line)==1,'One explicit private dependency import')
        code=code.replace(import_line,'')
    module.__dict__.update(injected or {})
    exec(compile(code,str(path),'exec'),module.__dict__)
    return module


def csv_scope(raw,start):
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
    require(reader.fieldnames==['Date','Open','High','Low','Close','Volume'],'Saved CSV schema')
    rows=list(reader);dates=[row['Date'] for row in rows]
    require(dates==sorted(set(dates)),'Unique ordered source sessions')
    return [day for day in dates if day>=start]


def verify_baselines(view,sources):
    known=[row['session'] for row in view['known_typed_rows']]
    actual=[row['session'] for row in view['known_typed_rows'] if row['session']<=view['last_observed_session']]
    for ticker in ('QQQ','SPY'):
        old=consume(view['baseline_references'][ticker],sources)
        accounted=consume(view['accounted_baseline_references'][ticker],sources)
        require(csv_scope(old,known[0])==actual,'Exact last actual baseline scope')
        require(csv_scope(accounted,known[0])==known,'Exact accounted baseline scope')
        require(accounted.startswith(old),'Complete last-actual byte prefix')


def save(path,value):
    raw=encode(value)
    if path.name!='failure.json':
        require(shutil.disk_usage(path.anchor).free>=5*1024**3+len(raw),'Resource stop before write')
    with safe(path).open('xb') as stream:
        require(stream.write(raw)==len(raw),'Complete write');stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Durable saved bytes')
    return reference(path,sha(raw))


def run(*,registration_path,registration_sha256,execute=False):
    require(execute is True,'Explicit compact history publication')
    # Pending/invalid configured anchors fail before any input IO.
    registration_core_ref=reference(*REGISTRATION_CORE)
    registration_ref=reference(registration_path,registration_sha256)
    dependencies={key:reference(*value) for key,value in DEPENDENCIES.items()}
    sources={};runtime_ref=reference(SOURCE,LOADED_SHA)
    consume(runtime_ref,sources)
    registration_core=compile_private(registration_core_ref['path'],consume(registration_core_ref,sources))
    registration=decode(consume(registration_ref,sources))
    plan=registration_core.prepare_compact_history_runtime(registration=registration,
        registration_reference=registration_ref,runtime_reference=runtime_ref,
        dependency_references=dependencies,research_root=str(RESEARCH))
    output=safe(plan['output_directory']);require(not output.exists(),'Create-only; no retry')
    helper_ref=dependencies['compact_helpers'];helper=compile_private(helper_ref['path'],consume(helper_ref,sources))
    core_ref=dependencies['history_core'];core=compile_private(core_ref['path'],consume(core_ref,sources),
        dict(compact=helper),'from backtest import ndx_prospective_observation_parent_history_research as compact')
    require(core.DEPENDENCY_SHA256==helper_ref['sha256'],'Exact private helper binding')
    parent=load_envelope(plan['parent'],(('document','reference'),('publication','publication_reference'),('readback','readback_reference')),sources)
    observation=load_envelope(plan['observation'],(('payload','payload_reference'),('receipt','receipt_reference'),('audit','audit_reference')),sources)
    parent_folder=Path(parent['reference']['path']).parent
    require(Path(parent['publication_reference']['path'])==parent_folder/'publication.json' and
        Path(parent['reference']['path'])==parent_folder/'history.json','Parent artifact names')
    audit_folder=Path(parent['readback_reference']['path']).parent
    same=audit_folder==parent_folder
    def inventories():
        namespace(parent_folder,{'started.json','history.json','publication.json'}|({'independent_readback.json'} if same else set()),sources)
        if not same: namespace(audit_folder,{'started.json','independent_readback.json'},sources)
        folder=Path(observation['payload_reference']['path']).parent
        for role,name in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]:
            require(Path(observation[role]['path'])==folder/name,'Observation artifact names')
        namespace(folder,{'started.json','observation_payload.json','receipt.json','independent_readback.json'},sources)
    inventories();view=core.inspect_parent_history_v4(parent);verify_baselines(view,sources)
    history=core.append_observation_history_v4(parent=parent,observation=observation)
    for path,digest in history['source_hashes'].items():consume(reference(path,digest),sources)
    # Verify independently that actual stored CSV bytes equal the embedded payload declarations.
    import base64
    for parts in observation['payload']['full_original_sources_preserved'].values():
        for part in parts.values():
            require(consume(part['reference'],sources)==base64.b64decode(part['original_csv_bytes_base64'],validate=True),
                'Saved CSV equals payload original bytes')
    guard(sources);inventories()
    require(shutil.disk_usage(output.anchor).free>=5*1024**3,'Resource stop before namespace')
    output.mkdir(parents=True,exist_ok=False)
    inputs=dict(parent=deepcopy(plan['parent']),observation=deepcopy(plan['observation']),
        registration=registration_ref,runtime=runtime_ref,dependencies=dependencies,
        registration_core=registration_core_ref)
    try:
        save(output/'started.json',dict(schema='PROSPECTIVE_OBSERVATION_HISTORY_STARTED_V4',
            input_references=inputs,source_hashes=deepcopy(sources),**FLAGS))
        history_ref=save(output/'history.json',dict(schema=core.WRAPPER_SCHEMA,history=history,
            input_references=inputs,source_hashes=deepcopy(sources),**FLAGS))
        guard(sources);inventories()
        publication_ref=save(output/'publication.json',dict(schema=core.PUBLICATION_SCHEMA,
            status=core.PUBLICATION_STATUS,history_reference=history_ref,input_references=inputs,
            counts=core.history_counts_v4(history),source_hashes=deepcopy(sources),**FLAGS))
        guard(sources);inventories()
        require({p.name for p in output.iterdir()}=={'started.json','history.json','publication.json'},'Exact output')
        require(sha((output/'history.json').read_bytes())==history_ref['sha256'] and
            sha((output/'publication.json').read_bytes())==publication_ref['sha256'],'Final publication bytes')
        return dict(history_reference=history_ref,publication_reference=publication_ref,
            independent_readback_required=True,**FLAGS)
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,
            error=str(error),automatic_retry_allowed=False,**FLAGS))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--registration-path',required=True)
    parser.add_argument('--registration-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();print(json.dumps(run(registration_path=args.registration_path,
        registration_sha256=args.registration_sha256,execute=args.execute)))
