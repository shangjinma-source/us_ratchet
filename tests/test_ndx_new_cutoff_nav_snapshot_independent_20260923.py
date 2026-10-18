"""Independent snapshot persistence checks, temporary directories only."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_nav_snapshot_20260923 as m


def frozen_input(name):
    # Replay the exact original bytes preserved by the sealed snapshot.
    raw = (m.ROOT / 'data/cache/research/new_cutoff_nav_snapshot_20260923_v1' / name).read_bytes()
    if m.digest(raw) != m.INPUTS[name][1]:
        raise ValueError('Frozen NAV fixture differs from original input SHA')
    return raw


class IndependentSnapshotTests(unittest.TestCase):
    def fixture(self, directory, stack):
        base = Path(directory)
        inputs = {}
        for name, (original, digest) in m.INPUTS.items():
            path = base / name
            path.write_bytes(frozen_input(name))
            inputs[name] = (path, digest)
        output = base / 'snapshot'
        stack.enter_context(patch.object(m, 'INPUTS', inputs))
        stack.enter_context(patch.object(m, 'OUTPUT', output))
        return inputs, output

    def test_snapshot_dependencies_exclude_mutable_originals(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            inputs, output = self.fixture(directory, stack)
            ref = m.run()
            report = json.loads(Path(ref['path']).read_bytes())
            self.assertEqual(set(report['source_hashes']), {str(m.SOURCE), str(output/'nav.csv'), str(output/'original_manifest.json')})
            for path, digest in inputs.values():
                self.assertNotIn(str(path), report['source_hashes'])
                path.write_bytes(b'changed after capture')
            for name, copy in report['immutable_copies'].items():
                self.assertEqual(m.digest(Path(copy['path']).read_bytes()), copy['sha256'])
            self.assertFalse(report['calendar_mapped'])
            self.assertFalse(report['returns_calculated'])

    def test_original_drift_after_first_copy_refuses_success(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            inputs, output = self.fixture(directory, stack)
            original_publish = m.publish_bytes
            def publish(path, raw):
                result = original_publish(path, raw)
                if path.name == 'nav.csv': inputs['nav.csv'][0].write_bytes(b'drift')
                return result
            with patch.object(m, 'publish_bytes', side_effect=publish), self.assertRaisesRegex(ValueError, 'Original local NAV input changed'):
                m.run()
            self.assertFalse((output/'snapshot.json').exists())
            with self.assertRaisesRegex(ValueError, 'Fresh fixed'): m.run()

    def test_copy_tamper_and_orphan_during_publication_refuse_success(self):
        for attack in ('copy', 'orphan'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                inputs, output = self.fixture(directory, stack)
                original_publish = m.publish_bytes
                def publish(path, raw):
                    result = original_publish(path, raw)
                    if path.name == 'snapshot.json':
                        (output/('nav.csv' if attack == 'copy' else 'unknown.json')).write_bytes(b'tampered')
                    return result
                with patch.object(m, 'publish_bytes', side_effect=publish), self.assertRaises(ValueError): m.run()

    def test_duplicate_json_and_close_convention_fail_closed(self):
        raw = frozen_input('nav.csv')
        metadata = frozen_input('original_manifest.json')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            m.validate(raw, b'{"fund_code":"012922",' + metadata.lstrip()[1:])
        lines = raw.decode().splitlines()
        fields = lines[1].split(',')
        fields[-1] = '2.123456'
        lines[1] = ','.join(fields)
        changed = ('\n'.join(lines)+'\n').encode()
        manifest = json.loads(metadata)
        manifest.update(content_sha256=m.digest(changed), content_bytes=len(changed))
        with self.assertRaisesRegex(ValueError, 'unit NAV convention'):
            m.validate(changed, json.dumps(manifest).encode())


if __name__ == '__main__': unittest.main()
