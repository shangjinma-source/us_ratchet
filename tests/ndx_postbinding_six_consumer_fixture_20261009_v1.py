"""Postbinding short physical chain; only roots and clocks may be patched."""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch
import hashlib
import json

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

ROOT = Path(__file__).resolve().parents[1]
SEALED = ROOT / 'tmp/continuation_six_real_consumers_same_pair_author_20261009_v1/physical'
PLAN = ROOT / 'tmp/continuation_current_scope_propagation_revision_20261009_v2/plan.json'
PLAN_SHA = '651fab1ec8bb4dbc2aa0229db0f695197bf30fd9b7eecb8d67b7ab90ccc69124'
CONSUMERS = dict(capture_publisher=capture, capture_independent_reader=capture_reader,
    observation_writer=writer, observation_independent_reader=observer,
    gap_publisher=gap, gap_independent_reader=gap_reader)
IMPLEMENTATIONS = (publisher, reader, *CONSUMERS.values())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def reference(path):
    return dict(path=str(Path(path)), sha256=sha(Path(path).read_bytes()))


def assert_bound_sources():
    raw = PLAN.read_bytes()
    assert sha(raw) == PLAN_SHA
    plan = json.loads(raw)
    for module in IMPLEMENTATIONS:
        expected = plan['new_source_hashes'][str(module.SOURCE.relative_to(ROOT)).replace('\\', '/')]
        assert reference(module.SOURCE)['sha256'] == expected == module.LOADED_SHA
    for module in (publisher, reader):
        for change in plan['initial_binding_deltas'][str(module.SOURCE.relative_to(ROOT)).replace('\\', '/')]:
            assert getattr(module, change['constant'])[1] == change['new_sha256']
    for module in CONSUMERS.values():
        assert module.SHARED_ANCESTRY_VERIFIER == (reader.SOURCE, reader.LOADED_SHA)
    return {str(module.SOURCE): module.LOADED_SHA for module in IMPLEMENTATIONS}


@contextmanager
def roots(module, context, clocks=None):
    """No pending-pin, shared verifier, loader or arithmetic substitutions."""
    with ExitStack() as stack:
        stack.enter_context(patch.multiple(module, RESEARCH=context['research'], CURRENT=context['current']))
        if clocks is not None:
            stack.enter_context(patch.object(module, 'now', side_effect=clocks))
        yield


def save(context, name, value):
    path = context['root'] / (name + '.json')
    with path.open('xb') as stream:
        stream.write(reader.encode(value))
    return reference(path)


def register(context, module, core, parent, name, **extra):
    dependencies = ({key: reader.reference(*value) for key, value in module.DEPENDENCIES.items()}
        if module is publisher else module.configured(module.DEPENDENCIES))
    item = save(context, name + '_registration', dict(schema=core.SCHEMA,
        runtime_reference=reference(module.SOURCE), dependency_references=dependencies,
        parent=parent, output_directory=str(context['research'] / name), **extra, **core.FLAGS))
    return dict(registration_path=item['path'], registration_sha256=item['sha256'])


def host(context):
    pair = save(context, 'TEMPORARY_POSTBINDING_B', dict(schema=binder.SCHEMA, family=binder.FAMILY,
        protocol=binder.PROTOCOL, role=binder.ROLE, publisher_reference=reference(publisher.SOURCE),
        independent_reader_reference=reference(reader.SOURCE), contract_reference=reader.reference(*reader.ANCESTRY_CONTRACT),
        publisher_dependency_references=reader.publisher_dependencies(),
        reader_dependency_references={key: reader.reference(*value) for key, value in reader.READER_ALGORITHMS.items()},
        approved_legacy_binding_references=[], **binder.FLAGS))
    consumer = save(context, 'TEMPORARY_POSTBINDING_C', dict(schema=registry.SCHEMA,
        family=registry.FAMILY, protocol=registry.PROTOCOL, role=registry.ROLE,
        implementation_pair_binding_reference=pair, ancestry_contract_reference=reader.reference(*reader.ANCESTRY_CONTRACT),
        consumer_references={role: reference(module.SOURCE) for role, module in CONSUMERS.items()}, **registry.FLAGS))
    context.update(pair=pair, consumer=consumer,
        host_bytes={item['path']: Path(item['path']).read_bytes() for item in (pair, consumer)},
        host_args=dict(implementation_pair_binding_path=pair['path'], implementation_pair_binding_sha256=pair['sha256'],
            consumer_role_registry_path=consumer['path'], consumer_role_registry_sha256=consumer['sha256'], execute=True))


def capture_pair(context, parent, name, minute):
    arguments = register(context, capture, capture_registration, parent, name)
    with roots(capture, context, [f'2026-10-13T20:{minute:02d}:00+00:00', f'2026-10-13T20:{minute:02d}:01+00:00']):
        produced = capture.run(**arguments, **context['host_args'])
    with roots(capture_reader, context):
        audited = capture_reader.readback(**arguments, **produced, **context['host_args'],
            output_directory=str(context['research'] / (name + '_audit')))
    refs = dict(reference=produced['capture_reference'], publication_reference=produced['publication_reference'],
        readback_reference=audited, reader_reference=reference(capture_reader.SOURCE))
    context['captures'].append(refs)
    return refs


