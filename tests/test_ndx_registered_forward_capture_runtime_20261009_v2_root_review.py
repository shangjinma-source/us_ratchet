"""Root review: physical upstream artifacts must belong to their namespace."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_ndx_registered_forward_capture_runtime_20261009_v2_independent_review as physical
from ndx_v5_physical_parent_fixture import physical_gap_parent, envelope, reference

capture = physical.capture


def relocate_evidence(parent, old_path, new_path):
    """Re-sign only disposable fixture artifacts with a different evidence path."""
    parent = deepcopy(parent)
    documents = envelope(parent)
    folder = Path(parent['reference']['path']).parent
    started = capture.decode((folder / 'started.json').read_bytes())

    def rewrite(value):
        if type(value) is dict:
            if value.get('path') == str(old_path):
                value['path'] = str(new_path)
            if str(old_path) in value:
                value[str(new_path)] = value.pop(str(old_path))
            for child in value.values():
                rewrite(child)
        elif type(value) is list:
            for child in value:
                rewrite(child)

    for document in (started, documents['document'], documents['publication'], documents['readback']):
        rewrite(document)
    (folder / 'started.json').write_bytes(capture.encode(started))
    for document in documents.values():
        physical.replace_claim(document, str(folder / 'started.json'), reference(folder / 'started.json')['sha256'])
    for role, key, following in (
            ('reference', 'document', ('publication', 'readback')),
            ('publication_reference', 'publication', ('readback',)),
            ('readback_reference', 'readback', ())):
        path = Path(parent[role]['path'])
        path.write_bytes(capture.encode(documents[key]))
        parent[role] = reference(path)
        for next_key in following:
            physical.replace_claim(documents[next_key], str(path), parent[role]['sha256'])
    return parent


class RootOriginalEvidenceTests(unittest.TestCase):
    def test_extra_fixed_host_evidence_pins_reject_before_any_read(self):
        for field in ('PREFIX_CORE', 'GAP_CORE'):
            with self.subTest(field=field), patch.object(capture, field, (getattr(capture, field)[0], None)), \
                    patch.object(capture, 'REGISTRATION_CORE', (capture.REGISTRATION_CORE[0], physical.REGISTRATION_SHA)), \
                    patch.object(capture, 'DEPENDENCIES', physical.dependencies()), \
                    patch.object(Path, 'read_bytes', side_effect=AssertionError('Pending host read')), \
                    self.assertRaises(ValueError):
                capture.run(registration_path='E:/synthetic/registration.json',
                            registration_sha256='a' * 64, execute=True)

    def test_equal_bytes_elsewhere_do_not_replace_namespace_evidence(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ROOT_V5_PATH_ATTACK_') as directory:
            root = Path(directory)
            research = root / 'research'
            research.mkdir()
            parent, _ = physical_gap_parent(root, research)
            old_path = Path(parent['reference']['path']).parent / 'QQQ.prefix_evidence.json'
            replacement = root / 'equal_evidence_elsewhere.json'
            replacement.write_bytes(old_path.read_bytes())
            forged = relocate_evidence(parent, old_path, replacement)
            # Structural acceptance proves this tests the IO association boundary.
            physical.view.inspect_parent_history_v5(envelope(forged))
            current = physical.current_files(root, forged, 'path_attack')
            with self.assertRaisesRegex(ValueError, 'prefix.*path|Prefix.*path|artifact.*path|Artifact.*path'):
                physical.run(root, research, forged, 'reject_relocated_evidence', current)
            self.assertFalse((research / 'reject_relocated_evidence').exists())
            from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as reader
            from test_ndx_registered_forward_capture_independent_readback_20261009_v2 import checkers
            checker, csv_reader = checkers()
            raw = {key: (reader.ROOT / path).read_bytes()
                   for key, (path, _) in reader.DEPENDENCIES.items()}
            sources = {}
            prefix = reader.private_prefix_checker(raw, sources)
            with self.assertRaises(ValueError):
                reader.verify_parent_chain(envelope(forged), checker, prefix, csv_reader, sources)


if __name__ == '__main__':
    unittest.main()
