"""Registered V5 gap publication; pending checker prevents actual execution.

Consumes immutable parent/capture receipts only. Shared upstream capture checker
validates parent originals and capture plan; only this gap runtime calls gap core.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import ModuleType

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
RESEARCH=ROOT/'data/cache/research'
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


def private_dependencies(raw):
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
        modules[role]=private_module(ROOT/path,raw[role],expected,substitutions)
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


def configured():return {role:reference(str(ROOT/path),sha)for role,(path,sha)in DEPENDENCIES.items()}


def final_guard(sources,inventories,checker):
    for role,refs in inventories:
        if role=='parent':checker.parent_inventories(refs,{})
        else:
            namespace(Path(refs['reference']['path']).parent,('started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'))
            namespace(Path(refs['readback_reference']['path']).parent,('started.json','independent_readback.json'))
    for path,sha in list(sources.items()):consume(reference(path,sha),{})


def run(*,registration_path,registration_sha256,execute=False):
    require(execute is True,'Explicit registered gap publication')
    # All pending anchors fail before filesystem reads.
    dependencies=configured();runtime=reference(str(SOURCE),LOADED_SHA)
    regref=reference(str(REGISTRATION_CORE[0]),REGISTRATION_CORE[1]);refref=reference(str(REFERENCE_CORE[0]),REFERENCE_CORE[1])
    registration_ref=reference(str(registration_path),registration_sha256);csvref=reference(str(CSV_READER[0]),CSV_READER[1])
    sources={};consume(runtime,sources)
    refs=private_module(REFERENCE_CORE[0],consume(refref,sources),REFERENCE_CORE[1])
    reg=private_module(REGISTRATION_CORE[0],consume(regref,sources),REGISTRATION_CORE[1],[
        ('from backtest import ndx_compact_history_runtime_registration_research_v1 as references','references',refs)])
    require(reg.REFERENCE_KERNEL_SHA256==REFERENCE_CORE[1],'Registration reference kernel binding')
    registration=decode(consume(registration_ref,sources))
    registered=reg.prepare_gap_runtime(registration=registration,registration_reference=registration_ref,
        runtime_reference=runtime,dependency_references=dependencies,research_root=str(RESEARCH))
    output=safe(registered['output_directory']);require(not output.exists(),'Create-only gap namespace; no retry')
    modules=private_dependencies({key:consume(item,sources)for key,item in dependencies.items()})
    checker=modules['capture_checker'];checker.CURRENT=CURRENT
    csv=private_module(CSV_READER[0],consume(csvref,sources),CSV_READER[1]).csv_rows
    parent=checker.load_parent_envelope(registered['parent'],sources)
    view=modules['parent_view'].inspect_parent_history_v5(parent)
    inventories=checker.verify_parent_chain(parent,modules['parent_view'],modules['prefix_core'],csv,sources)
    capture_refs=registered['capture']
    capture=decode(consume(capture_refs['reference'],sources))
    require(capture.get('schema')=='SOURCE_BOUND_FORWARD_CAPTURE_V5' and capture.get('plan',{}).get('schema')=='FORWARD_PARENT_CAPTURE_PLAN_V5','Current capture true registered V5 format')
    bridge=dict(capture_references=capture_refs,parent_references=registered['parent'],
        capture_started_at=capture['capture_started_at'],capture_completed_at=capture['capture_completed_at'],
        full_capture_source_references={t:capture['captured_artifacts'][t]for t in ('QQQ','SPY')},
        source_evidence=capture['plan']['source_evidence'],tzif_reference=capture['captured_artifacts']['tzif'])
    checker.verify_prior_capture(bridge,parent,modules['parent_view'],csv,sources)
    inventories.append(('capture',deepcopy(capture_refs)))
    require(capture['input_references']['runtime']==reference(str(checker.PRODUCER),checker.PRODUCER_SHA),'Capture runtime fixed host binding')
    require(capture_refs['reader_reference']==dependencies['capture_checker'],'Capture readback fixed host binding')
    source_refs=bridge['full_capture_source_references']
    raw={t:consume(source_refs[t],sources)for t in ('QQQ','SPY')}
    old={t:consume(view['accounted_baseline_references'][t],sources)for t in ('QQQ','SPY')}
    actual={t:consume(view['baseline_references'][t],sources)for t in ('QQQ','SPY')}
    tzif_ref=bridge['tzif_reference'];tzif=consume(tzif_ref,sources)
    # Derive expired sessions from supplied genuine capture clock/TZif, never registration.
    zone=modules['gap_core'].ZoneInfo.from_file(modules['gap_core'].BytesIO(tzif),key='America/New_York')
    begin,end=modules['gap_core'].utc(bridge['capture_started_at']),modules['gap_core'].utc(bridge['capture_completed_at'])
    known=[r['session']for r in view['known_typed_rows']]
    for day in bridge['source_evidence']['QQQ']['new_session_dates']:
        close,deadline=modules['gap_core'].conservative_timing(day,zone)
        if begin>=close and begin>=deadline and end>=deadline:known.append(day)
    prefixes={};evidences={}
    for ticker in ('QQQ','SPY'):
        prefixes[ticker],evidence=modules['prefix_core'].derive_accounted_prefix(source_bytes=raw[ticker],source_reference=source_refs[ticker],accounted_sessions=known,scope_start=known[0])
        evidences[ticker]=modules['gap_core'].prefix_evidence_bytes(evidence)
    inputs=dict(parent=registered['parent'],capture=capture_refs,registration=registration_ref,runtime=runtime,
        dependencies=dependencies,registration_core=regref,reference_core=refref,csv_reader=csvref)
    final_guard(sources,inventories,checker);resource_gate(output.anchor)
    output.mkdir(parents=True,exist_ok=False)
    try:
        started=save(output/'started.json',dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V5',input_references=inputs,source_hashes=dict(sources),
            retry_allowed=False,shared_upstream_capture_checker_reference=dependencies['capture_checker'],shared_upstream_checker_called=True,
            capture_readback_called=False,current_live_cache_read_or_reverified=False,**FLAGS))
        prefix_refs={t:save_bytes(output/(t+'.accounted_prefix.csv'),prefixes[t])for t in ('QQQ','SPY')}
        evidence_refs={t:save_bytes(output/(t+'.prefix_evidence.json'),evidences[t])for t in ('QQQ','SPY')}
        history=modules['gap_core'].extend_gap_history(parent=parent,capture_references=capture_refs,source_bytes=raw,source_references=source_refs,
            accounted_baseline_bytes=old,actual_baseline_bytes=actual,prefix_references=prefix_refs,prefix_evidence_references=evidence_refs,
            capture_started_at=bridge['capture_started_at'],capture_completed_at=bridge['capture_completed_at'],tzif_bytes=tzif,tzif_reference=tzif_ref)
        for item in (started,*prefix_refs.values(),*evidence_refs.values()):merge(sources,item)
        for path,sha in history['source_hashes'].items():require(sources.get(path)==sha,'Gap history outside immutable source closure')
        final_guard(sources,inventories,checker)
        href=save(output/'history.json',dict(schema=modules['parent_view'].WRAPPER_SCHEMA,history=history,input_references=inputs,
            source_hashes=dict(sources),shared_upstream_capture_checker_reference=dependencies['capture_checker'],shared_upstream_checker_called=True,
            capture_readback_called=False,current_live_cache_read_or_reverified=False,**FLAGS))
        publication=save(output/'publication.json',dict(schema=modules['parent_view'].PUBLICATION_SCHEMA,status=modules['parent_view'].PUBLICATION_STATUS,
            history_reference=href,input_references=inputs,source_hashes=dict(sources),**FLAGS))
        final_guard(sources,inventories,checker)
        for item in (started,href,publication):consume(item,{})
        namespace(output,('started.json','history.json','publication.json','QQQ.accounted_prefix.csv','SPY.accounted_prefix.csv','QQQ.prefix_evidence.json','SPY.prefix_evidence.json'))
        return dict(history_reference=href,publication_reference=publication)
    except BaseException as error:
        save(output/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,automatic_retry_allowed=False,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--registration-path',required=True);parser.add_argument('--registration-sha256',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();print(json.dumps(run(registration_path=args.registration_path,registration_sha256=args.registration_sha256,execute=args.execute)))
