"""Full reader over synthetic worker artifacts; raw gzip decoder remains real."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_ndx_double_source_execute_synthetic_review_20261008 as fixture_module
from scripts import ndx_double_replacement_compressed_independent_readback_20261008 as reader

worker = fixture_module.worker


class Tests(unittest.TestCase):
    def build(self, root, mode):
        registration, constants = fixture_module.Tests().fixture(root, mode)
        with patch.multiple(worker, **constants), patch.object(worker, 'resource_gate'):
            if mode == 'drift':
                with self.assertRaisesRegex(ValueError, 'Source drift'):
                    worker.execute(registration_path=registration['path'], registration_sha256=registration['sha256'], execute=True)
            else:
                worker.execute(registration_path=registration['path'], registration_sha256=registration['sha256'], execute=True)
        return registration, constants

    def read(self, root, registration, constants):
        parent = root/'output'
        request = parent/'requests/request-000000'
        result = request/'result.json'
        publication = parent/'publication.json'
        anchors = dict(ROOT=root, PARENT=parent, REQUEST=request, OUTPUT=root/'readback',
                       COUNTS=constants['COUNTS'], CONTENT=constants['CONTENT'],
                       PURE_SHA=reader.filehash(reader.PURE), WORKER=worker.SOURCE, WORKER_SHA=worker.LOADED,
                       REQUEST_RESULT_SHA=reader.filehash(result) if result.exists() else '1'*64,
                       PUBLICATION_SHA=reader.filehash(publication) if publication.exists() else None,
                       FIXED={key:constants['BOUND'][key] for key in reader.FIXED})
        calls = (root/'code/synthetic_calls.jsonl').read_bytes()
        with patch.multiple(reader, **anchors), patch.object(reader, 'memory_gate'), patch.object(worker, 'execute', side_effect=AssertionError('Worker execution prohibited during readback')), patch.object(worker, 'private_module', side_effect=AssertionError('Worker dependency loading prohibited during readback')):
            answer = reader.readback(registration_path=registration['path'], registration_sha256=registration['sha256'], execute=True)
        self.assertEqual((root/'code/synthetic_calls.jsonl').read_bytes(), calls)
        return json.loads(Path(answer['path']).read_bytes())

    def resign_result(self, root, change):
        path = root/'output/requests/request-000000/result.json'
        document = json.loads(path.read_bytes())
        change(document)
        path.write_bytes(reader.encode(document))
        publication = root/'output/publication.json'
        if publication.exists():
            value = json.loads(publication.read_bytes())
            value['result_reference'] = dict(path=str(path), sha256=reader.filehash(path), byte_count=path.stat().st_size)
            publication.write_bytes(reader.encode(value))

    def test_success_and_partial_readback_keep_original_raw_and_call_counts(self):
        for mode in ('success', 'postcheck'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registration, constants = self.build(root, mode)
                before = {str(p):reader.filehash(p) for p in (root/'output').rglob('*') if p.is_file()}
                report = self.read(root, registration, constants)
                self.assertEqual(report['inspection']['full_integer_count'], 513)
                self.assertEqual(report['inspection']['full_domain_complete'], mode == 'success')
                self.assertEqual(report['inspection']['counts']['validation_failure_returned'], 0 if mode == 'success' else 512)
                self.assertFalse(report['worker_called'])
                self.assertFalse(report['evaluator_called'])
                self.assertEqual(before, {str(p):reader.filehash(p) for p in (root/'output').rglob('*') if p.is_file()})

    def test_resigned_summary_stop_and_authority_rejected(self):
        changes = (
            ('summary', 'success', lambda value:value['partition']['counts'].update(inspected_feasible=512)),
            ('full_stop', 'success', lambda value:value.update(stopped={'status':'synthetic'})),
            ('partial_stop', 'postcheck', lambda value:value['stopped']['error'].update(message='different saved error')),
            ('authority', 'success', lambda value:value.update(promotion_allowed=True)),
        )
        for label, mode, change in changes:
            with self.subTest(attack=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registration, constants = self.build(root, mode)
                self.resign_result(root, change)
                with self.assertRaises(ValueError):
                    self.read(root, registration, constants)
                self.assertFalse((root/'readback').exists())

    def test_request_failure_overrides_complete_result_and_source_drift_is_rejected(self):
        for mode in ('success', 'drift'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registration, constants = self.build(root, mode)
                if mode == 'success':
                    (root/'output/requests/request-000000/failure.json').write_bytes(b'{}')
                    with self.assertRaisesRegex(ValueError, 'Failed request namespace'):
                        self.read(root, registration, constants)
                else:
                    self.assertTrue((root/'output/requests/request-000000/failure.json').exists())
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        self.read(root, registration, constants)
                self.assertFalse((root/'readback').exists())


if __name__ == '__main__':
    unittest.main()
