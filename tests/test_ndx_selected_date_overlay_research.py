from copy import deepcopy
import unittest
from backtest import ndx_selected_date_overlay_research as core
from scripts import ndx_selected_date_overlay_research as reader


class SelectedDateTests(unittest.TestCase):
    def bundle(self):
        tasks = [dict(job_id=str(i), tickers=['GOOG'], holding_count=1, weight_spec='EQUAL', selection_date='2023-04-03') for i in range(2)]
        records = [dict(task=t, origin='DELTA', status='PENDING_NUMERICAL_DELTA', result=None, lineage={}) for t in tasks]
        records.append(dict(task=dict(job_id='untouched'), origin='EQUAL', status='AVAILABLE', result={'risk': False}, lineage={'old': 'x'}))
        parent = dict(schema='ndx_corrected_base_overlay_limited_drift_v3', records=records, original_count=3,
            available_count=1, pending_count=2, historical_full_source_closure_verified=False,
            point_in_time_verified=False, promotion_allowed=False, selection_performed=False)
        replacements = []
        for t in tasks:
            result = dict(tickers=t['tickers'], holding_count=1, weight_spec='EQUAL', whole_lot_return=0.1,
                **{k: 0.2 for k in core.ECONOMIC_KEYS})
            lineage = {k: 'x' for k in ('checkpoint_path', 'checkpoint_sha256', 'complete_prefix_index_path',
                'complete_prefix_index_sha256', 'independent_audit_path', 'independent_audit_sha256')}
            replacements.append(dict(task=t, result=result, original_result=deepcopy(result), lineage=lineage))
        return dict(parent=parent, replacements=replacements, expected_tasks=tasks)

    def test_complete_date_preserves_unrelated_and_not_auth(self):
        args = self.bundle(); original = deepcopy(args)
        result = core.extend_selected_date(**args)
        self.assertEqual(args, original)
        self.assertEqual(result['records'][-1], args['parent']['records'][-1])
        self.assertEqual((result['available_count'], result['pending_count']), (3, 0))
        self.assertFalse(result['input_artifact_binding_verified'])
        self.assertFalse(result['promotion_allowed'])

    def test_partial_or_spoofed_task_cannot_be_complete_date(self):
        for mode in ('partial', 'missing', 'identity', 'lineage', 'nonfinite'):
            args = self.bundle()
            if mode == 'partial': args['expected_tasks'] = args['expected_tasks'][:1]
            if mode == 'missing': args['replacements'].pop()
            if mode == 'identity': args['replacements'][0]['result']['tickers'] = ['MSFT']
            if mode == 'lineage': args['replacements'][0]['lineage']['unreviewed'] = True
            if mode == 'nonfinite': args['replacements'][0]['result']['return_p50'] = float('nan')
            with self.subTest(mode=mode), self.assertRaises(ValueError): core.extend_selected_date(**args)

    def prefix(self):
        tasks = [dict(new_job_id=str(i), task=dict(selection_date='2023-04-03' if i < 2 else '2023-05-01', job_id=str(i))) for i in range(3)]
        flags = {k: False for k in reader.FLAGS}
        final = dict(schema='ndx_selected_delta_exact_gap_finalization_v1', planned=3, completed=2,
            status='PARTIAL', immutable_numerical_source_closure_verified=True, **flags)
        index = dict(schema='ndx_selected_delta_exact_gap_completion_index_v1', planned=3, status='PARTIAL',
            manifest=dict(path=str(reader.MANIFEST), sha256=reader.MANIFEST_SHA), finalization=final,
            completed=[dict(path=str(i), sha256=str(i)) for i in range(2)], **flags)
        audited = [dict(**t, scalar_max_error=0.0, all_windows_max_error=0.0, legacy_close_max_error=0.0,
            saved_non20_fields_independently_recomputed=False, binary_float_ledger_hash_independently_verified=False) for t in tasks[:2]]
        audit = dict(schema='SELECTED_COMPLETED_QUEUE_INDEPENDENT_SCALAR_DECIMAL_AUDIT_V1', planned=3,
            completed=2, status='PARTIAL', completed_queue_all_tasks_audited=True, tasks=audited)
        return index, audit, dict(tasks=tasks)

    def test_global_partial_can_have_complete_date(self):
        index, audit, manifest = self.prefix()
        self.assertEqual(len(reader.complete_date_rows(index, audit, manifest, '2023-04-03')), 2)
        with self.assertRaises(ValueError): reader.complete_date_rows(index, audit, manifest, '2023-05-01')

    def test_partial_date_audit_task_or_error_rejected(self):
        for mode in ('date', 'identity', 'error', 'count'):
            index, audit, manifest = self.prefix()
            if mode == 'date': manifest['tasks'][2]['task']['selection_date'] = '2023-04-03'
            if mode == 'identity': audit['tasks'][0]['task'] = dict(job_id='fake')
            if mode == 'error': audit['tasks'][0]['scalar_max_error'] = 1e-3
            if mode == 'count': audit['completed'] = 1
            with self.subTest(mode=mode), self.assertRaises(ValueError): reader.complete_date_rows(index, audit, manifest, '2023-04-03')


if __name__ == '__main__': unittest.main()
