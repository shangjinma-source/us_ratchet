"""Real capture arithmetic and IO; shared-family/ancestry APIs are controlled.

The pending shared-reader pin is never bypassed as a production assertion.
These tests do not execute real R2 or establish continuous 14->15 acceptance.
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from backtest import ndx_continuation_consumer_role_registry_research_v1 as registry
from scripts import ndx_continuation_forward_capture_runtime_20261009_v1 as producer
from scripts import ndx_continuation_forward_capture_independent_readback_20261009_v1 as reader
from test_ndx_continuation_forward_capture_runtime_20261009_v1_independent_review import pipeline_fixture, run_pipeline


def reader_fixture(root):
    context = pipeline_fixture(root)
    registration = producer.decode(Path(context['args']['registration_path']).read_bytes())
    base = context['replay'].verify_saved_parent_ancestry(parent_references=registration['parent'], **context['args'])
    cref = Path(context['args']['consumer_role_registry_path'])
    document = producer.decode(cref.read_bytes())
    previous = document['consumer_references']['capture_independent_reader']
    document['consumer_references']['capture_independent_reader'] = reader.reference(str(reader.SOURCE), reader.LOADED_SHA)
    cref.write_bytes(producer.encode(document))
    registry_ref = producer.reference(str(cref), producer.digest(cref.read_bytes()))
    context['args']['consumer_role_registry_sha256'] = registry_ref['sha256']
    base['consumer_registry_view'] = registry.inspect_consumer_roles(registry=document,
        registry_reference=registry_ref, host_registry_reference=registry_ref, bound_pair=base['bound_pair'])
    base['sources'][str(cref)] = registry_ref['sha256']
    del base['sources'][previous['path']]
    base['sources'][str(reader.SOURCE)] = reader.LOADED_SHA

    def guard():
        for path, digest in base['sources'].items():
            producer.consume(producer.reference(path, digest), {})

    def replay(**kwargs):
        assert kwargs['parent_references'] == registration['parent']
        assert kwargs['consumer_role_registry_sha256'] == registry_ref['sha256']
        return dict(base, sources=deepcopy(base['sources']), final_guard=guard)

    def family(**kwargs):
        assert kwargs['consumer_role_registry_sha256'] == registry_ref['sha256']
        return {key: (guard if key == 'final_guard' else deepcopy(value)) for key, value in
            dict(bound_pair=base['bound_pair'], consumer_registry_view=base['consumer_registry_view'],
                consumer_registry_core_reference=base['consumer_registry_core_reference'],
                consumer_metadata_contract_reference=base['consumer_metadata_contract_reference'],
                sources=base['sources'], final_guard=guard).items()}

    context['replay'] = SimpleNamespace(verify_saved_parent_ancestry=replay, inspect_host_continuation_family=family)
    return context


def run_reader(context, published):
    original = reader.compile_private

    def compile_role(path, raw, expected, replacements=()):
        if str(path) == context['stub']['path']:
            assert reader.digest(raw) == expected == context['stub']['sha256']
            return context['replay']
        return original(path, raw, expected, replacements)

    with patch.multiple(reader, RESEARCH=context['research'], CURRENT=context['current'],
            SHARED_ANCESTRY_VERIFIER=(Path(context['stub']['path']), context['stub']['sha256'])), \
            patch.object(reader, 'compile_private', side_effect=compile_role):
        return reader.readback(**context['args'], **published, output_directory=str(context['research'] / 'capture_reader'))


class ContinuationCaptureReaderTests(unittest.TestCase):
    def test_pending_shared_reader_pin_prevents_any_io(self):
        with patch.object(reader, 'consume', side_effect=AssertionError('Pending source IO')):
            with self.assertRaises(ValueError):
                reader.readback(registration_path='E:/synthetic/registration', registration_sha256='a' * 64,
                    capture_reference=reader.reference('E:/synthetic/capture', 'b' * 64),
                    publication_reference=reader.reference('E:/synthetic/publication', 'c' * 64),
                    output_directory='E:/synthetic/readback', implementation_pair_binding_path='E:/synthetic/B',
                    implementation_pair_binding_sha256='d' * 64, consumer_role_registry_path='E:/synthetic/C',
                    consumer_role_registry_sha256='e' * 64, execute=True)

    def test_real_independent_formula_report_and_mutable_cache_exclusion(self):
        with TemporaryDirectory(prefix='CAPTURE_READER_CONTROLLED_SHARED_APIS_') as directory:
            context = reader_fixture(Path(directory))
            published = run_pipeline(context)
            for path in context['current'].values():
                path.write_bytes(b'newer mutable cache; must not be read by independent reconstruction')
            report_ref = run_reader(context, published)
            report = reader.decode(Path(report_ref['path']).read_bytes())
            own_start = report['reader_started_reference_observed_not_external_anchor']
            self.assertEqual(report['status'], 'PURE_FORWARD_CAPTURE_READBACK_PASS')
            self.assertEqual(report['counts']['parent_typed_row_count'], 69)
            self.assertEqual(report['counts']['status'], 'NO_NEW_SESSION')
            self.assertFalse(report['producer_called'])
            self.assertFalse(report['capture_core_called'])
            self.assertFalse(report['prefix_core_called_for_parent_evidence_only'])
            self.assertEqual(report['source_hashes'][own_start['path']], own_start['sha256'])
            self.assertEqual(len(report['reader_input_references']), 13)
            self.assertEqual(reader.decode(Path(own_start['path']).read_bytes())['input_references'], report['input_references'])
            for path in context['current'].values():
                self.assertNotIn(str(path), report['source_hashes'])
            for key in reader.FLAGS:
                self.assertIs(report[key], False)
            with self.assertRaisesRegex(ValueError, 'create-only'):
                run_reader(context, published)

    def test_coordinated_source_omission_and_unknown_wrapper_reject_without_output(self):
        for attack in ('missing_fixed_source', 'unknown_wrapper_ref'):
            with self.subTest(attack=attack), TemporaryDirectory(prefix='CAPTURE_READER_CLOSURE_ATTACK_') as directory:
                context = reader_fixture(Path(directory))
                published = run_pipeline(context)
                document_path = Path(published['capture_reference']['path'])
                publication_path = Path(published['publication_reference']['path'])
                document = reader.decode(document_path.read_bytes())
                publication = reader.decode(publication_path.read_bytes())
                trap_path = None
                if attack == 'missing_fixed_source':
                    del document['source_hashes'][str(reader.CONSUMER_METADATA_CORE[0])]
                    del publication['source_hashes'][str(reader.CONSUMER_METADATA_CORE[0])]
                else:
                    trap = Path(directory) / 'MUST_NOT_READ.identity'
                    trap.write_bytes(b'UNCLASSIFIED_SOURCE_CLAIM_TRAP')
                    trap_path = str(trap)
                    claim = reader.reference(trap_path, reader.digest(trap.read_bytes()))
                    document['unknown_extra_evidence'] = claim
                    document['source_hashes'][trap_path] = claim['sha256']
                document_path.write_bytes(reader.encode(document))
                published['capture_reference'] = reader.reference(str(document_path), reader.digest(document_path.read_bytes()))
                publication['capture_reference'] = published['capture_reference']
                publication_path.write_bytes(reader.encode(publication))
                published['publication_reference'] = reader.reference(str(publication_path), reader.digest(publication_path.read_bytes()))
                original_consume = reader.consume

                def classified_consume(item, sources, **kwargs):
                    if trap_path is not None and item.get('path') == trap_path:
                        raise AssertionError('Unclassified claim selected source IO')
                    return original_consume(item, sources, **kwargs)

                with patch.object(reader, 'consume', side_effect=classified_consume), self.assertRaises(ValueError):
                    run_reader(context, published)
                self.assertFalse((context['research'] / 'capture_reader').exists())

    def test_reader_own_start_drift_or_extra_file_preserves_failure_and_blocks_retry(self):
        for attack in ('own_start', 'extra_file'):
            with self.subTest(attack=attack), TemporaryDirectory(prefix='CAPTURE_READER_OWN_GUARD_') as directory:
                context = reader_fixture(Path(directory))
                published = run_pipeline(context)
                original = reader.save_bytes

                def save(path, raw):
                    value = original(path, raw)
                    if path.name == 'started.json':
                        if attack == 'own_start':
                            path.write_bytes(raw + b'\n')
                        else:
                            (path.parent / 'unregistered.json').write_bytes(b'{}')
                    return value

                with patch.object(reader, 'save_bytes', side_effect=save), self.assertRaises(ValueError):
                    run_reader(context, published)
                output = context['research'] / 'capture_reader'
                self.assertTrue((output / 'failure.json').exists())
                self.assertFalse((output / 'independent_readback.json').exists())
                with self.assertRaisesRegex(ValueError, 'create-only'):
                    run_reader(context, published)


if __name__ == '__main__':
    unittest.main()
