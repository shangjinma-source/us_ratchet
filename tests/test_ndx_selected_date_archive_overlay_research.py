from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import ndx_selected_date_archive_overlay_research as m


def prefix():
    tasks = [dict(new_job_id=str(i), task=dict(selection_date='2023-04-03' if i < 2 else '2023-05-01', job_id=str(i))) for i in range(3)]
    reference = dict(path='archive_manifest.json', sha256='x')
    flags = dict.fromkeys(m.audited_archive.FLAGS, False)
    final = dict(schema='SELECTED_ARCHIVE_RESOLUTION_FINALIZATION_V1', completed=2, planned=3, status='PARTIAL',
                 immutable_numerical_source_closure_verified=True, original_historical_provenance_verified=False, **flags)
    index = dict(schema='SELECTED_ARCHIVE_RESOLUTION_COMPLETION_INDEX_V1', manifest=reference, planned=3,
                 completed=[dict(path=str(i)+'.json', sha256='x') for i in range(2)], status='PARTIAL', finalization=final, **flags)
    audited = [dict(**t, scalar_max_error=0., all_windows_max_error=0., legacy_close_max_error=0.,
                    saved_non20_fields_independently_recomputed=False, binary_float_ledger_hash_independently_verified=False) for t in tasks[:2]]
    audit = dict(schema=m.audited_archive.SCHEMA, planned=3, completed=2, status='PARTIAL',
                 completed_queue_all_tasks_audited=True, manifest=reference, tasks=audited)
    return index, audit, dict(tasks=tasks, planned=3)


class Tests(unittest.TestCase):
    def test_complete_date_in_finalized_partial_prefix(self):
        index, audit, manifest = prefix()
        self.assertEqual(len(m.complete_date_rows(index, audit, manifest, '2023-04-03')), 2)
        with self.assertRaises(ValueError): m.complete_date_rows(index, audit, manifest, '2023-05-01')

    def test_partial_duplicate_wrong_audit_nonfinite_and_claim_upgrade(self):
        for defect in ('partialdate', 'no_final', 'duplicate', 'wrongtask', 'bool', 'nan', 'scope', 'oldschema'):
            index, audit, manifest = prefix()
            if defect == 'partialdate': manifest['tasks'][2]['task']['selection_date'] = '2023-04-03'
            if defect == 'no_final': index['finalization'] = None
            if defect == 'duplicate': index['completed'][1] = dict(index['completed'][0])
            if defect == 'wrongtask': audit['tasks'][0]['task'] = dict(job_id='fake')
            if defect == 'bool': audit['tasks'][0]['scalar_max_error'] = False
            if defect == 'nan': audit['tasks'][0]['all_windows_max_error'] = float('nan')
            if defect == 'scope': audit['tasks'][0]['saved_non20_fields_independently_recomputed'] = True
            if defect == 'oldschema': audit['schema'] = 'SELECTED_COMPLETED_QUEUE_INDEPENDENT_SCALAR_DECIMAL_AUDIT_V1'
            with self.subTest(defect=defect), self.assertRaises(ValueError): m.complete_date_rows(index, audit, manifest, '2023-04-03')

    def test_parent_sealed_gap_not_live_observation_and_verified_omission(self):
        gap = dict(expected_historical_sha256='old', observed_current_sha256='sealed')
        parent = dict(historical_expected_source_hashes={'gap.csv':'old', 'raw.json':'raw'}, verified_source_hashes={'raw.json':'raw'},
                      historical_price_cache_gap_observations=[dict(gap, path='gap.csv', historical_bytes_verified=False, current_observation_unchanged=True)])
        with patch.object(m.drift, 'load_contract', return_value=dict(exceptions={'gap.csv':gap})), patch.object(m.archive, 'verify_expected_sources') as check:
            m.verify_parent_partition(parent, {})
            self.assertEqual(check.call_args.args[0], {'gap.csv':'old', 'raw.json':'raw'})
            altered = deepcopy(parent); altered['historical_price_cache_gap_observations'][0]['observed_current_sha256'] = 'today'
            with self.assertRaises(ValueError): m.verify_parent_partition(altered, {})
            altered = deepcopy(parent); altered['verified_source_hashes'].clear()
            with self.assertRaises(ValueError): m.verify_parent_partition(altered, {})

    def test_output_cannot_claim_old_live_map_or_omit_loaded_code(self):
        required = dict(m.LOADED, **{str(m.INVENTORY):m.INVENTORY_SHA, str(m.PLAN):m.PLAN_SHA, str(m.MANIFEST):m.MANIFEST_SHA})
        value = dict(historical_expected_source_hashes=required, source_resolution_schema=m.RESOLUTION_SCHEMA, verified_source_hashes={})
        with self.assertRaisesRegex(ValueError, 'Explicit archive'): m.verify(value)
        value.pop('verified_source_hashes'); value['historical_expected_source_hashes'] = {}
        with self.assertRaisesRegex(ValueError, 'Missing loaded'): m.verify(value)


if __name__ == '__main__': unittest.main()
