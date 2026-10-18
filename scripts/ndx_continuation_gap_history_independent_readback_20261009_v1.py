"""Host-bound independent continuation gap reconstruction.

The shared reader verifies ancestors. Capture arithmetic uses the frozen
independent 7c gap formula, b66 prefix reconstruction and c9 CSV parser; no producer algorithm executes.
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
CONSUMER_ROLE = 'gap_independent_reader'


INDEPENDENT_GAP = (ROOT / 'backtest/ndx_gap_history_independent_reconstruction_research_v1.py', '7c05552f8015af34b7eb2a215929258b0e83edc4b7ed9edaba494e45dfea8cd3')
INDEPENDENT_PREFIX = (ROOT / 'backtest/ndx_accounted_source_prefix_independent_reconstruction_research_v1.py', 'b66bf0824971a94d0ba4f7f65ae91b7f6ed898c1977503fcdd15bf1fe38473b5')
CSV_READER = (ROOT / 'backtest/ndx_capture_source_csv_independent_reconstruction_research_v1.py', 'c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787')


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


def exact(left, right, message):
    require(encode(left) == encode(right), message)


def private_parent_checker(raw):
    helper = compile_private(ROOT / DEPENDENCIES['compact_helpers'][0], raw['compact_helpers'], DEPENDENCIES['compact_helpers'][1])
    legacy = compile_private(ROOT / DEPENDENCIES['legacy_view'][0], raw['legacy_view'], DEPENDENCIES['legacy_view'][1], [
        ('from backtest import ndx_prospective_observation_parent_history_research as compact', 'compact', helper)])
    return compile_private(ROOT / DEPENDENCIES['parent_view'][0], raw['parent_view'], DEPENDENCIES['parent_view'][1], [
        ('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy', 'legacy', legacy)])


def readback(*,registration_path,registration_sha256,history_reference,publication_reference,output_directory,
        implementation_pair_binding_path,implementation_pair_binding_sha256,consumer_role_registry_path,consumer_role_registry_sha256,execute=False):
    require(type(execute)is bool,'Explicit bool')
    if not execute:return dict(status='NOT_EXECUTED')
    fixed={key:reference(str(value[0]),value[1])for key,value in dict(registration_core=REGISTRATION_CORE,reference_core=REFERENCE_CORE,pair_binding_core=PAIR_BINDING_CORE,
        consumer_registry_core=CONSUMER_REGISTRY_CORE,consumer_metadata_contract=CONSUMER_METADATA_CORE,ancestry_contract=ANCESTRY_CONTRACT,legacy_ancestry_contract=LEGACY_ANCESTRY_CONTRACT,shared_ancestry_verifier=SHARED_ANCESTRY_VERIFIER).items()}
    independent={key:reference(str(value[0]),value[1])for key,value in dict(independent_gap_reconstructor=INDEPENDENT_GAP,independent_prefix_reconstructor=INDEPENDENT_PREFIX,csv_reader=CSV_READER).items()}
    dependencies=configured(DEPENDENCIES);self_ref=reference(str(SOURCE),LOADED_SHA)
    registration_ref=reference(str(registration_path),registration_sha256);binding_ref=reference(str(implementation_pair_binding_path),implementation_pair_binding_sha256);registry_ref=reference(str(consumer_role_registry_path),consumer_role_registry_sha256)
    merge({},history_reference);merge({},publication_reference)
    output=safe(output_directory);output_key=PureWindowsPath(str(output))
    require(output_key.parent==PureWindowsPath(str(RESEARCH))and re.fullmatch(r'[a-z][a-z0-9_]{2,119}',output_key.name)is not None and not output.exists(),'Independent create-only direct namespace')
    bootstrap={};registration_core,metadata=host_modules(bootstrap,fixed)
    shared_ref=fixed['shared_ancestry_verifier'];shared=compile_private(shared_ref['path'],consume(shared_ref,bootstrap),shared_ref['sha256']);shared.RESEARCH=RESEARCH;shared.CURRENT=CURRENT
    family_args=dict(implementation_pair_binding_path=binding_ref['path'],implementation_pair_binding_sha256=binding_ref['sha256'],consumer_role_registry_path=registry_ref['path'],consumer_role_registry_sha256=registry_ref['sha256'],execute=True)
    family=shared.inspect_host_continuation_family(**family_args)
    context=dict(bound_pair=family['bound_pair'],consumer_registry_view=family['consumer_registry_view'],consumer_registry_core_reference=family['consumer_registry_core_reference'],metadata_contract_reference=family['consumer_metadata_contract_reference'])
    require(context['consumer_registry_view']is not None,'Explicit host consumer registry')
    exact(context['bound_pair']['binding_reference'],binding_ref,'Independent host binding');exact(context['bound_pair']['contract_reference'],fixed['ancestry_contract'],'Fixed ancestry contract');exact(context['bound_pair']['independent_reader_reference'],shared_ref,'Fixed shared verifier');exact(context['consumer_registry_view']['registry_reference'],registry_ref,'Independent host registry');exact(context['consumer_registry_core_reference'],fixed['consumer_registry_core'],'Fixed registry core');exact(context['metadata_contract_reference'],fixed['consumer_metadata_contract'],'Fixed metadata core')
    exact(context['consumer_registry_view']['consumer_references'][CONSUMER_ROLE],self_ref,'Exact gap independent reader self role')
    producer_ref=context['consumer_registry_view']['consumer_references']['gap_publisher']
    pubmeta=metadata.expected_consumer_metadata(consumer_role='gap_publisher',**context);readmeta=metadata.expected_consumer_metadata(consumer_role=CONSUMER_ROLE,**context)
    registered=registration_core.prepare_gap_runtime(registration=decode(consume(registration_ref,bootstrap)),registration_reference=registration_ref,runtime_reference=producer_ref,dependency_references=dependencies,research_root=str(RESEARCH))
    folder=safe(registered['output_directory']);require(folder!=output,'Distinct gap publisher/reader namespace')
    exact(history_reference['path'],str(folder/'history.json'),'Fixed history filename');exact(publication_reference['path'],str(folder/'publication.json'),'Fixed publication filename');namespace(folder,metadata.NAMESPACE_FILES['gap_publisher'])
    d=decode(consume(history_reference,{}));p=decode(consume(publication_reference,{}))
    metadata.inspect_consumer_metadata(d,expected_role='gap_publisher',**context);metadata.inspect_consumer_metadata(p,expected_role='gap_publisher',**context)
    upstream=dict(shared_upstream_capture_checker_reference=dependencies['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,current_live_cache_read_or_reverified=False)
    require(set(d)=={'schema','history','input_references','source_hashes',*upstream,*metadata.METADATA_KEYS,*FLAGS},'Closed gap wrapper before reference use')
    require(set(p)=={'schema','status','history_reference','input_references','source_hashes',*metadata.METADATA_KEYS,*FLAGS},'Closed gap publication before reference use')
    replay=shared.verify_saved_parent_ancestry(parent_references=registered['parent'],consumer_capture_references=registered['capture'],**family_args)
    require(replay.get('status')=='READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS','Complete parent/capture original replay')
    exact(replay['bound_pair'],context['bound_pair'],'Stable host pair');exact(replay['consumer_registry_view'],context['consumer_registry_view'],'Stable host registry')
    parent=replay['parent_envelope'];view=replay['parent_view'];capture=replay['capture_envelope'];cap=capture['document']
    exact({key:capture[key]for key in ('reference','publication_reference','readback_reference','reader_reference')},registered['capture'],'Explicit verified capture original refs');exact(cap['parent_references'],registered['parent'],'Capture belongs to original parent')
    inputs=dict(parent=registered['parent'],capture=registered['capture'],registration=registration_ref,runtime=producer_ref,dependencies=dependencies,registration_core=fixed['registration_core'],reference_core=fixed['reference_core'],csv_reader=independent['csv_reader'],**metadata.continuation_input_references(registered_dependency_references=dependencies,consumer_role='gap_publisher',**context))
    exact(d['input_references'],inputs,'Whole closed original public input');exact(p['input_references'],inputs,'Whole common public input')
    initial=deepcopy(replay['sources'])
    def add(value,target):
        if type(value)is dict:
            if set(value)=={'path','sha256'}:consume(value,target)
            else:
                for child in value.values():add(child,target)
    add(inputs,initial)
    raw_dependencies={key:consume(item,initial)for key,item in dependencies.items()}
    checker=private_parent_checker(raw_dependencies);exact(checker.inspect_parent_history_v5(parent),view,'Original normalized parent')
    formula=compile_private(INDEPENDENT_GAP[0],consume(independent['independent_gap_reconstructor'],{}),INDEPENDENT_GAP[1])
    prefix=compile_private(INDEPENDENT_PREFIX[0],consume(independent['independent_prefix_reconstructor'],{}),INDEPENDENT_PREFIX[1])
    csv=compile_private(CSV_READER[0],consume(independent['csv_reader'],{}),CSV_READER[1])
    source_refs={t:cap['captured_artifacts'][t]for t in ('QQQ','SPY')};raw={t:consume(source_refs[t],initial)for t in ('QQQ','SPY')}
    old={t:consume(view['accounted_baseline_references'][t],initial)for t in ('QQQ','SPY')};actual={t:consume(view['baseline_references'][t],initial)for t in ('QQQ','SPY')};tzref=cap['captured_artifacts']['tzif'];tz=consume(tzref,initial)
    # Saved prefix refs are derived from the fixed seven filenames, not from an
    # arbitrary nested metadata reference or self-reported source claim.
    def observed(name):
        path=safe(folder/name);require(path.is_file()and path.stat().st_size<=64*1024**2 and not(path.parent/'failure.json').exists(),'Bounded immutable original artifact')
        return reference(str(path),digest(path.read_bytes()))
    prefrefs={t:observed(t+'.accounted_prefix.csv')for t in ('QQQ','SPY')};evidrefs={t:observed(t+'.prefix_evidence.json')for t in ('QQQ','SPY')}
    history=formula.reconstruct_gap_history(parent=parent,capture_references=registered['capture'],source_bytes=raw,source_references=source_refs,accounted_baseline_bytes=old,actual_baseline_bytes=actual,prefix_references=prefrefs,prefix_evidence_references=evidrefs,capture_started_at=cap['capture_started_at'],capture_completed_at=cap['capture_completed_at'],tzif_bytes=tz,tzif_reference=tzref,parent_checker=checker,csv_rows=csv.csv_rows,prefix_checker=prefix)
    exact(d['history'],history,'Entire independently reconstructed history')
    for ticker in ('QQQ','SPY'):
        pref,evidence=prefix.reconstruct_accounted_prefix(source_bytes=raw[ticker],source_reference=source_refs[ticker],accounted_sessions=[row['session']for row in history['known_typed_rows']],scope_start=history['known_typed_rows'][0]['session'])
        require(consume(prefrefs[ticker],{})==pref,'Entire saved original prefix bytes');require(consume(evidrefs[ticker],{})==encode(evidence)+b'\n','Entire canonical evidence artifact bytes')
    startref=observed('started.json');exact(decode(consume(startref,{})),dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V5',input_references=inputs,source_hashes=initial,retry_allowed=False,**upstream,**pubmeta,**FLAGS),'Whole publisher START')
    published=deepcopy(initial)
    for item in (startref,*prefrefs.values(),*evidrefs.values()):consume(item,published)
    require(consume(history_reference,{})==encode(dict(schema=checker.WRAPPER_SCHEMA,history=history,input_references=inputs,source_hashes=published,**upstream,**pubmeta,**FLAGS)),'Whole canonical history wrapper bytes')
    require(consume(publication_reference,{})==encode(dict(schema=checker.PUBLICATION_SCHEMA,status=checker.PUBLICATION_STATUS,history_reference=history_reference,input_references=inputs,source_hashes=published,**pubmeta,**FLAGS)),'Whole canonical publication bytes')
    private_inputs=dict(runtime=self_ref,dependencies=dependencies,auxiliary_dependencies={},independent_dependencies=independent,registration_core=fixed['registration_core'],reference_core=fixed['reference_core'],pair_binding_core=fixed['pair_binding_core'],implementation_pair_binding=binding_ref,consumer_role_registry=registry_ref,ancestry_contract=fixed['ancestry_contract'],shared_ancestry_verifier=shared_ref,consumer_registry_core=fixed['consumer_registry_core'],consumer_metadata_contract=fixed['consumer_metadata_contract'])
    sources=deepcopy(published);add(private_inputs,sources)
    for item in (history_reference,publication_reference):consume(item,sources)
    created={}
    def final_guard():
        family['final_guard']();replay['final_guard']();namespace(folder,metadata.NAMESPACE_FILES['gap_publisher'])
        for path,value in sources.items():consume(reference(path,value),{})
        if output.exists():namespace(output,created)
        for item in created.values():consume(item,{})
    final_guard();resource_gate(output.anchor);output.mkdir(parents=True,exist_ok=False)
    try:
        own=save(output/'started.json',dict(schema='PROSPECTIVE_GAP_HISTORY_READBACK_STARTED_V5',history_reference=history_reference,publication_reference=publication_reference,registration_reference=registration_ref,reader_sha256=LOADED_SHA,input_references=inputs,reader_input_references=private_inputs,**readmeta,**FLAGS));created['started.json']=own;merge(sources,own);final_guard()
        report=save(output/'independent_readback.json',dict(schema=checker.READBACK_SCHEMA,status=checker.READBACK_STATUS,history_reference=history_reference,publication_reference=publication_reference,reader_sha256=LOADED_SHA,input_references=inputs,reader_input_references=private_inputs,source_hashes=deepcopy(sources),counts=checker.gap_counts(history),entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,producer_prefix_core_called=False,producer_scoped_parser_called=False,snapshot_bytes_verified=True,
            independent_gap_reconstructor_reference=independent['independent_gap_reconstructor'],independent_prefix_reconstructor_reference=independent['independent_prefix_reconstructor'],csv_reader_reference=independent['csv_reader'],**upstream,publisher_started_reference_observed_not_external_anchor=startref,publisher_started_externally_authenticated=False,reconstruction_scope='INDEPENDENT_ENTIRE_GAP_RESULT_AND_PREFIX_BYTES_SHARED_UPSTREAM_CAPTURE_CHECKER_NO_SOURCE_OR_CLOCK_AUTHENTICATION',reader_started_reference_observed_not_external_anchor=own,reader_started_externally_authenticated=False,**readmeta,**FLAGS));created['independent_readback.json']=report;final_guard()
        namespace(output,metadata.NAMESPACE_FILES[CONSUMER_ROLE]);return report
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**readmeta,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration-path', 'registration-sha256', 'implementation-pair-binding-path', 'implementation-pair-binding-sha256', 'consumer-role-registry-path', 'consumer-role-registry-sha256', 'history-path', 'history-sha256', 'publication-path', 'publication-sha256', 'output-directory'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true');args=vars(parser.parse_args())
    args['history_reference']=reference(args.pop('history_path'),args.pop('history_sha256'));args['publication_reference']=reference(args.pop('publication_path'),args.pop('publication_sha256'))
    print(json.dumps(readback(**args)))