def gap_pair(context, parent, captured):
    arguments = register(context, gap, gap_registration, parent, 'postbinding_gap', capture=captured)
    with roots(gap, context):
        produced = gap.run(**arguments, **context['host_args'])
    with roots(gap_reader, context):
        audited = gap_reader.readback(**arguments, **produced, **context['host_args'],
            output_directory=str(context['research'] / 'postbinding_gap_audit'))
    refs = dict(reference=produced['history_reference'], publication_reference=produced['publication_reference'],
        readback_reference=audited, reader_reference=reference(gap_reader.SOURCE))
    context['gap'] = refs
    return refs


def actual_pair(context, parent, captured):
    arguments = register(context, writer, observation_registration, parent, 'postbinding_observation', capture=captured)
    with roots(writer, context, [f'2026-10-13T20:06:0{second}+00:00' for second in range(4)]):
        receipt = writer.run(**arguments, **context['host_args'])
    payload = json.loads(Path(receipt['path']).read_bytes())['payload_reference']
    with roots(observer, context):
        audited = observer.readback(**arguments, **context['host_args'], payload_reference=payload, receipt_reference=receipt)
    observed = dict(payload_reference=payload, receipt_reference=receipt, audit_reference=audited,
        reader_reference=reference(observer.SOURCE))
    context['observation'] = observed
    arguments = register(context, publisher, compact_registration, parent, 'postbinding_actual', observation=observed)
    with roots(publisher, context):
        produced = publisher.run(**arguments, **context['host_args'])
    with roots(reader, context):
        audited = reader.readback(**arguments, **context['host_args'],
            history_reference=produced['history_reference'], publication_reference=produced['publication_reference'],
            output_directory=str(context['research'] / 'postbinding_actual_audit'))
    return dict(reference=produced['history_reference'], publication_reference=produced['publication_reference'],
        readback_reference=audited, reader_reference=reference(reader.SOURCE))


def build_context(root):
    assert_bound_sources()
    root = Path(root).resolve()
    assert root != SEALED and SEALED not in root.parents
    research = root / 'research'
    research.mkdir(exist_ok=False)
    current_folder = root / 'current'
    current_folder.mkdir(exist_ok=False)
    current = {}
    for ticker in ('QQQ', 'SPY'):
        source = SEALED / 'research/mixed_gap_capture' / (ticker + '.csv')
        raw = source.read_bytes()
        assert raw.splitlines()[-1].split(b',', 1)[0] == b'2026-10-13'
        current[ticker] = current_folder / (ticker + '.csv')
        with current[ticker].open('xb') as stream:
            stream.write(raw)
    legacy = SEALED / 'research/registered_gap_parent'
    parent = dict(reference=reference(legacy / 'history.json'), publication_reference=reference(legacy / 'publication.json'),
        readback_reference=reference(SEALED / 'research/registered_gap_parent_audit/independent_readback.json'),
        reader_reference=reference(ROOT / 'scripts/ndx_registered_gap_history_independent_readback_20261009_v1.py'))
    changed_sources = set(assert_bound_sources())
    for key in ('reference', 'publication_reference', 'readback_reference'):
        value = json.loads(Path(parent[key]['path']).read_bytes())
        assert changed_sources.isdisjoint(value['source_hashes'])
    context = dict(root=root, research=research, current=current, parent=parent, captures=[])
    host(context)
    return context


def run_short_chain(context):
    parent = context['parent']
    mixed = capture_pair(context, parent, 'postbinding_mixed_capture', 3)
    parent = gap_pair(context, parent, mixed)
    unique = capture_pair(context, parent, 'postbinding_unique_capture', 5)
    plan = json.loads(Path(unique['reference']['path']).read_bytes())['plan']
    assert (plan['status'], plan['candidate_session']) == ('ONE_NEW_SESSION_CAPTURE_CANDIDATE', '2026-10-13')
    actual = actual_pair(context, parent, unique)
    final_capture = capture_pair(context, actual, 'postbinding_final_capture', 9)
    with roots(reader, context):
        replay = reader.verify_saved_parent_ancestry(parent_references=actual,
            consumer_capture_references=final_capture, **context['host_args'])
        replay['final_guard']()
        assert replay['capture_plan']['status'] == 'NO_NEW_SESSION'
        for path, digest in replay['sources'].items():
            assert reference(path)['sha256'] == digest
        replay['final_guard']()
    for path, raw in context['host_bytes'].items():
        assert Path(path).read_bytes() == raw
    assert_bound_sources()
    context.update(actual=actual, final_capture=final_capture,
        replay={key: value for key, value in replay.items() if key != 'final_guard'})
    return context
