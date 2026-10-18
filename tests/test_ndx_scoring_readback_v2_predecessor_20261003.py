from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from scripts import ndx_registered_scoring_queue_independent_readback_v2_20261003 as reader


def fixture(root):
    parent = root / 'failed'
    parent.mkdir()
    for i in range(53):
        (parent / f'shard_{i:04d}.json').write_bytes(b'{}')
    (parent / 'started.json').write_bytes(b'{}')
    failure = dict(status='FAILED_NO_RETRY_NOT_FINAL_AUTHORITY', error='Complete saved recovery evidence', completed_shard_audits_are_diagnostic_until_final_readback=True)
    (parent / 'failure.json').write_bytes(reader.enc(failure))
    source = root / 'old_reader.py'
    source.write_bytes(b'old immutable reader')
    hashes = {str(source): reader.filehash(source)}
    snapshot = dict(schema='FAILED_SCORING_READBACK_EVIDENCE_SNAPSHOT_V1', original_handle=20223, original_exit_code=1,
        failed_output_directory=str(parent), source_hashes=hashes,
        output_hashes={str(path): reader.filehash(path) for path in parent.iterdir()},
        exact_output_names=sorted(path.name for path in parent.iterdir()), diagnostic_shard_count=53,
        original_failure_reclassified=False, partial_reports_are_final_authority=False, optimization_rerun=False,
        score_recomputed=False, selection_allowed=False, failure_preserved=failure)
    manifest = root / 'snapshot.json'
    manifest.write_bytes(reader.enc(snapshot))
    return parent, source, manifest, snapshot, hashes


class Tests(unittest.TestCase):
    def test_pending_v2_inspector_stops_before_io(self):
        with patch.object(reader, 'INSPECTOR_SHA', None), patch.object(Path, 'read_bytes', side_effect=AssertionError('No source IO')):
            with self.assertRaisesRegex(ValueError, 'inspector anchor pending'):
                reader.readback(execute=True)

    def test_complete_failed_evidence_is_separate_and_stays_failed(self):
        with TemporaryDirectory() as tmp:
            parent, source, manifest, snapshot, hashes = fixture(Path(tmp))
            with patch.multiple(reader, FAILED_PARENT=parent, FAILED_SNAPSHOT=manifest, FAILED_SNAPSHOT_SHA=reader.filehash(manifest), FAILED_SOURCE_HASHES=hashes):
                document, sources = reader.load_failed_predecessor()
                self.assertEqual(document, snapshot)
                self.assertEqual(len(sources), 57)
                self.assertFalse(document['partial_reports_are_final_authority'])
                self.assertTrue((parent / 'failure.json').exists())
                reader.guard_failed_predecessor(sources)
                (parent / 'shard_0052.json').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'attempt changed'):
                    reader.guard_failed_predecessor(sources)

    def test_resigned_metadata_or_new_success_file_cannot_reclassify_old_failure(self):
        for attack in ('count_bool', 'authority', 'foreign_output', 'new_final'):
            with self.subTest(attack=attack), TemporaryDirectory() as tmp:
                parent, source, manifest, snapshot, hashes = fixture(Path(tmp))
                if attack == 'count_bool':
                    snapshot['diagnostic_shard_count'] = True
                elif attack == 'authority':
                    snapshot['partial_reports_are_final_authority'] = True
                elif attack == 'foreign_output':
                    snapshot['output_hashes'][str(source)] = hashes[str(source)]
                else:
                    (parent / 'independent_readback.json').write_bytes(b'{}')
                manifest.write_bytes(reader.enc(snapshot))
                with patch.multiple(reader, FAILED_PARENT=parent, FAILED_SNAPSHOT=manifest, FAILED_SNAPSHOT_SHA=reader.filehash(manifest), FAILED_SOURCE_HASHES=hashes):
                    with self.assertRaises(ValueError):
                        reader.load_failed_predecessor()


if __name__ == '__main__':
    unittest.main()
