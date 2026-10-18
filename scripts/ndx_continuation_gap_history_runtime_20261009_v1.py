"""Host-bound continuation gap publisher; original gap arithmetic and full ancestor replay.

The shared reader verifies original ancestors; this producer calls only its
original capture business kernel and never creates an observation.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from pathlib import PureWindowsPath
import re
import shutil
from datetime import datetime, timezone
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH = ROOT / 'data/cache/research'
REGISTRATION_CORE = (ROOT / 'backtest/ndx_gap_runtime_registration_research_v1.py', '6ad72acda28688cb25383bd4385da437ae7733060cb096341120178cd9e90092')
PREFIX_CORE = (ROOT / 'backtest/ndx_accounted_source_prefix_research_v1.py', '5602376c97e654ba665ba2d4f711ee73171364a17d977cc9588ad51c385d8c9b')
GAP_CORE = (ROOT / 'backtest/ndx_prospective_gap_history_research_v5.py', '11a8826b1c5f27201730afc1c482b29520fd2047115b4249fb003388f87a6592')
MAX_PARENT_DEPTH = 128
CSV_READER = (ROOT / 'backtest/ndx_capture_source_csv_independent_reconstruction_research_v1.py', 'c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787')
REFERENCE_CORE = (ROOT / 'backtest/ndx_compact_history_runtime_registration_research_v1.py',
    'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
DEPENDENCIES={
 'gap_core':('backtest/ndx_prospective_gap_history_research_v5.py','11a8826b1c5f27201730afc1c482b29520fd2047115b4249fb003388f87a6592'),
 'parent_view':('backtest/ndx_prospective_history_parent_view_research_v5.py','32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373'),
 'legacy_view':('backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'compact_helpers':('backtest/ndx_prospective_observation_parent_history_research.py','1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
 'prefix_core':('backtest/ndx_accounted_source_prefix_research_v1.py','5602376c97e654ba665ba2d4f711ee73171364a17d977cc9588ad51c385d8c9b'),
 'scoped':('backtest/ndx_forward_source_capture_scoped_research.py','9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'),
 'base':('backtest/ndx_forward_source_capture_research.py','30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
 'capture_checker':('scripts/ndx_registered_forward_capture_independent_readback_20261009_v2.py','461cbb0d792001a4096a4c5a4caa701685b245b4989c2aa685f2c03e34ac6ca1')}
CURRENT = {ticker: ROOT / 'data/cache' / (ticker + '.csv') for ticker in ('QQQ', 'SPY')}
FLAGS = dict.fromkeys((
    'source_authenticity_verified', 'parent_history_authenticated_by_this_module',
    'clock_authenticity_verified', 'timeliness_verified',
    'filesystem_attempt_inventory_authenticated', 'observation_created',
    'candidate_seal_allowed', 'cohort_registration_allowed', 'point_in_time_verified',
    'promotion_allowed', 'live_mutation_allowed', 'future_independent_oos',
    'production_generator_authorized', 'old_calendar_mutated',
    'network_quote_refresh_performed', 'full_transitive_source_closure_reverified',
    'network_capture_performed', 'seal_event_created', 'partial_recovery_performed',
    'canonical_calendar_append_allowed', 'retrospective_backfill_allowed',
    'decision_eligible', 'exchange_holidays_and_early_closes_verified',
), False)
MIN_FREE = 5 * 1024**3



PAIR_BINDING_CORE = (ROOT / 'backtest/ndx_compact_implementation_pair_binding_research_v1.py', 'dde8b681612d2b4fc0993bb9b697dcefb0222036d3e1bb6f4aa5f2dd76d7e4ad')
CONSUMER_REGISTRY_CORE = (ROOT / 'backtest/ndx_continuation_consumer_role_registry_research_v1.py', '184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b')
CONSUMER_METADATA_CORE = (ROOT / 'backtest/ndx_continuation_consumer_metadata_research_v1.py', 'b0d16b1b364d2c32e55d826c1f9d63dfffeb27df7bcabfe972efd029e8e2fdeb')
ANCESTRY_CONTRACT = (ROOT / 'backtest/ndx_compact_ancestry_contract_research_v2.py', '081ba024fa997c37c1f030fcec7d4d22ca6411eec652d15a5049b57d62a31a76')
LEGACY_ANCESTRY_CONTRACT = (ROOT / 'backtest/ndx_compact_ancestry_contract_research_v1.py', '1f50f4d5a893c163149bf69593880f73a1387293ee04b2ab9c0fcbb58090fc5e')
# Root binds the reviewed final R2 bytes once the optional-C IO source is frozen.
SHARED_ANCESTRY_VERIFIER = (ROOT / 'scripts/ndx_registered_compact_history_independent_readback_20261009_v2.py', '5ceec753c972ecb5047311331285e5c7ec0ec67c361709f51ba101584498dddf')
CONSUMER_ROLE = 'gap_publisher'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON ' + value)))


def reference(path, sha256):
    require(type(path) is str and path and path.strip() == path, 'Exact reference path')
    canonical_path(path)
    require(type(sha256) is str and len(sha256) == 64 and
            all(char in '0123456789abcdef' for char in sha256), 'Pending immutable anchor')
    return dict(path=path, sha256=sha256)


def canonical_path(value):
    path = PureWindowsPath(value)
    require(path.is_absolute() and re.fullmatch(r'[A-Za-z]:', path.drive) is not None,
        'Absolute local drive path')
    require(not any(part in ('.', '..') for part in value.replace('\\', '/').split('/')),
        'No relative path components')
    reserved = {'con', 'prn', 'aux', 'nul', *('com' + str(i) for i in range(1, 10)),
        *('lpt' + str(i) for i in range(1, 10))}
    for part in path.parts[1:]:
        require(not any(ord(char) < 32 or char in '<>:"|?*' for char in part)
            and not part.endswith((' ', '.')) and part.split('.')[0].casefold() not in reserved,
            'No ambiguous Windows source path')
    return str(path).casefold()


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact reference fields')
    reference(item['path'], item['sha256'])
    require(item['path'] not in sources or sources[item['path']] == item['sha256'], 'Source conflict')
    identity = canonical_path(item['path'])
    require(all(canonical_path(path) != identity or path == item['path']
        for path in sources), 'No source path spelling aliases')
    sources[item['path']] = item['sha256']


def safe(path):
    path = Path(path)
    require(path.is_absolute(), 'Absolute source/output path')
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink() and not getattr(ancestor, 'is_junction', lambda: False)(),
                'Linked source/output forbidden')
    return path


def consume(item, sources, *, allow_current=False):
    merge(sources, item)
    path = safe(item['path'])
    mutable = {value.resolve() for value in CURRENT.values()} | {
        (ROOT / 'data/cache' / (ticker + '.csv')).resolve() for ticker in ('QQQ', 'SPY')}
    require(allow_current or path.resolve() not in mutable, 'Mutable cache excluded before immutable source read')
    require(path.is_file() and path.stat().st_size <= 64 * 1024**2, 'Bounded regular source')
    require(not (path.parent / 'failure.json').exists(), 'Failed source namespace')
    raw = path.read_bytes()
    require(digest(raw) == item['sha256'], 'Source SHA changed')
    return raw


def namespace(folder, names):
    items = list(safe(folder).iterdir())
    require({item.name for item in items} == set(names), 'Exact namespace inventory')
    require(all(safe(item).is_file() for item in items), 'Regular namespace files')


def configured(bound):
    return {key: reference(str(ROOT / path), sha256) for key, (path, sha256) in bound.items()}


def compile_private(path, raw, expected, replacements=()):
    require(digest(raw)==expected, 'Private dependency SHA')
    module=ModuleType('_registered_capture_'+Path(path).stem);module.__file__=str(path)
    code=raw.decode('utf-8-sig')
    for line,attribute,value in replacements:
        require(code.count(line)==1, 'Explicit private dependency import')
        code=code.replace(line,'');module.__dict__[attribute]=value
    exec(compile(code,str(path),'exec'),module.__dict__)
    return module


def private_core(raw):
    modules={}
    for role in ('base','scoped','compact_helpers','legacy_view','parent_view','prefix_core','gap_core','capture_checker'):
        substitutions=[]
        if role=='scoped':substitutions=[('from backtest import ndx_forward_source_capture_research as capture','capture',modules['base'])]
        if role=='legacy_view':substitutions=[('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',modules['compact_helpers'])]
        if role=='parent_view':substitutions=[('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy','legacy',modules['legacy_view'])]
        if role=='prefix_core':substitutions=[('from backtest import ndx_forward_source_capture_scoped_research as scoped_parser','scoped_parser',modules['scoped'])]
        if role=='gap_core':substitutions=[
            ('from backtest import ndx_accounted_source_prefix_research_v1 as prefix_core','prefix_core',modules['prefix_core']),
            ('from backtest import ndx_forward_source_capture_scoped_research as scoped_parser','scoped_parser',modules['scoped']),
            ('from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view','parent_view',modules['parent_view']),
            ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',modules['compact_helpers'])]
        path,expected=DEPENDENCIES[role]
        modules[role]=compile_private(ROOT/path,raw[role],expected,substitutions)
    checker=modules['capture_checker']
    for role in ('parent_view','legacy_view','compact_helpers','scoped','base'):
        require(checker.DEPENDENCIES[role]==DEPENDENCIES[role],'Shared checker host dependency '+role)
    require(checker.DEPENDENCIES['capture_core']==('backtest/ndx_forward_parent_capture_research_v5.py',
        'ddd570ab3a79832ef6d530693ade9ac37b8f82c18b13efe322558099a04a7e5e'),'Shared checker current capture core host binding')
    require(checker.REGISTRATION_CORE==(ROOT/'backtest/ndx_forward_capture_runtime_registration_research_v2.py',
        'fc907ddff33988b3f3e29f4585c32ae7b2e743ea9f6abe29055772ce0f0876cd') and
        checker.REFERENCE_CORE==REFERENCE_CORE,'Shared checker registration host bindings')
    require(checker.PREFIX_CORE==(ROOT/DEPENDENCIES['prefix_core'][0],DEPENDENCIES['prefix_core'][1]) and
        checker.GAP_CORE==(ROOT/DEPENDENCIES['gap_core'][0],DEPENDENCIES['gap_core'][1]) and checker.CSV_READER==CSV_READER,'Shared checker prefix/gap/CSV host bindings')
    reference(str(checker.PRODUCER),checker.PRODUCER_SHA)
    require(checker.PRODUCER==ROOT/'scripts/ndx_registered_forward_capture_runtime_20261009_v2.py','Shared checker capture producer host path')
    return modules


def resource_gate(anchor,size=0):
    require(type(size) is int and size >= 0, 'Exact nonnegative reserve')
    require(shutil.disk_usage(Path(anchor)).free >= MIN_FREE + size, 'RESOURCE_STOP_BEFORE_WRITE')


def save_bytes(path, raw):
    if path.name != 'failure.json':
        resource_gate(path.anchor,len(raw))
    with safe(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'Complete output write')
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Durable saved bytes')
    return reference(str(path), digest(raw))


def save(path, value):
    return save_bytes(path, encode(value))


def host_modules(sources, refs):
    """Privately load pinned metadata kernels; no artifact chooses code."""
    refcore = compile_private(REFERENCE_CORE[0], consume(refs['reference_core'], sources), REFERENCE_CORE[1])
    consumer = compile_private(CONSUMER_REGISTRY_CORE[0], consume(refs['consumer_registry_core'], sources),
        CONSUMER_REGISTRY_CORE[1], [
            ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references', 'references', refcore)])
    metadata = compile_private(CONSUMER_METADATA_CORE[0], consume(refs['consumer_metadata_contract'], sources),
        CONSUMER_METADATA_CORE[1], [
            ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references', 'references', refcore),
            ('from backtest import ndx_continuation_consumer_role_registry_research_v1 as consumer_registry', 'consumer_registry', consumer)])
    registration = compile_private(REGISTRATION_CORE[0], consume(refs['registration_core'], sources),
        REGISTRATION_CORE[1], [
            ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references', 'references', refcore)])
    require(registration.REFERENCE_KERNEL_SHA256 == REFERENCE_CORE[1], 'Registration reference kernel binding')
    return registration, metadata


def run(*,registration_path,registration_sha256,implementation_pair_binding_path,
        implementation_pair_binding_sha256,consumer_role_registry_path,consumer_role_registry_sha256,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    fixed={key:reference(str(value[0]),value[1])for key,value in dict(registration_core=REGISTRATION_CORE,
        reference_core=REFERENCE_CORE,pair_binding_core=PAIR_BINDING_CORE,consumer_registry_core=CONSUMER_REGISTRY_CORE,
        consumer_metadata_contract=CONSUMER_METADATA_CORE,ancestry_contract=ANCESTRY_CONTRACT,
        legacy_ancestry_contract=LEGACY_ANCESTRY_CONTRACT,shared_ancestry_verifier=SHARED_ANCESTRY_VERIFIER).items()}
    dependencies=configured(DEPENDENCIES);csvref=reference(str(CSV_READER[0]),CSV_READER[1])
    registration_ref=reference(str(registration_path),registration_sha256)
    binding_ref=reference(str(implementation_pair_binding_path),implementation_pair_binding_sha256)
    registry_ref=reference(str(consumer_role_registry_path),consumer_role_registry_sha256)
    runtime_ref=reference(str(SOURCE),LOADED_SHA)
    bootstrap={};registration_core,metadata=host_modules(bootstrap,fixed)
    shared_ref=fixed['shared_ancestry_verifier']
    shared=compile_private(shared_ref['path'],consume(shared_ref,bootstrap),shared_ref['sha256']);shared.RESEARCH=RESEARCH;shared.CURRENT=CURRENT
    family_args=dict(implementation_pair_binding_path=binding_ref['path'],implementation_pair_binding_sha256=binding_ref['sha256'],consumer_role_registry_path=registry_ref['path'],consumer_role_registry_sha256=registry_ref['sha256'],execute=True)
    family=shared.inspect_host_continuation_family(**family_args)
    context=dict(bound_pair=family['bound_pair'],consumer_registry_view=family['consumer_registry_view'],consumer_registry_core_reference=family['consumer_registry_core_reference'],metadata_contract_reference=family['consumer_metadata_contract_reference'])
    require(context['consumer_registry_view']is not None,'Explicit host consumer registry')
    require(context['bound_pair']['binding_reference']==binding_ref and context['bound_pair']['contract_reference']==fixed['ancestry_contract'] and context['bound_pair']['independent_reader_reference']==shared_ref and context['consumer_registry_view']['registry_reference']==registry_ref and context['consumer_registry_core_reference']==fixed['consumer_registry_core'] and context['metadata_contract_reference']==fixed['consumer_metadata_contract'],'Exact host family kernels')
    require(context['consumer_registry_view']['consumer_references'][CONSUMER_ROLE]==runtime_ref,'Exact gap publisher self role')
    registration=decode(consume(registration_ref,bootstrap))
    registered=registration_core.prepare_gap_runtime(registration=registration,registration_reference=registration_ref,runtime_reference=runtime_ref,dependency_references=dependencies,research_root=str(RESEARCH))
    output=safe(registered['output_directory']);require(not output.exists(),'Create-only gap namespace; no retry')
    replay=shared.verify_saved_parent_ancestry(parent_references=registered['parent'],consumer_capture_references=registered['capture'],**family_args)
    require(replay.get('status')=='READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS','Complete original ancestor and capture replay')
    require(replay['bound_pair']==context['bound_pair'] and replay['consumer_registry_view']==context['consumer_registry_view'],'Stable host family')
    parent=replay['parent_envelope'];view=replay['parent_view'];capture=replay['capture_envelope'];cap=capture['document']
    require({key:capture[key]for key in ('reference','publication_reference','readback_reference','reader_reference')}==registered['capture'],'Explicit verified capture refs')
    require(cap['parent_references']==registered['parent'],'Capture belongs to original parent')
    inputs=dict(parent=registered['parent'],capture=registered['capture'],registration=registration_ref,runtime=runtime_ref,dependencies=dependencies,registration_core=fixed['registration_core'],reference_core=fixed['reference_core'],csv_reader=csvref,
        **metadata.continuation_input_references(registered_dependency_references=dependencies,consumer_role=CONSUMER_ROLE,**context))
    metadata.inspect_producer_input_references(inputs,consumer_role=CONSUMER_ROLE,registered_dependency_references=dependencies,**context)
    sources=deepcopy(replay['sources'])
    # Only closed code-constructed public input roles may select additional IO.
    def add(value):
        if type(value)is dict:
            if set(value)=={'path','sha256'}:consume(value,sources)
            else:
                for child in value.values():add(child)
    add(inputs)
    modules=private_core({key:consume(item,sources)for key,item in dependencies.items()})
    require(modules['parent_view'].inspect_parent_history_v5(parent)==view,'Original normalized parent')
    raw={t:consume(cap['captured_artifacts'][t],sources)for t in ('QQQ','SPY')}
    source_refs={t:cap['captured_artifacts'][t]for t in ('QQQ','SPY')}
    old={t:consume(view['accounted_baseline_references'][t],sources)for t in ('QQQ','SPY')}
    actual={t:consume(view['baseline_references'][t],sources)for t in ('QQQ','SPY')}
    tzif_ref=cap['captured_artifacts']['tzif'];tzif=consume(tzif_ref,sources);core=modules['gap_core']
    zone=core.ZoneInfo.from_file(core.BytesIO(tzif),key='America/New_York')
    begin,end=core.utc(cap['capture_started_at']),core.utc(cap['capture_completed_at'])
    known=[row['session']for row in view['known_typed_rows']]
    for day in cap['plan']['source_evidence']['QQQ']['new_session_dates']:
        close,deadline=core.conservative_timing(day,zone)
        if begin>=close and begin>=deadline and end>=deadline:known.append(day)
    prefixes={};evidences={}
    for ticker in ('QQQ','SPY'):
        prefixes[ticker],evidence=modules['prefix_core'].derive_accounted_prefix(source_bytes=raw[ticker],source_reference=source_refs[ticker],accounted_sessions=known,scope_start=known[0])
        evidences[ticker]=core.prefix_evidence_bytes(evidence)
    header=metadata.expected_consumer_metadata(consumer_role=CONSUMER_ROLE,**context)
    upstream=dict(shared_upstream_capture_checker_reference=dependencies['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,current_live_cache_read_or_reverified=False)
    created={}
    def final_guard():
        family['final_guard']();replay['final_guard']()
        for path,value in sources.items():consume(reference(path,value),{})
        if output.exists():namespace(output,created)
        for item in created.values():consume(item,{})
    final_guard();resource_gate(output.anchor);output.mkdir(parents=True,exist_ok=False)
    try:
        started=save(output/'started.json',dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V5',input_references=inputs,source_hashes=deepcopy(sources),retry_allowed=False,**upstream,**header,**FLAGS));created['started.json']=started
        final_guard()
        prefix_refs={};evidence_refs={}
        for ticker in ('QQQ','SPY'):
            name=ticker+'.accounted_prefix.csv';prefix_refs[ticker]=save_bytes(output/name,prefixes[ticker]);created[name]=prefix_refs[ticker];final_guard()
            name=ticker+'.prefix_evidence.json';evidence_refs[ticker]=save_bytes(output/name,evidences[ticker]);created[name]=evidence_refs[ticker];final_guard()
        history=core.extend_gap_history(parent=parent,capture_references=registered['capture'],source_bytes=raw,source_references=source_refs,accounted_baseline_bytes=old,actual_baseline_bytes=actual,prefix_references=prefix_refs,prefix_evidence_references=evidence_refs,capture_started_at=cap['capture_started_at'],capture_completed_at=cap['capture_completed_at'],tzif_bytes=tzif,tzif_reference=tzif_ref)
        for item in (started,*prefix_refs.values(),*evidence_refs.values()):merge(sources,item)
        for path,value in history['source_hashes'].items():require(sources.get(path)==value,'Inner claims cannot choose source IO')
        final_guard()
        href=save(output/'history.json',dict(schema=modules['parent_view'].WRAPPER_SCHEMA,history=history,input_references=inputs,source_hashes=deepcopy(sources),**upstream,**header,**FLAGS));created['history.json']=href;final_guard()
        pub=save(output/'publication.json',dict(schema=modules['parent_view'].PUBLICATION_SCHEMA,status=modules['parent_view'].PUBLICATION_STATUS,history_reference=href,input_references=inputs,source_hashes=deepcopy(sources),**header,**FLAGS));created['publication.json']=pub;final_guard()
        namespace(output,metadata.NAMESPACE_FILES[CONSUMER_ROLE])
        return dict(history_reference=href,publication_reference=pub)
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**header,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration-path', 'registration-sha256', 'implementation-pair-binding-path', 'implementation-pair-binding-sha256', 'consumer-role-registry-path', 'consumer-role-registry-sha256'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true');args=vars(parser.parse_args())
    print(json.dumps(run(**args)))
