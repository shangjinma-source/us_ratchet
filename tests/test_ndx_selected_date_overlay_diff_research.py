from copy import deepcopy
import unittest
from scripts import ndx_selected_date_overlay_diff_research as audit


class DiffTests(unittest.TestCase):
    def bundle(self):
        task = dict(job_id='x', selection_date='2023-04-03', tickers=['GOOG'], holding_count=1, weight_spec='EQUAL')
        before = dict(task=task, origin='DELTA', status='PENDING_NUMERICAL_DELTA', result=None, lineage={'old': 1}, risk_flag=False)
        other = dict(task=dict(job_id='y'), origin='EQUAL', status='AVAILABLE', result={'metric': 2}, lineage={})
        parent = dict(records=[before, other], original_count=2, available_count=1, pending_count=1)
        saved = dict(result=dict(original_task=task, result=dict(metric=3, whole_lot_metric=4)))
        changed = deepcopy(before)
        changed.update(status='AVAILABLE', result=deepcopy(saved['result']['result']), overlay_mode='SELECTED_DELTA_COMPLETE_DATE', original_historical_provenance_verified=False)
        changed['lineage']['completed_selected_delta'] = {k: 'x' for k in audit.LINEAGE_KEYS}
        output = dict(schema='ndx_selected_complete_date_overlay_v1', records=[changed, deepcopy(other)],
            original_count=2, available_count=2, pending_count=0, selected_delta_added=1,
            counts={'DELTA': dict(planned=1, available=1, pending=0), 'EQUAL': dict(planned=1, available=1, pending=0)},
            economic_inputs_complete=True, winner=None)
        output['records_sha256'] = audit.digest(output['records'])
        return parent, output, [task], lambda lineage, task: saved

    def test_exact_ordered_complete_date(self):
        result = audit.compare_records(*self.bundle())
        self.assertEqual(result['selected_replaced'], 1)
        self.assertEqual(result['unrelated_records_exact'], 1)

    def test_unrelated_mutation_rejected_even_resigned(self):
        args = self.bundle(); args[1]['records'][1]['result']['metric'] = 99
        args[1]['records_sha256'] = audit.digest(args[1]['records'])
        with self.assertRaises(ValueError): audit.compare_records(*args)

    def test_forged_checkpoint_result_and_added_metadata_rejected(self):
        for mode in ('result', 'extra', 'lineage', 'order', 'missing'):
            args = self.bundle(); row = args[1]['records'][0]
            if mode == 'result': row['result']['metric'] = 999
            if mode == 'extra': row['unreviewed'] = True
            if mode == 'lineage': row['lineage']['completed_selected_delta']['extra'] = True
            if mode == 'order': args[1]['records'].reverse()
            if mode == 'missing': args[1]['records'][0] = deepcopy(args[0]['records'][0])
            args[1]['records_sha256'] = audit.digest(args[1]['records'])
            with self.subTest(mode=mode), self.assertRaises((ValueError, KeyError)): audit.compare_records(*args)

    def test_partial_date_denominator_rejected(self):
        args = self.bundle(); args[0]['records'].append(dict(task=dict(job_id='z'), status='PENDING_NUMERICAL_DELTA'))
        with self.assertRaises(ValueError): audit.compare_records(*args)


if __name__ == '__main__': unittest.main()
