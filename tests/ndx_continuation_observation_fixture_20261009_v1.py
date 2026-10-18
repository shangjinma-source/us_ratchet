"""Disposable real registered ancestors and new capture/observation implementations."""
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_registered_compact_history_independent_readback_20261009_v2 as shared
from scripts import ndx_continuation_forward_capture_runtime_20261009_v1 as capture
from scripts import ndx_continuation_forward_capture_independent_readback_20261009_v1 as capture_reader
from scripts import ndx_continuation_observation_writer_20261009_v1 as writer
from scripts import ndx_continuation_observation_independent_readback_20261009_v1 as observer
from backtest import ndx_forward_capture_runtime_registration_research_v2 as capture_registration
from backtest import ndx_observation_runtime_registration_research_v1 as observation_registration
from test_ndx_compact_reader_v2_optional_consumer_author_20261009 import host_files, pins
from ndx_registered_v5_parent_fixture_v2 import physical_registered_gap_parent, reference, envelope
from ndx_registered_v5_observation_fixture_v2 import _capture, _gap


def bind_shared(module, research, current):
    original = module.compile_private
    def compile_bound(path, raw, expected, replacements=()):
        loaded = original(path, raw, expected, replacements)
        if Path(path) == shared.SOURCE:
            loaded.__dict__.update(pins())
            loaded.RESEARCH = research
            loaded.CURRENT = current
        return loaded
    return compile_bound


def physical_continuation_candidate(root):
    root = Path(root).resolve()
    research = root / 'research'
    initial, context = physical_registered_gap_parent(root, research)
    current = context['current']
    captures, _ = _capture(root, research, initial, current, 'registered_second_gap_capture',
        '2026-10-13T20:03:00+00:00', '2026-10-13T20:03:01+00:00')
    parent, _ = _gap(root, research, initial, current, captures, 'registered_second_gap_parent')
    implementations = {role: reference(module.SOURCE) for role, module in (
        ('capture_publisher', capture), ('capture_independent_reader', capture_reader),
        ('observation_writer', writer), ('observation_independent_reader', observer))}
    host_args, _ = host_files(root, implementations)
    value = dict(schema=capture_registration.SCHEMA, runtime_reference=implementations['capture_publisher'],
        dependency_references=capture.configured(capture.DEPENDENCIES), parent=parent,
        output_directory=str(research / 'continuation_unique_capture'), **capture_registration.FLAGS)
    path = root / 'continuation_unique_capture_registration.json'
    path.write_bytes(capture.encode(value))
    args = dict(registration_path=str(path), registration_sha256=reference(path)['sha256'])
    shared_ref = (shared.SOURCE, shared.LOADED_SHA)
    with patch.multiple(capture, RESEARCH=research, CURRENT=current, SHARED_ANCESTRY_VERIFIER=shared_ref), \
            patch.object(capture, 'compile_private', bind_shared(capture, research, current)), \
            patch.object(capture, 'now', side_effect=['2026-10-13T20:05:00+00:00', '2026-10-13T20:05:01+00:00']):
        saved = capture.run(**args, **host_args)
    with patch.multiple(capture_reader, RESEARCH=research, CURRENT=current, SHARED_ANCESTRY_VERIFIER=shared_ref), \
            patch.object(capture_reader, 'compile_private', bind_shared(capture_reader, research, current)):
        audited = capture_reader.readback(**args, **host_args, **saved,
            output_directory=str(research / 'continuation_unique_capture_audit'))
    captures = dict(reference=saved['capture_reference'], publication_reference=saved['publication_reference'],
        readback_reference=audited, reader_reference=implementations['capture_independent_reader'])
    plan = envelope(captures)['document']['plan']
    if plan['status'] != 'ONE_NEW_SESSION_CAPTURE_CANDIDATE' or plan['candidate_session'] != '2026-10-13':
        raise ValueError('Physical registered prefix must yield the unique 13th session')
    value = dict(schema=observation_registration.SCHEMA, runtime_reference=implementations['observation_writer'],
        dependency_references=writer.configured(writer.DEPENDENCIES), parent=parent, capture=captures,
        output_directory=str(research / 'continuation_actual'), **observation_registration.FLAGS)
    path = root / 'continuation_actual_registration.json'
    path.write_bytes(writer.encode(value))
    args = dict(registration_path=str(path), registration_sha256=reference(path)['sha256'])
    return dict(root=root, research=research, current=current, parent=parent, capture=captures,
        host_args=host_args, registration_args=args, shared_reference=shared_ref)


def run_writer(context):
    with patch.multiple(writer, RESEARCH=context['research'], CURRENT=context['current'],
            SHARED_ANCESTRY_VERIFIER=context['shared_reference']), \
            patch.object(writer, 'compile_private', bind_shared(writer, context['research'], context['current'])), \
            patch.object(writer, 'now', side_effect=['2026-10-13T20:06:00+00:00', '2026-10-13T20:06:01+00:00',
                '2026-10-13T20:06:02+00:00', '2026-10-13T20:06:03+00:00']):
        receipt = writer.run(**context['registration_args'], **context['host_args'])
    payload = writer.decode(Path(receipt['path']).read_bytes())['payload_reference']
    return payload, receipt


def run_reader(context, payload, receipt):
    with patch.multiple(observer, RESEARCH=context['research'], CURRENT=context['current'],
            SHARED_ANCESTRY_VERIFIER=context['shared_reference']), \
            patch.object(observer, 'compile_private', bind_shared(observer, context['research'], context['current'])):
        return observer.readback(**context['registration_args'], **context['host_args'],
            payload_reference=payload, receipt_reference=receipt)
