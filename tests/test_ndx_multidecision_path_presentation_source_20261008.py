"""Physical temporary source closure; never publishes to the actual namespace."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_multidecision_path_presentation_20261008 as subject
from test_ndx_multidecision_path_presentation_research import fixture


def write(path, value):
    blob = subject.encode(value)
    path.write_bytes(blob)
    return dict(path=str(path), sha256=hashlib.sha256(blob).hexdigest())


class SourceTests(unittest.TestCase):
    def environment(self, directory):
        original = fixture()
        root = Path(directory)
        parent, auditroot = root / 'k', root / 'audit'
        parent.mkdir(); auditroot.mkdir()
        reader = root / 'reader.py'
        reader.write_text('raise AssertionError("Reader must never execute")', encoding='utf-8')
        readerref = dict(path=str(reader), sha256=subject.sha(reader.read_bytes()))
        candidate = write(root / 'inputs.json', original['candidate_inputs_document'])
        inputs = dict(candidate_inputs=candidate)
        base = {candidate['path']: candidate['sha256'], readerref['path']: readerref['sha256']}
        comp = deepcopy(original['comparison_document'])
        pub = deepcopy(original['publication'])
        audit = deepcopy(original['audit'])
        for doc in (comp, pub, audit):
            doc['input_references'] = inputs
            doc['source_hashes'] = dict(base)
            doc['source_inventories'] = {}
        start = write(parent / 'started.json', dict(input_references=inputs, source_hashes=base, source_inventories={}))
        raw = write(parent / 'raw_result.json', dict(input_references=inputs, source_hashes=base,
            source_inventories={}, result=comp['comparison'], returned=True, call_invoked=True, error=None, started_reference=start))
        comp['raw_reference'] = raw
        compref = write(parent / 'comparison.json', comp)
        pub.update(comparison_reference=compref, started_reference=start, raw_reference=raw)
        pubref = write(parent / 'publication.json', pub)
        audit.update(comparison_reference=compref, publication_reference=pubref, reader_sha256=readerref['sha256'])
        for item in (start, raw, compref, pubref): audit['source_hashes'][item['path']] = item['sha256']
        auditref = write(auditroot / 'independent_readback.json', audit)
        write(auditroot / 'started.json', dict(comparison_reference=compref, publication_reference=pubref, source_hashes=audit['source_hashes']))
        refs = dict(comparison=compref, publication=pubref, audit=auditref, reader=readerref, candidate_inputs=candidate)
        return dict(BOUND={key: (value['path'], value['sha256']) for key, value in refs.items()},
                    PARENT=parent, AUDIT_ROOT=auditroot, OUTPUT=root / 'output', PURE_SHA=subject.sha(subject.PURE.read_bytes()))

    def test_complete_physical_publication_and_create_only(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.environment(directory)
            with patch.multiple(subject, **env):
                ref = subject.run(execute=True)
                result = json.loads(Path(ref['path']).read_bytes())
                self.assertEqual(subject.sha(Path(ref['path']).read_bytes()), ref['sha256'])
                self.assertEqual(result['presentation']['track_count'], 16)
                self.assertEqual(result['presentation']['coordinate_count'], 48)
                self.assertEqual({p.name for p in subject.OUTPUT.iterdir()}, {'started.json', 'presentation.json', 'publication.json'})
                self.assertFalse(result['independent_presentation_readback_passed'])
                with self.assertRaisesRegex(ValueError, 'Create-only'): subject.run(execute=True)

    def test_pending_and_unindexed_parent_bytes_stop_before_output(self):
        for attack in ('pending', 'extra', 'failed'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as directory:
                env = self.environment(directory)
                if attack == 'pending': env['PURE_SHA'] = None
                else: (env['PARENT'] / ('failure.json' if attack == 'failed' else 'extra.json')).write_text('{}')
                with patch.multiple(subject, **env):
                    with self.assertRaises(ValueError): subject.run(execute=True)
                    self.assertFalse(subject.OUTPUT.exists())

    def test_source_drift_after_projection_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.environment(directory)
            save = subject.save
            def drift(path, value):
                ref = save(path, value)
                if path.name == 'presentation.json':
                    Path(env['BOUND']['reader'][0]).write_text('changed')
                return ref
            with patch.multiple(subject, **env), patch.object(subject, 'save', side_effect=drift):
                with self.assertRaisesRegex(ValueError, 'Source closure drift'): subject.run(execute=True)
                self.assertTrue((subject.OUTPUT / 'presentation.json').exists())
                self.assertTrue((subject.OUTPUT / 'failure.json').exists())
                self.assertFalse((subject.OUTPUT / 'publication.json').exists())


if __name__ == '__main__':
    unittest.main()
