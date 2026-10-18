"""Disposable zero-stub same-B/C physical chain. Never runs at import time.

Only pending source pins, research/current roots and clocks are patched in memory.
All eight implementations execute their original bytes and original algorithms.
"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_registered_compact_history_runtime_20261009_v3 as publisher
from scripts import ndx_registered_compact_history_independent_readback_20261009_v2 as reader
from scripts import ndx_continuation_forward_capture_runtime_20261009_v1 as capture
from scripts import ndx_continuation_forward_capture_independent_readback_20261009_v1 as capture_reader
from scripts import ndx_continuation_observation_writer_20261009_v1 as writer
from scripts import ndx_continuation_observation_independent_readback_20261009_v1 as observer
from scripts import ndx_continuation_gap_history_runtime_20261009_v1 as gap
from scripts import ndx_continuation_gap_history_independent_readback_20261009_v1 as gap_reader
from backtest import ndx_compact_implementation_pair_binding_research_v1 as binder
from backtest import ndx_continuation_consumer_role_registry_research_v1 as registry
from backtest import ndx_forward_capture_runtime_registration_research_v2 as capture_registration
from backtest import ndx_observation_runtime_registration_research_v1 as observation_registration
from backtest import ndx_gap_runtime_registration_research_v1 as gap_registration
from backtest import ndx_compact_history_runtime_registration_research_v1 as compact_registration
from ndx_registered_v5_parent_fixture_v2 import physical_registered_gap_parent, reference, envelope


CONSUMERS = dict(capture_publisher=capture, capture_independent_reader=capture_reader,
    observation_writer=writer, observation_independent_reader=observer,
    gap_publisher=gap, gap_independent_reader=gap_reader)
LOCKS = {
    publisher: '34f7aba84abf2fe19ceca40058d26fc57b9ad14373ef4b5925ab3fa40dabeeb4',
    reader: '5ceec753c972ecb5047311331285e5c7ec0ec67c361709f51ba101584498dddf',
    capture: '702ac5f79a68447e2d6eef54c9e0eaa80130f80d4042ef585ce47f3f9f0896bc',
    capture_reader: '0cf731d547ec15fcffd87f2f8b18bcfe4a227e7c8de69a1c25e14e0ffb798cea',
    writer: 'b9c07d070538f2fd8cadc689210cbbd317dcf094341db8d6bbe8ad6bbdee2704',
    observer: 'c41155112759d536773148449aa725b30f48b00a2fd149286fb15f6257484822',
    gap: '13f890289fd1816da50b7c6abcdd215c3c9701a8e306e04306b5f612dff8cdb3',
    gap_reader: 'd3b3cc7a765d58c2f3dcb45c6cca1f13aed4fc47e45b27f43e2490435bfc85cd'}
PIN_DIGESTS = dict(PAIR_BINDING_CORE='dde8b681612d2b4fc0993bb9b697dcefb0222036d3e1bb6f4aa5f2dd76d7e4ad',
    ANCESTRY_CONTRACT='081ba024fa997c37c1f030fcec7d4d22ca6411eec652d15a5049b57d62a31a76',
    CONSUMER_ROLE_CORE='184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b',
    CONSUMER_METADATA_CORE='b0d16b1b364d2c32e55d826c1f9d63dfffeb27df7bcabfe972efd029e8e2fdeb')


def pins(module):
    names = dict(CONSUMER_ROLE_CORE='CONSUMER_REGISTRY_CORE',
        CONSUMER_METADATA_CORE='CONSUMER_METADATA_CONTRACT') if module is publisher else {}
    return {names.get(key, key): (getattr(module, names.get(key, key))[0], digest)
        for key, digest in PIN_DIGESTS.items()}


def assert_source_locks():
    for module, digest in LOCKS.items():
        assert reference(module.SOURCE)['sha256'] == digest
        assert module.LOADED_SHA == digest


@contextmanager
def bound(module, context, clocks=None):
    with ExitStack() as stack:
        values = dict(RESEARCH=context['research'], CURRENT=context['current'])
        if module in (publisher, reader):
            values.update(pins(module))
        else:
            values['SHARED_ANCESTRY_VERIFIER'] = (reader.SOURCE, LOCKS[reader])
            original = module.compile_private
            def compile_bound(path, raw, digest, replacements=()):
                loaded = original(path, raw, digest, replacements)
                if Path(path) == reader.SOURCE:
                    loaded.__dict__.update(pins(reader))
                    loaded.RESEARCH = context['research']
                    loaded.CURRENT = context['current']
                return loaded
            stack.enter_context(patch.object(module, 'compile_private', compile_bound))
        stack.enter_context(patch.multiple(module, **values))
        if clocks is not None:
            stack.enter_context(patch.object(module, 'now', side_effect=clocks))
        yield


def saved(context, name, value):
    path = context['root'] / (name + '.json')
    assert not path.exists()
    path.write_bytes(reader.encode(value))
    return reference(path)


def create_host(context):
    """First and only B/C writes bind actual sources, with no intermediate stubs."""
    pair = saved(context, 'TEMPORARY_REAL_PAIR_B', dict(schema=binder.SCHEMA,
        family=binder.FAMILY, protocol=binder.PROTOCOL, role=binder.ROLE,
        publisher_reference=reference(publisher.SOURCE), independent_reader_reference=reference(reader.SOURCE),
        contract_reference=reader.reference(*pins(reader)['ANCESTRY_CONTRACT']),
        publisher_dependency_references=reader.publisher_dependencies(),
        reader_dependency_references={key: reader.reference(*value) for key, value in reader.READER_ALGORITHMS.items()},
        approved_legacy_binding_references=[], **binder.FLAGS))
    consumers = {role: reference(module.SOURCE) for role, module in CONSUMERS.items()}
    assert set(consumers) == set(registry.CONSUMER_ROLES)
    consumer = saved(context, 'TEMPORARY_REAL_CONSUMERS_C', dict(schema=registry.SCHEMA,
        family=registry.FAMILY, protocol=registry.PROTOCOL, role=registry.ROLE,
        implementation_pair_binding_reference=pair,
        ancestry_contract_reference=reader.reference(*pins(reader)['ANCESTRY_CONTRACT']),
        consumer_references=consumers, **registry.FLAGS))
    context.update(pair=pair, consumer=consumer, implementations=consumers,
        original_host_bytes={item['path']: Path(item['path']).read_bytes() for item in (pair, consumer)},
        host_args=dict(implementation_pair_binding_path=pair['path'], implementation_pair_binding_sha256=pair['sha256'],
            consumer_role_registry_path=consumer['path'], consumer_role_registry_sha256=consumer['sha256'], execute=True))


def registration(context, module, core, parent, name, **extra):
    dependencies = module.configured(module.DEPENDENCIES) if module is not publisher else {
        key: reader.reference(*value) for key, value in publisher.DEPENDENCIES.items()}
    item = saved(context, name + '_registration', dict(schema=core.SCHEMA,
        runtime_reference=reference(module.SOURCE), dependency_references=dependencies,
        parent=parent, output_directory=str(context['research'] / name), **extra, **core.FLAGS))
    context['registrations'].append(item)
    return dict(registration_path=item['path'], registration_sha256=item['sha256'])


def capture_pair(context, parent, name, day, minute):
    args = registration(context, capture, capture_registration, parent, name)
    with bound(capture, context, [f'{day}T20:{minute:02d}:00+00:00', f'{day}T20:{minute:02d}:01+00:00']):
        produced = capture.run(**args, **context['host_args'])
    with bound(capture_reader, context):
        audit = capture_reader.readback(**args, **produced, **context['host_args'],
            output_directory=str(context['research'] / (name + '_audit')))
    refs = dict(reference=produced['capture_reference'], publication_reference=produced['publication_reference'],
        readback_reference=audit, reader_reference=reference(capture_reader.SOURCE))
    context['captures'].append(refs)
    return refs


def gap_pair(context, parent, captured, name):
    args = registration(context, gap, gap_registration, parent, name, capture=captured)
    with bound(gap, context):
        produced = gap.run(**args, **context['host_args'])
    with bound(gap_reader, context):
        audit = gap_reader.readback(**args, **produced, **context['host_args'],
            output_directory=str(context['research'] / (name + '_audit')))
    refs = dict(reference=produced['history_reference'], publication_reference=produced['publication_reference'],
        readback_reference=audit, reader_reference=reference(gap_reader.SOURCE))
    context['gaps'].append(refs)
    return refs


def actual_pair(context, parent, captured, day):
    name = 'actual_' + day.replace('-', '_')
    args = registration(context, writer, observation_registration, parent, name + '_observation', capture=captured)
    with bound(writer, context, [f'{day}T20:06:0{second}+00:00' for second in range(4)]):
        receipt = writer.run(**args, **context['host_args'])
    payload = reader.decode(Path(receipt['path']).read_bytes())['payload_reference']
    with bound(observer, context):
        audit = observer.readback(**args, **context['host_args'], payload_reference=payload, receipt_reference=receipt)
    observed = dict(payload_reference=payload, receipt_reference=receipt,
        audit_reference=audit, reader_reference=reference(observer.SOURCE))
    context['observations'].append(observed)
    args = registration(context, publisher, compact_registration, parent, name, observation=observed)
    with bound(publisher, context):
        produced = publisher.run(**args, **context['host_args'])
    with bound(reader, context):
        audit = reader.readback(**args, history_reference=produced['history_reference'],
            publication_reference=produced['publication_reference'], **context['host_args'],
            output_directory=str(context['research'] / (name + '_audit')))
    refs = dict(reference=produced['history_reference'], publication_reference=produced['publication_reference'],
        readback_reference=audit, reader_reference=reference(reader.SOURCE))
    context['actuals'].append(refs)
    return refs


def append_temporary_session(context, previous, following):
    """Append equal-price rows only to disposable current files, preserving prefix."""
    for path in context['current'].values():
        path = Path(path).resolve()
        assert context['root'] in path.parents
        raw = path.read_bytes()
        assert raw.endswith(b'\n')
        row = raw.splitlines()[-1]
        date, suffix = row.split(b',', 1)
        assert date.decode() == previous
        path.write_bytes(raw + following.encode() + b',' + suffix + b'\n')
        assert path.read_bytes().startswith(raw)


def physical_six_consumer_pair_chain(root):
    assert_source_locks()
    root = Path(root).resolve()
    context = dict(root=root, research=root / 'research', registrations=[], captures=[], gaps=[], observations=[], actuals=[])
    parent, legacy = physical_registered_gap_parent(root, context['research'])
    context['current'] = legacy['current']
    context['legacy_parent'] = parent
    create_host(context)
    captured = capture_pair(context, parent, 'mixed_gap_capture', '2026-10-13', 3)
    parent = gap_pair(context, parent, captured, 'mixed_gap_parent')
    captured = capture_pair(context, parent, 'no_expired_gap_capture', '2026-10-13', 4)
    parent = gap_pair(context, parent, captured, 'no_expired_gap_parent')
    for day in ('2026-10-13', '2026-10-14', '2026-10-15'):
        if day != '2026-10-13':
            append_temporary_session(context, '2026-10-' + str(int(day[-2:]) - 1), day)
        captured = capture_pair(context, parent, 'unique_capture_' + day.replace('-', '_'), day, 5)
        plan = envelope(captured)['document']['plan']
        assert (plan['status'], plan['candidate_session']) == ('ONE_NEW_SESSION_CAPTURE_CANDIDATE', day)
        parent = actual_pair(context, parent, captured, day)
    final_capture = capture_pair(context, parent, 'capture_after_actual15', '2026-10-15', 9)
    with bound(reader, context):
        replay = reader.verify_saved_parent_ancestry(parent_references=parent,
            consumer_capture_references=final_capture, **context['host_args'])
        replay['final_guard']()
    context.update(final_parent=parent, final_capture=final_capture, replay=replay)
    for path, raw in context['original_host_bytes'].items():
        assert Path(path).read_bytes() == raw
    assert_source_locks()
    return context
