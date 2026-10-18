from copy import deepcopy
from math import comb
from unittest.mock import patch
import unittest
from test_ndx_multidecision_scoring_budget_research import fixture
from backtest import ndx_multidecision_scoring_budget_research as m

def plan(reg,universe,decisions):
    return m.plan_multidecision_scoring_budget(registration=reg,registration_reference={'path':'policy.json','sha256':m.POLICY_SOURCE_SHA},universe=universe,decisions=decisions)

class Review(unittest.TestCase):
    def test_closed_form_full_denominator_and_source_independent_draw(self):
        reg,u,d=fixture();a=plan(reg,u,d);changed=deepcopy(d)
        for row in changed:
            row['mode_sources'][0]['complete_thirteen_windows']=True
            row['mode_sources'][0]['reference']={'path':'different-target','sha256':'f'*64}
            row['scoring_data_reference']={'path':'different-data','sha256':'e'*64}
        b=plan(reg,u,changed)
        for x,y in zip(a['rows'],b['rows']):
            self.assertEqual(x['sampling'],y['sampling']);self.assertEqual(x['draw_context'],y['draw_context'])
            self.assertEqual(len(x['domain_coverage']),76)
            for c in x['domain_coverage']:
                k=c['k'];n=(comb(75,k) if k<=75 else 0)+2*comb(75,k-1)
                self.assertEqual(c['full_inventory_combination_count'],n)
                self.assertEqual(sum(c[key] for key in ('qualification_excluded_combination_count','necessary_bound_excluded_combination_count','selected_combination_count','unsearched_eligible_after_bounds')),n)
                self.assertEqual(c['full_three_spec_task_denominator'],3*n)
            self.assertFalse(x['mode_plans'][0]['score_dispatch_authorized'])

    def test_full77_coverage_and_hard_proposal_stop(self):
        _,u,_=fixture();groups=m.group_rows(u);index=m.index_for(groups);cards=m.cards(index)
        context={'algorithm_version':m.ORDER,'seed_text':'independent-test','decision_cutoff':'2026-03-31','canonical_issuer_security_groups':groups,'static_budget':deepcopy(m.BUDGET)}
        full=m.sample_positions(index,context,cards)
        self.assertTrue(full['complete']);self.assertLessEqual(full['proposal_count'],4096)
        bysid={x['security_id']:x['issuer_id'] for x in u}
        for c in full['cardinality_coverage']:
            if c['requested_position_count']:
                self.assertEqual(c['selected_position_count'],32)
                self.assertEqual(len(c['security_exposures']),77)
                self.assertTrue(all(c['security_exposures'].values()))
        for p in full['positions']:self.assertEqual(len({bysid[s] for s in p['security_ids']}),p['k'])
        with patch.dict(m.BUDGET,{'max_proposals_per_decision':1}):stopped=m.sample_positions(index,context,cards)
        self.assertEqual(stopped['proposal_count'],1);self.assertFalse(stopped['complete'])
        self.assertEqual(stopped['status'],'INCOMPLETE_POINT_SELECTION')
        self.assertGreater(sum(c['unprocessed_requested_position_count'] for c in stopped['cardinality_coverage']),0)
        self.assertEqual(len(stopped['cardinality_coverage']),76)

    def test_no_eligible_subpool_substitution_or_threshold_override(self):
        reg,u,d=fixture()
        with self.assertRaises(ValueError):plan(reg,u[:8],d)
        for edit in (lambda q:q['mdv_evidence'].update(median_dollar_volume_exact='49999999'),
                     lambda q:q['mdv_evidence'].update(formal_eligibility_verified=0),
                     lambda q:q['mdv_evidence']['required_dates'].pop(),
                     lambda q:q.update(conditional_member_scope_passed=1)):
            bad=deepcopy(d);edit(bad[0]['qualifications'][0])
            with self.assertRaises(ValueError):plan(reg,u,bad)

if __name__=='__main__':unittest.main()
