from copy import deepcopy
import unittest

from backtest import ndx_registered_scoring_queue_research as queue
from backtest import ndx_multidecision_scoring_budget_research as budget
from test_ndx_multidecision_scoring_budget_research import fixture


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        registration, universe, decisions = fixture()
        for decision in decisions:
            for qualification in decision['qualifications']:
                qualification['history_13_complete'] = True
        cls.plan = budget.plan_multidecision_scoring_budget(
            registration=registration, registration_reference=dict(path='policy', sha256=budget.POLICY_SOURCE_SHA),
            universe=universe, decisions=decisions)
        cls.reference = dict(path='sealed/plan.json', sha256='b' * 64)

    def test_all_tasks_blocked_partition_shards_and_first_probe_slot_preserved(self):
        result = queue.build_registered_scoring_queue(budget_plan=self.plan, budget_reference=self.reference)
        self.assertEqual((result['logical_job_count'], result['executable_job_count'], result['source_blocked_job_count']),
                         (19584, 9792, 9792))
        self.assertEqual(result['shard_count'], 306)
        first = result['first_executable_job']
        self.assertEqual(first['logical_ordinal'], 1632)
        self.assertEqual(first['execution_ordinal'], 0)
        self.assertEqual(first['job_id'], result['shards'][0]['job_ids'][0])
        self.assertEqual([i for shard in result['shards'] for i in shard['logical_ordinals']],
                         result['executable_logical_ordinals'])
        self.assertTrue(all(len(shard['job_ids']) == 32 for shard in result['shards']))
        self.assertEqual(len(set(result['source_blocked_logical_ordinals']) & set(result['executable_logical_ordinals'])), 0)
        self.assertFalse(result['first_probe_removed_from_registered_domain'])
        self.assertFalse(result['execution_authorized'])

    def test_resigned_missing_changed_or_duplicated_task_rejected(self):
        for attack in ('missing', 'duplicate', 'status', 'domain'):
            plan = deepcopy(self.plan)
            jobs = plan['rows'][0]['mode_plans'][1]['tasks']
            if attack == 'missing':
                jobs.pop()
                plan['rows'][0]['mode_plans'][1]['task_count'] -= 1
            elif attack == 'duplicate':
                jobs[1] = deepcopy(jobs[0])
            elif attack == 'status':
                jobs[0]['status'] = 'SOURCE_BLOCKED'
            else:
                plan['rows'][0]['domain_coverage'][0]['full_inventory_combination_count'] -= 1
            plan['content_sha256'] = queue.digest({k: v for k, v in plan.items() if k != 'content_sha256'})
            with self.assertRaises(ValueError):
                queue.build_registered_scoring_queue(budget_plan=plan, budget_reference=self.reference)

    def test_engineering_queue_can_preserve_both_modes_when_both_sources_complete(self):
        plan = deepcopy(self.plan)
        for row in plan['rows']:
            mode = row['mode_plans'][0]
            mode['source_preserved']['complete_thirteen_windows'] = True
            mode['status'] = 'PLANNED_NOT_ATTEMPTED'
            for job in mode['tasks']:
                job['status'] = 'PLANNED_NOT_ATTEMPTED'
        plan['content_sha256'] = queue.digest({k: v for k, v in plan.items() if k != 'content_sha256'})
        result = queue.build_registered_scoring_queue(budget_plan=plan, budget_reference=self.reference)
        self.assertEqual(result['executable_job_count'], 19584)
        self.assertEqual(result['source_blocked_job_count'], 0)
        self.assertEqual(result['first_executable_job']['fx_mode'], 'STRICT_SAME_SESSION_FX')


if __name__ == '__main__':
    unittest.main()
