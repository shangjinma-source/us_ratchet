"""Physical gap reader attacks, independent of author test assertions."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_ndx_continuation_gap_history_consumers_20261009_v1 import physical_gap_consumers, publish_gap
from scripts import ndx_continuation_gap_history_runtime_20261009_v1 as publisher
from scripts import ndx_continuation_gap_history_independent_readback_20261009_v1 as reader


class GapRootIndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix='SYNTHETIC_ONLY_ROOT_GAP_INDEPENDENT_')
        cls.root = Path(cls.temporary.name)
        cls.context = physical_gap_consumers(cls.root)
        cls.research, parent, _, _, capture, _, _ = cls.context
        cls.refs = publish_gap(cls.context, parent, capture, 'root_independent_gap')
        cls.folder = Path(cls.refs['reference']['path']).parent
        cls.originals = {path.name: path.read_bytes() for path in cls.folder.iterdir()}
        cls.registration = cls.root / 'root_independent_gap_registration.json'

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tearDown(self):
        for name, raw in self.originals.items():
            (self.folder / name).write_bytes(raw)

    def read(self, output_name, history=None, publication=None):
        research, _, original, host, _, shared, private_patch = self.context
        args = dict(registration_path=str(self.registration), registration_sha256=reader.digest(self.registration.read_bytes()),
            history_reference=history or self.refs['reference'], publication_reference=publication or self.refs['publication_reference'],
            output_directory=str(research / output_name))
        with patch.multiple(reader, RESEARCH=research, CURRENT=original['current'], SHARED_ANCESTRY_VERIFIER=shared), \
                patch.object(reader, 'compile_private', side_effect=private_patch(reader)):
            return reader.readback(**args, **host)

    def test_coordinated_unclassified_source_cannot_select_io(self):
        trap = self.root / 'UNCLASSIFIED_READ_TRAP.json'
        trap.write_bytes(b'{"never_read":true}')
        trap_ref = reader.reference(str(trap), reader.digest(trap.read_bytes()))
        for index, attack in enumerate(('source_only', 'metadata', 'private_inputs')):
            with self.subTest(attack=attack):
                for name, raw in self.originals.items():
                    (self.folder / name).write_bytes(raw)
                history = reader.decode(self.originals['history.json'])
                publication = reader.decode(self.originals['publication.json'])
                for document in (history, publication):
                    document['source_hashes'][trap_ref['path']] = trap_ref['sha256']
                    if attack == 'metadata':
                        document['consumer_metadata_contract_reference'] = trap_ref
                    if attack == 'private_inputs':
                        document['reader_input_references'] = dict(runtime=trap_ref)
                raw = reader.encode(history)
                (self.folder / 'history.json').write_bytes(raw)
                href = reader.reference(str(self.folder / 'history.json'), reader.digest(raw))
                publication['history_reference'] = href
                raw = reader.encode(publication)
                (self.folder / 'publication.json').write_bytes(raw)
                pref = reader.reference(str(self.folder / 'publication.json'), reader.digest(raw))
                original_read = Path.read_bytes
                def read_guard(path):
                    if path == trap:
                        raise AssertionError('Unclassified metadata selected source IO')
                    return original_read(path)
                with patch.object(Path, 'read_bytes', read_guard), self.assertRaises(ValueError):
                    self.read('root_trap_audit_' + str(index), href, pref)
                self.assertFalse((self.research / ('root_trap_audit_' + str(index))).exists())

    def test_post_report_reader_start_drift_fails_and_forbids_retry(self):
        original_save = reader.save
        audit_folder = self.research / 'root_own_start_drift_audit'
        def drifting_save(path, value):
            result = original_save(path, value)
            if path.name == 'independent_readback.json':
                started = path.parent / 'started.json'
                started.write_bytes(started.read_bytes() + b'\n')
            return result
        with patch.object(reader, 'save', side_effect=drifting_save), self.assertRaises(ValueError):
            self.read(audit_folder.name)
        self.assertTrue((audit_folder / 'failure.json').exists())
        self.assertTrue((audit_folder / 'independent_readback.json').exists())
        with self.assertRaises(ValueError):
            self.read(audit_folder.name)
        result_ref = reader.reference(str(audit_folder / 'independent_readback.json'),
            reader.digest((audit_folder / 'independent_readback.json').read_bytes()))
        with self.assertRaises(ValueError):
            reader.consume(result_ref, {})


if __name__ == '__main__':
    unittest.main()
