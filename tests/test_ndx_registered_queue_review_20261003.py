from copy import deepcopy
import unittest
from backtest import ndx_registered_scoring_queue_research as queue
import test_ndx_registered_scoring_queue_research as author_fixture


class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        author_fixture.Tests.setUpClass();cls.plan=author_fixture.Tests.plan;cls.reference=author_fixture.Tests.reference

    def test_per_k_selected_count_must_describe_actual_queue(self):
        plan=deepcopy(self.plan)
        for k,delta in [(4,1),(5,-1)]:
            card=plan['rows'][0]['domain_coverage'][k-1]
            card['selected_combination_count']+=delta
            card['unsearched_eligible_after_bounds']-=delta
        plan['content_sha256']=queue.digest({k:v for k,v in plan.items() if k!='content_sha256'})
        with self.assertRaises(ValueError):queue.build_registered_scoring_queue(budget_plan=plan,budget_reference=self.reference)

    def test_blocked_mode_not_removed_and_shards_do_not_reorder(self):
        result=queue.build_registered_scoring_queue(budget_plan=self.plan,budget_reference=self.reference)
        expected=[i for period in range(6) for i in range(period*3264+1632,(period+1)*3264)]
        self.assertEqual(result['executable_logical_ordinals'],expected)
        self.assertEqual([i for shard in result['shards'] for i in shard['logical_ordinals']],expected)
        for shard in result['shards']:
            self.assertEqual(shard['job_ids'],[result['logical_jobs'][i]['job_id'] for i in shard['logical_ordinals']])
        self.assertEqual(result['first_executable_job']['logical_ordinal'],1632)
        self.assertFalse(result['first_probe_removed_from_registered_domain'])

    def test_source_role_and_false_count_are_not_untyped_metadata(self):
        for attack in ('role','bool'):
            plan=deepcopy(self.plan)
            if attack=='role':plan['rows'][0]['mode_plans'][0]['source_preserved']['mode']='BACKWARD_LATEST_VALID_FX'
            else:plan['rows'][0]['domain_coverage'][0]['selected_combination_count']=False
            plan['content_sha256']=queue.digest({k:v for k,v in plan.items() if k!='content_sha256'})
            with self.assertRaises(ValueError):queue.build_registered_scoring_queue(budget_plan=plan,budget_reference=self.reference)


if __name__=='__main__':unittest.main()
