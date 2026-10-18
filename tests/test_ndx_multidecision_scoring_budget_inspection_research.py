from copy import deepcopy
import unittest
from backtest import ndx_multidecision_scoring_budget_inspection_research as a
from backtest import ndx_multidecision_scoring_budget_research as p
from test_ndx_multidecision_scoring_budget_research import fixture


def case():
    r,u,d=fixture()
    args=dict(registration=r,registration_reference=dict(path='policy.json',sha256=a.POLICY_SHA),universe=u,decisions=d)
    return args,p.plan_multidecision_scoring_budget(**args)


def resign(plan):
    plan.pop('content_sha256',None);plan['content_sha256']=a.digest(plan)


class Tests(unittest.TestCase):
    def test_complete_two_modes_full_domain(self):
        args,plan=case();before=deepcopy(plan)
        self.assertEqual(a.inspect_scoring_budget(**args,saved_plan=plan)['status'],'PASS')
        self.assertEqual(plan,before)
        self.assertEqual(plan['rows'][0]['mode_plans'][0]['status'],'SOURCE_BLOCKED')
        for row in plan['rows']:
            for c in row['domain_coverage']:
                self.assertEqual(c['full_inventory_combination_count'],sum(c[x] for x in ('qualification_excluded_combination_count','necessary_bound_excluded_combination_count','selected_combination_count','unsearched_eligible_after_bounds')))

    def test_resigned_proposal_job_denominator_attacks(self):
        args,plan=case()
        changes=[lambda x:x['rows'][0]['sampling']['proposal_log'].pop(),
                 lambda x:x['rows'][0]['sampling']['positions'][0]['security_ids'].reverse(),
                 lambda x:x['rows'][0]['draw_context'].update(future_source_hash='a'*64),
                 lambda x:x['rows'][0]['mode_plans'][0]['tasks'][0]['identity'].__setitem__('fitter_source_reference',{'path':'old25','sha256':'c'*64}),
                 lambda x:x['rows'][0]['mode_plans'][0]['tasks'].pop(),
                 lambda x:x['rows'][0]['domain_coverage'][20].__setitem__('necessary_bound_excluded_combination_count',1),
                 lambda x:x.__setitem__('source_bytes_authenticated',0)]
        for change in changes:
            v=deepcopy(plan);change(v);resign(v)
            with self.assertRaises(ValueError):a.inspect_scoring_budget(**args,saved_plan=v)

    def test_unknown_pool_and_inputs(self):
        args,_=case()
        for q in args['decisions'][0]['qualifications']:q['history_13_complete']=False
        plan=p.plan_multidecision_scoring_budget(**args)
        self.assertEqual(a.inspect_scoring_budget(**args,saved_plan=plan)['status'],'PASS')
        args['decisions'][0]['qualifications'][0]['history_13_complete']=0
        with self.assertRaises(ValueError):a.inspect_scoring_budget(**args,saved_plan=plan)


if __name__=='__main__':unittest.main()

