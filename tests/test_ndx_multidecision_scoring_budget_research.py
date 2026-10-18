from copy import deepcopy
import math,unittest,json
from pathlib import Path
from datetime import date,timedelta
from backtest import ndx_multidecision_scoring_budget_research as m


def fixture():
    ref=dict(path='registered.json',sha256='a'*64)
    reg=json.loads(Path('research_contracts/multidecision_conditional_scoring_policy_20261003_v1.json').read_bytes())
    universe=[dict(security_id=f'S{i}',ticker=f'T{i}',issuer_id=f'I{i}',sector='ENERGY') for i in range(7)]+[dict(security_id='S76',ticker='T76',issuer_id='I0',sector='ENERGY')]+[dict(security_id=f'S{i}',ticker=f'T{i}',issuer_id=f'I{i}',sector='ENERGY') for i in range(7,76)]
    calendar=[];day=date(2023,1,2)
    while day<=date(2026,8,31):
        if day.weekday()<5:calendar.append(day.isoformat())
        day+=timedelta(days=1)
    decisions=[]
    for c in m.CUTOFFS:
        end=calendar.index(c);dates=calendar[end-504:end+1]
        q=[dict(security_id=u['security_id'],cutoff=c,history_13_complete=u in universe[:8],mdv_available=True,liquidity_passed=True,conditional_member_scope_passed=True,history_reference=ref,mdv_reference=ref,mdv_evidence=dict(coordinate=u,formal_eligibility_verified=False,required_dates=dates[-63:],median_dollar_volume_exact='50000000',status='CONDITIONAL_MDV_COMPUTABLE',conditional_numerical_threshold_passed=True),reasons=[]) for u in universe]
        decisions.append(dict(cutoff=c,scoring_price_dates=dates,incumbent_fee_reference=ref,scoring_data_reference=ref,fitter_source_reference=ref,qualifications=q,mode_sources=[dict(mode=mode,complete_thirteen_windows=mode==m.MODES[1],reference=ref) for mode in m.MODES]))
    return reg,universe,decisions


class Tests(unittest.TestCase):
    def test_full_domain_and_same_combinations_two_modes(self):
        r,u,d=fixture();out=m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=d)
        for row in out['rows']:
            self.assertTrue(row['sampling']['complete']);self.assertLessEqual(row['sampling']['proposal_count'],4096)
            for card in row['domain_coverage']:
                k=card['k'];want=(math.comb(75,k) if k<=75 else 0)+2*math.comb(75,k-1)
                self.assertEqual(card['full_inventory_combination_count'],want)
                self.assertEqual(want,card['qualification_excluded_combination_count']+card['necessary_bound_excluded_combination_count']+card['selected_combination_count']+card['unsearched_eligible_after_bounds'])
            a,b=row['mode_plans'];self.assertEqual(a['status'],'SOURCE_BLOCKED');self.assertEqual(b['status'],'PLANNED_NOT_ATTEMPTED')
            self.assertEqual([(x['identity']['security_ids'],x['identity']['weight_spec']) for x in a['tasks']],[(x['identity']['security_ids'],x['identity']['weight_spec']) for x in b['tasks']])
            self.assertNotEqual(a['tasks'][0]['job_id'],b['tasks'][0]['job_id'])
            self.assertTrue(all(not({'S0','S76'}<=set(x['identity']['security_ids'])) for x in a['tasks']))
    def test_price_artifact_changes_ids_never_draws(self):
        r,u,d=fixture();a=m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=d)
        changed=deepcopy(d)
        for x in changed:x['scoring_data_reference']['sha256']='c'*64
        b=m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=changed)
        for x,y in zip(a['rows'],b['rows']):
            self.assertEqual(x['draw_context'],y['draw_context']);self.assertEqual(x['sampling'],y['sampling']);self.assertNotEqual(x['mode_plans'][1]['tasks'][0]['job_id'],y['mode_plans'][1]['tasks'][0]['job_id'])
    def test_unknown_history_mdv_retains_whole_inventory(self):
        r,u,d=fixture();d[0]['qualifications'][0].update(history_13_complete=False,reasons=['FLOOR']);d[0]['qualifications'][1].update(mdv_available=False,liquidity_passed=None,reasons=['UNKNOWN_UNITS']);d[0]['qualifications'][1]['mdv_evidence'].update(median_dollar_volume_exact=None,status='UNKNOWN_LIQUIDITY',conditional_numerical_threshold_passed=None)
        out=m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=d);row=out['rows'][0]
        self.assertEqual(row['universe_preserved'],u);self.assertEqual(len(row['excluded_securities']),71);self.assertNotIn('S0',row['eligible_security_ids']);self.assertEqual(len(row['full_inventory_cardinalities']),76)
        for q in d[0]['qualifications']:q['history_13_complete']=False
        row=m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=d)['rows'][0]
        self.assertEqual(row['sampling']['status'],'NO_SCORABLE_SECURITIES');self.assertEqual(row['mode_plans'][1]['tasks'],[])
    def test_exact_mdv_threshold_and_fee_identity(self):
        r,u,d=fixture();q=d[0]['qualifications'][0]
        q['mdv_evidence'].update(median_dollar_volume_exact='499999999/10',conditional_numerical_threshold_passed=False);q['liquidity_passed']=False
        out=m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=d)
        self.assertNotIn('S0',out['rows'][0]['eligible_security_ids'])
        job=out['rows'][1]['mode_plans'][1]['tasks'][0]['identity']
        self.assertIsNone(job['internal_initial_previous_weights']);self.assertEqual(job['candidate_transaction_cost_bps'],10)
        self.assertEqual(job['first_candidate_fee_reference'],d[1]['incumbent_fee_reference'])
        self.assertFalse(job['outer_lane_prior_applied'])
        q['liquidity_passed']=True
        with self.assertRaises(ValueError):m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=d)

    def test_contract_strict_types_and_qualification_date(self):
        r,u,d=fixture()
        for edit in (lambda v:v[0]['qualifications'][0].update(history_13_complete=1),lambda v:v[0]['qualifications'][0].update(cutoff='2026-09-21'),lambda v:v[0]['mode_sources'].reverse(),lambda v:v[0]['qualifications'].pop(),lambda v:v[0]['qualifications'][0].update(mdv_available=False,liquidity_passed=True)):
            bad=deepcopy(d);edit(bad)
            with self.assertRaises(ValueError):m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=bad)
        r['budget']['maximum_proposals_per_decision']=4095
        with self.assertRaises(ValueError):m.plan_multidecision_scoring_budget(registration=r,registration_reference=dict(path='policy.json',sha256=m.POLICY_SOURCE_SHA),universe=u,decisions=d)

if __name__=='__main__':unittest.main()
