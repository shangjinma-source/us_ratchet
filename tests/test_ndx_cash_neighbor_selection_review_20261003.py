"""Bounded selector contract review; no saved actual result consumption."""
import copy
import unittest
from unittest.mock import patch
from test_ndx_cash_neighbor_selection_research import fixture, ref, score, m


class SelectionReview(unittest.TestCase):
    def test_exact_tie_old_first_then_new_frozen_order(self):
        a = fixture()
        record = a['new_records'][0]
        for doc in (record['postcheck'], record['shard_audit']['document']['detail']['task_results'][0]):
            doc['original_target_stock_weight_l1'] = score(2)
        out = m.select_scenario(**a)
        self.assertEqual(out['selected']['origin'], 'OLD')
        self.assertEqual(out['status'], 'REUSE_EXISTING_PAIRED_PATH')
        a = fixture()
        second = copy.deepcopy(a['new_records'][0])
        second['task']['scenario_candidate_ordinal'] = 1
        second['task']['identity']['buy_shares'] = {'A': 4}
        second['task']['task_id'] = m.digest(second['task']['identity'])
        second['raw']['result']['branches'][0]['evaluated_plans'][0]['buy_shares'] = {'A': 4}
        second['shard_audit']['document']['detail']['task_results'][0]['task_id'] = second['task']['task_id']
        a['new_records'].append(second)
        a['expected_new_count'] = 2
        out = m.select_scenario(**a)
        self.assertEqual(out['selected']['buy_shares'], {'A': 3})
        self.assertEqual(out['total_candidate_count'], 4)
        self.assertFalse(out['candidate_ledger'][1]['feasible'])

    def test_aggregate_cannot_replace_complete_ledger_with_declared_counts(self):
        a = fixture()
        saved = m.select_scenario(**a)
        rows = []
        for i in range(40):
            row = copy.deepcopy(saved)
            row['scenario_id'] = 'case' + str(i)
            row['new_candidate_count'] = 301657 if i == 0 else 0
            row['total_candidate_count'] = row['old_candidate_count'] + row['new_candidate_count']
            rows.append(row)
        with self.assertRaises(ValueError):
            m.collect_selections(scenario_results=rows, expected_scenario_ids=[r['scenario_id'] for r in rows], full_audit=a['full_audit'])

    def test_external_first_audit_must_belong_to_full_saved_sources(self):
        a = fixture()
        record = a['new_records'][0]
        tid = record['task']['task_id']
        checked = record['shard_audit']['document']['detail']['task_results'][0]
        checked.update(outcome='EXTERNALLY_REFERENCED', new_arithmetic_checked=False)
        single_ref = ref(700)
        record['single_audit'] = dict(reference=single_ref, document=dict(schema='CASH_TOPUP_SINGLE_EVALUATION_INDEPENDENT_READBACK_V1', status='PASS', task_id=tid, returned_arithmetic_independently_verified=True, technical_failure_preserved=False, attempt_outcome='FEASIBLE', original_target_stock_weight_l1=score(1), raw_reference=record['references']['raw'], postcheck_reference=record['references']['postcheck']))
        a['full_audit']['document']['source_hashes'] = {r['path']: r['sha256'] for r in (single_ref, record['references']['raw'], record['references']['postcheck'])}
        with patch.object(m, 'FIRST_ID', tid):
            self.assertEqual(m.select_scenario(**a)['status'], 'NEW_PATH_REQUIRED')
            for role in ('single_audit', 'raw', 'postcheck'):
                bad = copy.deepcopy(a)
                source_ref = single_ref if role == 'single_audit' else record['references'][role]
                bad['full_audit']['document']['source_hashes'][source_ref['path']] = 'f' * 64
                with self.subTest(role=role), self.assertRaises(ValueError):
                    m.select_scenario(**bad)


if __name__ == '__main__':
    unittest.main()
