from copy import deepcopy
import unittest
from scripts import ndx_base_limited_overlay_diff_audit_research as audit
from backtest.ndx_corrected_base_overlay_research import extend_base_overlay
from test_ndx_corrected_base_overlay_research import fixture


class FullDiffTests(unittest.TestCase):
    def case(self):
        parent, replacements = fixture()
        parent['coordinate'] = {'selection_date': '2023-07-03'}
        parent['records_sha256'] = audit.records_digest(parent['records'])
        replacements[0]['lineage'] = dict(checkpoint_path='p', checkpoint_sha256='s', complete_index_path='i',
            complete_index_sha256='is', independent_audit_path='a', independent_audit_sha256='as')
        new = extend_base_overlay(parent=parent, replacements=replacements, expected_base_job_ids=['base'])
        saved = dict(new_job_id='new', result=dict(evaluation=dict(result=deepcopy(new['records'][0]['result'])), cache_checkpoint_sha256='old'))
        return parent, new, lambda lineage: saved

    def check(self, old, new, read, pairs):
        return audit.check_records(old, new, read, pairs, {'new': old['records'][0]['task']})

    def test_all_ordered_rows_and_full_checkpoint_result_match(self):
        old, new, read = self.case()
        result = self.check(old, new, read, {('p', 's')})
        self.assertEqual(result, dict(original_count=3, replaced_base_pending=1, other_records_exact=2,
                                     available_count=2, pending_count=1))

    def test_unrelated_change_missing_replacement_and_counterfeit_result_rejected(self):
        for change, message in [('other', 'Unrelated'), ('missing', 'replacement missing'), ('number', 'checkpoint result')]:
            old, new, read = self.case()
            if change == 'other':
                new['records'][2]['result']['unchanged'] = 'tampered'
            elif change == 'missing':
                new['records'][0] = deepcopy(old['records'][0])
            else:
                new['records'][0]['result']['return_p50'] += 0.01
            new['records_sha256'] = audit.records_digest(new['records'])
            with self.assertRaisesRegex(ValueError, message):
                self.check(old, new, read, {('p', 's')})

    def test_unindexed_result_and_wrong_origin_counts_rejected(self):
        old, new, read = self.case()
        with self.assertRaisesRegex(ValueError, 'absent from external'):
            self.check(old, new, read, set())
        new['counts']['NON_EQUAL_BASE']['available'] += 1
        with self.assertRaisesRegex(ValueError, 'Per-origin counts'):
            self.check(old, new, read, {('p', 's')})

    def test_boolean_cannot_impersonate_numeric_checkpoint_value(self):
        old, new, read = self.case()
        read(None)['result']['evaluation']['result']['return_p50'] = 1.0
        new['records'][0]['result']['return_p50'] = True
        new['records_sha256'] = audit.records_digest(new['records'])
        with self.assertRaisesRegex(ValueError, 'checkpoint result'):
            self.check(old, new, read, {('p', 's')})

    def test_wrong_full_task_and_extra_lineage_rejected(self):
        old, new, read = self.case()
        with self.assertRaisesRegex(ValueError, 'task identity'):
            audit.check_records(old, new, read, {('p', 's')}, {'new': dict(old['records'][0]['task'], holding_count=9)})
        new['records'][0]['lineage']['completed_base_delta']['extra_claim'] = 'not validated'
        with self.assertRaisesRegex(ValueError, 'lineage fields'):
            self.check(old, new, read, {('p', 's')})


if __name__ == '__main__':
    unittest.main()
