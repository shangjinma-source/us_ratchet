from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_selected_date_archive_diff_research as audit
from test_ndx_selected_date_overlay_diff_research import DiffTests


class ArchiveDiffTests(unittest.TestCase):
    def test_full_record_oracle_rejects_resigned_mutation(self):
        bundle = DiffTests().bundle()
        self.assertEqual(audit.pure.compare_records(*bundle)['selected_replaced'], 1)
        bundle[1]['records'][1]['result']['metric'] = 999
        bundle[1]['records_sha256'] = audit.pure.digest(bundle[1]['records'])
        with self.assertRaises(ValueError): audit.pure.compare_records(*bundle)

    def test_different_independent_index_rejected(self):
        path = str(Path('index.json').resolve()); reference = dict(path='manifest', sha256='a')
        manifest = dict(planned=2, tasks=[dict(new_job_id='a'), dict(new_job_id='b')])
        final = dict(schema='SELECTED_ARCHIVE_RESOLUTION_FINALIZATION_V1', completed=2, planned=2,
                     status='COMPLETE', immutable_numerical_source_closure_verified=True,
                     original_historical_provenance_verified=False, **dict.fromkeys(audit.scalar.FLAGS, False))
        index = dict(schema='SELECTED_ARCHIVE_RESOLUTION_COMPLETION_INDEX_V1', manifest=reference,
                     planned=2, status='COMPLETE', finalization=final,
                     completed=[dict(path='a.json'), dict(path='b.json')], **dict.fromkeys(audit.scalar.FLAGS, False))
        report = dict(schema=audit.scalar.SCHEMA, manifest=reference, completed=2, planned=2,
                      status='COMPLETE', completed_queue_all_tasks_audited=True,
                      completed_index=dict(path=path, sha256='x'), tasks=[dict(new_job_id='a'), dict(new_job_id='b')],
                      historical_expected_source_hashes={path: 'x'})
        self.assertEqual(audit.check_audit(index, manifest, report, index_path=path, index_sha256='x'), ['a', 'b'])
        for change in ('index', 'order', 'bool', 'status'):
            forged = deepcopy(report)
            if change == 'index': forged['completed_index']['sha256'] = 'y'
            if change == 'order': forged['tasks'].reverse()
            if change == 'bool': forged['completed'] = True
            if change == 'status': forged['status'] = 'PARTIAL'
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit.check_audit(index, manifest, forged, index_path=path, index_sha256='x')

    def test_atomic_publication_and_no_overwrite(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'report.json'
            with patch.object(audit, 'verify'), patch.object(audit.os, 'link', side_effect=OSError('injected')):
                with self.assertRaises(OSError): audit.publish_verified(target, {'x': 1})
            self.assertEqual(list(Path(folder).iterdir()), [])
            with patch.object(audit, 'verify'):
                audit.publish_verified(target, {'x': 1})
                before = target.read_bytes()
                with self.assertRaises(FileExistsError): audit.publish_verified(target, {'x': 2})
                self.assertEqual(before, target.read_bytes())

    def test_no_scope_upgrade(self):
        for key in audit.FLAGS:
            report = dict(schema=audit.SCHEMA, **dict.fromkeys(audit.FLAGS, False))
            report[key] = True
            with self.subTest(key=key), self.assertRaises(ValueError): audit.verify(report)

    def test_final_verify_checks_separate_loader_gap(self):
        report = dict(schema=audit.SCHEMA, historical_expected_source_hashes=dict(audit.LOADED),
                      output_path='bound-output', output_sha256='bound-sha', archive_resolution={},
                      historical_loader_gap_observations=[{'path': 'separate-config'}],
                      **dict.fromkeys(audit.FLAGS, False))
        report['historical_expected_source_hashes']['bound-output'] = 'bound-sha'
        with patch.object(audit.archive, 'load_contract'), patch.object(audit.archive, 'verify_expected_sources', return_value={}):
            with patch.object(audit.scalar.original, 'verify_gaps', side_effect=ValueError('changed config')) as checked:
                with self.assertRaisesRegex(ValueError, 'changed config'): audit.verify(report)
                checked.assert_called_once_with(report['historical_loader_gap_observations'])


if __name__ == '__main__': unittest.main()
