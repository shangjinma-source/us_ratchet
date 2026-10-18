"""Independent registered V5 gap readback; immutable publisher anchor required.

Shared capture checker validates upstream originals only. New result arithmetic
uses independent gap/CSV/prefix code; no producer kernel or parser is executed.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
from types import ModuleType,SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH=ROOT/'data/cache/research'
PRODUCER=ROOT/'scripts/ndx_registered_gap_history_runtime_20261009_v1.py'
PRODUCER_SHA='05d2a8d216aabd031c1325f8b63ce2b21b3e4020d6b23c6c131e6afb563daeed'
CURRENT={t:ROOT/'data/cache'/f'{t}.csv'for t in ('QQQ','SPY')}
REGISTRATION_CORE=(ROOT/'backtest/ndx_gap_runtime_registration_research_v1.py','6ad72acda28688cb25383bd4385da437ae7733060cb096341120178cd9e90092')
REFERENCE_CORE=(ROOT/'backtest/ndx_compact_history_runtime_registration_research_v1.py','d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')
CSV_READER=(ROOT/'backtest/ndx_capture_source_csv_independent_reconstruction_research_v1.py','c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787')
DEPENDENCIES={
 'gap_core':('backtest/ndx_prospective_gap_history_research_v5.py','11a8826b1c5f27201730afc1c482b29520fd2047115b4249fb003388f87a6592'),
 'parent_view':('backtest/ndx_prospective_history_parent_view_research_v5.py','32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373'),
 'legacy_view':('backtest/ndx_prospective_observation_parent_history_research_v4.py','06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'),
 'compact_helpers':('backtest/ndx_prospective_observation_parent_history_research.py','1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'),
 'prefix_core':('backtest/ndx_accounted_source_prefix_research_v1.py','5602376c97e654ba665ba2d4f711ee73171364a17d977cc9588ad51c385d8c9b'),
 'scoped':('backtest/ndx_forward_source_capture_scoped_research.py','9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee'),
 'base':('backtest/ndx_forward_source_capture_research.py','30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
 'capture_checker':('scripts/ndx_registered_forward_capture_independent_readback_20261009_v2.py','461cbb0d792001a4096a4c5a4caa701685b245b4989c2aa685f2c03e34ac6ca1')}
FLAGS=dict.fromkeys(('source_authenticity_verified','parent_history_authenticated_by_this_module','clock_authenticity_verified',
 'timeliness_verified','filesystem_attempt_inventory_authenticated','observation_created','candidate_seal_allowed','cohort_registration_allowed',
 'point_in_time_verified','promotion_allowed','live_mutation_allowed','future_independent_oos','production_generator_authorized','old_calendar_mutated',
 'network_quote_refresh_performed','full_transitive_source_closure_reverified','network_capture_performed','seal_event_created','partial_recovery_performed',
 'canonical_calendar_append_allowed','retrospective_backfill_allowed','decision_eligible','exchange_holidays_and_early_closes_verified'),False)
MIN_FREE=5*1024**3


INDEPENDENT_GAP=(ROOT/'backtest/ndx_gap_history_independent_reconstruction_research_v1.py','7c05552f8015af34b7eb2a215929258b0e83edc4b7ed9edaba494e45dfea8cd3')
INDEPENDENT_PREFIX=(ROOT/'backtest/ndx_accounted_source_prefix_independent_reconstruction_research_v1.py','b66bf0824971a94d0ba4f7f65ae91b7f6ed898c1977503fcdd15bf1fe38473b5')
GAP_NAMES=('started.json','history.json','publication.json','QQQ.accounted_prefix.csv','SPY.accounted_prefix.csv','QQQ.prefix_evidence.json','SPY.prefix_evidence.json')


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
    require(type(sha256) is str and len(sha256) == 64 and
            all(char in '0123456789abcdef' for char in sha256), 'Pending immutable anchor')
    return dict(path=path, sha256=sha256)


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact reference fields')
    reference(item['path'], item['sha256'])
    require(item['path'] not in sources or sources[item['path']] == item['sha256'], 'Source conflict')
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


def private_module(path,raw,expected,replacements=()):
    require(digest(raw)==expected,'Private source SHA')
    module=ModuleType('_registered_gap_'+Path(path).stem);module.__file__=str(path)
    code=raw.decode('utf-8-sig')
    for line,name,value in replacements:
        require(code.count(line)==1,'Explicit private import')
        code=code.replace(line,'');module.__dict__[name]=value
    exec(compile(code,str(path),'exec'),module.__dict__)
    return module


def exact(left,right):require(encode(left)==encode(right),'Independent exact value mismatch')


def configured():return {role:reference(str(ROOT/path),sha)for role,(path,sha)in DEPENDENCIES.items()}


def private_checkers(raw,independent_raw,csv_raw):
    """Compile only shared parent inspectors and independent reconstruction code."""
    helper=private_module(ROOT/DEPENDENCIES['compact_helpers'][0],raw['compact_helpers'],DEPENDENCIES['compact_helpers'][1])
    legacy=private_module(ROOT/DEPENDENCIES['legacy_view'][0],raw['legacy_view'],DEPENDENCIES['legacy_view'][1],[
        ('from backtest import ndx_prospective_observation_parent_history_research as compact','compact',helper)])
    parent=private_module(ROOT/DEPENDENCIES['parent_view'][0],raw['parent_view'],DEPENDENCIES['parent_view'][1],[
        ('from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy','legacy',legacy)])
    checker=private_module(ROOT/DEPENDENCIES['capture_checker'][0],raw['capture_checker'],DEPENDENCIES['capture_checker'][1])
    prefix=private_module(INDEPENDENT_PREFIX[0],independent_raw['prefix'],INDEPENDENT_PREFIX[1])
    gap=private_module(INDEPENDENT_GAP[0],independent_raw['gap'],INDEPENDENT_GAP[1])
    csv=private_module(CSV_READER[0],csv_raw,CSV_READER[1])
    expected=dict(parent_view=DEPENDENCIES['parent_view'][1],csv_reader=CSV_READER[1],independent_prefix=INDEPENDENT_PREFIX[1])
    exact(gap.DEPENDENCY_SHA256,expected)
    for role in ('parent_view','legacy_view','compact_helpers','scoped','base'):exact(checker.DEPENDENCIES[role],DEPENDENCIES[role])
    require(checker.PREFIX_CORE==(ROOT/DEPENDENCIES['prefix_core'][0],DEPENDENCIES['prefix_core'][1]),'Shared prefix source role')
    require(checker.GAP_CORE==(ROOT/DEPENDENCIES['gap_core'][0],DEPENDENCIES['gap_core'][1]),'Shared gap source role')
    require(checker.CSV_READER==CSV_READER,'Shared CSV host binding')
    require(checker.PRODUCER==ROOT/'scripts/ndx_registered_forward_capture_runtime_20261009_v2.py','Shared capture producer host path')
    exact(checker.PRODUCER_SHA,'915fda6119f9ba1ce4e966a6557c18e2d0840dd7f40269dadc22bf2fd30b530f')
    return dict(parent=parent,capture=checker,prefix=prefix,gap=gap,csv=csv)


def inventory_guard(sources,inventories,checker,gap_folder):
    for kind,refs in inventories:
        if kind=='parent':checker.parent_inventories(refs,{})
        else:
            namespace(Path(refs['reference']['path']).parent,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
            namespace(Path(refs['readback_reference']['path']).parent,('started.json','independent_readback.json'))
    namespace(gap_folder,GAP_NAMES)
    for path,sha in list(sources.items()):consume(reference(path,sha),{})


def counts(history):
    fields=('parent_typed_row_count','parent_actual_observation_count','typed_row_count','observation_count','gap_count',
        'new_observation_count','new_missed_observation_count','last_observed_session','last_accounted_session','first_actual_observed_session_by_month')
    return dict({key:deepcopy(history[key])for key in fields},pending_source_session_count=len(history['pending_source_sessions']),
        excluded_not_completed_source_session_count=len(history['excluded_not_completed_source_sessions']))


def observed(path,sources):
    path=safe(path);require(path.is_file()and path.stat().st_size<=64*1024**2 and not(path.parent/'failure.json').exists(),'Bounded nonfailed observed artifact')
    raw=path.read_bytes();ref=reference(str(path),digest(raw));consume(ref,sources)
    return ref,raw


def readback(*,registration_path,registration_sha256,history_reference,publication_reference,output_directory,execute=False):
    require(type(execute)is bool,'Explicit execution bool')
    if not execute:return dict(status='NOT_EXECUTED')
    # Validate all trusted/passed pending references before source reads.
    producer=reference(str(PRODUCER),PRODUCER_SHA);deps=configured()
    regref=reference(str(REGISTRATION_CORE[0]),REGISTRATION_CORE[1]);refref=reference(str(REFERENCE_CORE[0]),REFERENCE_CORE[1])
    registration_ref=reference(str(registration_path),registration_sha256);csvref=reference(str(CSV_READER[0]),CSV_READER[1])
    gapref=reference(str(INDEPENDENT_GAP[0]),INDEPENDENT_GAP[1]);prefixref=reference(str(INDEPENDENT_PREFIX[0]),INDEPENDENT_PREFIX[1])
    merge({},history_reference);merge({},publication_reference)
    initial={};consume(producer,initial)
    refs=private_module(REFERENCE_CORE[0],consume(refref,initial),REFERENCE_CORE[1])
    reg=private_module(REGISTRATION_CORE[0],consume(regref,initial),REGISTRATION_CORE[1],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',refs)])
    exact(reg.REFERENCE_KERNEL_SHA256,REFERENCE_CORE[1])
    registration=decode(consume(registration_ref,initial));registered=reg.prepare_gap_runtime(registration=registration,registration_reference=registration_ref,
        runtime_reference=producer,dependency_references=deps,research_root=str(RESEARCH))
    folder=safe(registered['output_directory']);output=safe(output_directory)
    out=refs.canonical_path(str(output));require(out.parent==refs.canonical_path(str(RESEARCH))and
        out!=refs.canonical_path(str(folder))and not output.exists(),'Independent create-only namespace')
    require(re.fullmatch('[a-z][a-z0-9_]{2,119}',out.name)is not None,'Stable readback namespace')
    exact(history_reference['path'],str(folder/'history.json'));exact(publication_reference['path'],str(folder/'publication.json'))
    raw={role:consume(item,initial)for role,item in deps.items()}
    independent_sources={}
    independent_raw=dict(gap=consume(gapref,independent_sources),prefix=consume(prefixref,independent_sources))
    csv_raw=consume(csvref,initial)
    modules=private_checkers(raw,independent_raw,csv_raw);checker=modules['capture'];checker.CURRENT=CURRENT
    parent=checker.load_parent_envelope(registered['parent'],initial);view=modules['parent'].inspect_parent_history_v5(parent)
    # Adapter uses independent prefix arithmetic for shared upstream verification too.
    prefix_adapter=SimpleNamespace(derive_accounted_prefix=modules['prefix'].reconstruct_accounted_prefix)
    inventories=checker.verify_parent_chain(parent,modules['parent'],prefix_adapter,modules['csv'].csv_rows,initial)
    capture_refs=registered['capture'];capture=decode(consume(capture_refs['reference'],initial))
    require(capture.get('schema')=='SOURCE_BOUND_FORWARD_CAPTURE_V5'and capture.get('plan',{}).get('schema')=='FORWARD_PARENT_CAPTURE_PLAN_V5','Current true registered V5 capture')
    bridge=dict(capture_references=capture_refs,parent_references=registered['parent'],capture_started_at=capture['capture_started_at'],
        capture_completed_at=capture['capture_completed_at'],full_capture_source_references={t:capture['captured_artifacts'][t]for t in ('QQQ','SPY')},
        source_evidence=capture['plan']['source_evidence'],tzif_reference=capture['captured_artifacts']['tzif'])
    checker.verify_prior_capture(bridge,parent,modules['parent'],modules['csv'].csv_rows,initial);inventories.append(('capture',capture_refs))
    exact(capture_refs['reader_reference'],deps['capture_checker'])
    exact(capture['input_references']['runtime'],reference(str(checker.PRODUCER),checker.PRODUCER_SHA))
    source_refs=bridge['full_capture_source_references'];source_bytes={t:consume(source_refs[t],initial)for t in ('QQQ','SPY')}
    old={t:consume(view['accounted_baseline_references'][t],initial)for t in ('QQQ','SPY')}
    actual={t:consume(view['baseline_references'][t],initial)for t in ('QQQ','SPY')}
    tzref=bridge['tzif_reference'];tz=consume(tzref,initial)
    inputs=dict(parent=registered['parent'],capture=capture_refs,registration=registration_ref,runtime=producer,dependencies=deps,
        registration_core=regref,reference_core=refref,csv_reader=csvref)
    publisher_initial=deepcopy(initial)
    sources=deepcopy(initial)
    for path,sha in independent_sources.items():merge(sources,reference(path,sha))
    consume(reference(str(SOURCE),LOADED_SHA),sources)
    d_raw=consume(history_reference,sources);p_raw=consume(publication_reference,sources);d=decode(d_raw);p=decode(p_raw)
    prefixes={};evidences={};prefixes_raw={};evidences_raw={}
    for ticker in ('QQQ','SPY'):
        prefixes[ticker],prefixes_raw[ticker]=observed(folder/(ticker+'.accounted_prefix.csv'),sources)
        evidences[ticker],evidences_raw[ticker]=observed(folder/(ticker+'.prefix_evidence.json'),sources)
    expected=modules['gap'].reconstruct_gap_history(parent=parent,capture_references=capture_refs,source_bytes=source_bytes,source_references=source_refs,
        accounted_baseline_bytes=old,actual_baseline_bytes=actual,prefix_references=prefixes,prefix_evidence_references=evidences,
        capture_started_at=bridge['capture_started_at'],capture_completed_at=bridge['capture_completed_at'],tzif_bytes=tz,tzif_reference=tzref,
        parent_checker=modules['parent'],csv_rows=modules['csv'].csv_rows,prefix_checker=modules['prefix'])
    for ticker in ('QQQ','SPY'):
        prefix,evidence=modules['prefix'].reconstruct_accounted_prefix(source_bytes=source_bytes[ticker],source_reference=source_refs[ticker],
            accounted_sessions=[row['session']for row in expected['known_typed_rows']],scope_start=expected['known_typed_rows'][0]['session'])
        require(prefixes_raw[ticker]==prefix and evidences_raw[ticker]==encode(evidence)+b'\n','Exact independent prefix/evidence saved bytes')
    started,start_raw=observed(folder/'started.json',sources)
    expected_start=dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V5',input_references=inputs,source_hashes=publisher_initial,retry_allowed=False,
        shared_upstream_capture_checker_reference=deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,
        current_live_cache_read_or_reverified=False,**FLAGS)
    require(start_raw==encode(expected_start),'Complete canonical publisher START bytes')
    published_sources=deepcopy(publisher_initial)
    for item in (started,*prefixes.values(),*evidences.values()):merge(published_sources,item)
    wrapper=dict(schema=modules['parent'].WRAPPER_SCHEMA,history=expected,input_references=inputs,source_hashes=published_sources,
        shared_upstream_capture_checker_reference=deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,
        current_live_cache_read_or_reverified=False,**FLAGS)
    publication=dict(schema=modules['parent'].PUBLICATION_SCHEMA,status=modules['parent'].PUBLICATION_STATUS,history_reference=history_reference,
        input_references=inputs,source_hashes=published_sources,**FLAGS)
    require(d_raw==encode(wrapper)and p_raw==encode(publication),'Complete independently reconstructed publication bytes')
    # Check all source aliases before creating the independent namespace.
    for path in sources:
        value=refs.canonical_path(path);require(value!=out and out not in value.parents,'Readback aliases input')
    def final_guard():inventory_guard(sources,inventories,checker,folder)
    final_guard();resource_gate(output.anchor);output.mkdir(parents=True,exist_ok=False)
    try:
        own_start=save(output/'started.json',dict(schema='PROSPECTIVE_GAP_HISTORY_READBACK_STARTED_V5',history_reference=history_reference,
            publication_reference=publication_reference,registration_reference=registration_ref,reader_sha256=LOADED_SHA,**FLAGS))
        report=save(output/'independent_readback.json',dict(schema='PROSPECTIVE_GAP_HISTORY_INDEPENDENT_READBACK_V5',status='PURE_GAP_HISTORY_READBACK_PASS',
            history_reference=history_reference,publication_reference=publication_reference,reader_sha256=LOADED_SHA,input_references=inputs,
            source_hashes=sources,counts=counts(expected),entire_history_independently_reconstructed=True,publisher_called=False,new_pure_called=False,
            producer_prefix_core_called=False,producer_scoped_parser_called=False,current_live_cache_read_or_reverified=False,snapshot_bytes_verified=True,
            independent_gap_reconstructor_reference=gapref,independent_prefix_reconstructor_reference=prefixref,csv_reader_reference=csvref,
            shared_upstream_capture_checker_reference=deps['capture_checker'],shared_upstream_checker_called=True,capture_readback_called=False,
            publisher_started_reference_observed_not_external_anchor=started,publisher_started_externally_authenticated=False,
            reconstruction_scope='INDEPENDENT_ENTIRE_GAP_RESULT_AND_PREFIX_BYTES_SHARED_UPSTREAM_CAPTURE_CHECKER_NO_SOURCE_OR_CLOCK_AUTHENTICATION',**FLAGS))
        final_guard();consume(own_start,{});consume(report,{});namespace(output,('started.json','independent_readback.json'))
        return report
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration-path','registration-sha256','history-path','history-sha256','publication-path','publication-sha256','output-directory'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(readback(registration_path=args.registration_path,registration_sha256=args.registration_sha256,
        history_reference=reference(args.history_path,args.history_sha256),publication_reference=reference(args.publication_path,args.publication_sha256),
        output_directory=args.output_directory,execute=args.execute)))
