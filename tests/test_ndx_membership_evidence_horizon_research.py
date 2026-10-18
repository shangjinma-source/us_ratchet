"""Synthetic evidence assertions only; no source authentication or real eligibility."""
from copy import deepcopy
import unittest
from backtest import ndx_membership_evidence_horizon_research as m


def fixture():
    def evidence(name, **fields):
        return dict(source_reference=dict(path='synthetic/'+name, sha256='a'*64), available_date='2026-03-19', authenticated=True, index_symbol='NDX', **fields)
    return dict(security_id='S_A', issuer_id='I_A', decision_cutoff='2026-09-20', decision_session='2026-09-21', required_start='2026-03-20', required_end='2026-09-21',
        baseline_evidence=evidence('baseline', as_of='2026-03-19', complete=True),
        event_coverage_evidence=evidence('events', start='2026-03-19', end='2026-09-21', complete=True, covered_intervals=[dict(start='2026-03-19',end='2026-09-21')]),
        membership_evidence=evidence('member', security_id='S_A', issuer_id='I_A', status='MEMBER',effective_start='2026-03-19',effective_end='2026-09-21'),
        unresolved_cases=[],eligibility_checks=dict(identity=True,liquidity=True,risk=True))


def gral():
    return dict(source_reference=dict(path='synthetic/gral',sha256='b'*64),original_case=dict(case_id='gral', ticker='GRAL', blocked_selection_start='2024-06-24',blocked_selection_end='2026-03-31',promotion_allowed=False,scope_lock='exact_addition_supported_removal_unresolved',exact_addition_supported=True,exact_removal_date_supported=False,notes='original untouched'))


class Tests(unittest.TestCase):
    def test_supplied_claims_never_produce_certification(self):
        a=fixture();before=deepcopy(a);r=m.evaluate_membership_evidence_horizon(**a)
        self.assertEqual(r['supplied_authentication_claims'],dict(baseline=True,events=True,membership=True))
        self.assertEqual(r['authentication_claims_origin'],'SUPPLIED_EXTERNAL_ASSERTIONS_NOT_AUTHENTICATED_BY_THIS_MODULE')
        self.assertTrue(r['eligible']);self.assertEqual(r['membership_status'],'MEMBER_UNDER_SUPPLIED_ATTESTATIONS')
        self.assertFalse(r['formal_eligibility_authorized']);self.assertFalse(r['point_in_time_certification_created']);self.assertFalse(r['source_authenticity_reverified']);self.assertFalse(r['promotion_allowed']);self.assertFalse(r['execution_authorized']);self.assertEqual(a,before)
    def test_absent_baseline_or_coverage_never_infers_complete(self):
        for key in ('baseline_evidence','event_coverage_evidence','membership_evidence'):
            a=fixture();a[key]=None;r=m.evaluate_membership_evidence_horizon(**a)
            self.assertEqual(r['membership_status'],'UNKNOWN');self.assertIsNone(r['eligible'])
    def test_dates_availability_and_future_effectiveness(self):
        for attack in ('baseline_asof','baseline_future','events_future','member_future','announced_future','coverage_end','chain_start'):
            a=fixture()
            if attack=='baseline_asof':a['baseline_evidence']['as_of']='2026-03-21'
            elif attack=='baseline_future':a['baseline_evidence']['available_date']='2026-09-21'
            elif attack=='events_future':a['event_coverage_evidence']['available_date']='2026-09-21'
            elif attack=='member_future':a['membership_evidence']['available_date']='2026-09-21'
            elif attack=='announced_future':a['membership_evidence'].update(effective_start='2026-09-22',effective_end='2026-09-23')
            elif attack=='coverage_end':
                a['event_coverage_evidence']['end']='2026-03-31';a['event_coverage_evidence']['covered_intervals'][0]['end']='2026-03-31'
            else:
                a['event_coverage_evidence']['start']='2026-03-20';a['event_coverage_evidence']['covered_intervals'][0]['start']='2026-03-20'
            with self.subTest(attack=attack):self.assertEqual(m.evaluate_membership_evidence_horizon(**a)['membership_status'],'UNKNOWN')
    def test_gral_end_is_not_removal_proof(self):
        for day in ('2026-03-31','2026-04-01','2026-09-21'):
            a=fixture();a.update(required_start=day,required_end=day,decision_session=day,decision_cutoff=day,unresolved_cases=[gral()]);before=deepcopy(a['unresolved_cases'])
            r=m.evaluate_membership_evidence_horizon(**a)
            self.assertEqual(r['membership_status'],'UNKNOWN');self.assertEqual(r['original_unresolved_cases'],before)
            self.assertFalse(r['membership_interval_extended_from_gap'])
            if day>'2026-03-31':self.assertEqual(r['known_active_gap_ids'],[]);self.assertEqual(r['unresolved_removal_outside_saved_scope_ids'],['gral'])
    def test_ceg_known_day_does_not_block_other_dates_or_prove_pool(self):
        a=fixture();a['unresolved_cases']=[dict(source_reference=dict(path='synthetic/ceg',sha256='b'*64),original_case=dict(case_id='ceg',blocked_selection_start='2022-02-02',blocked_selection_end='2022-02-02',promotion_allowed=False,scope_lock='exclude_effective_day_until_source_available'))]
        r=m.evaluate_membership_evidence_horizon(**a);self.assertEqual(r['blocking_case_ids'],[])
        self.assertFalse(r['full_pool_completeness_certified'])
        a['baseline_evidence']=None;self.assertEqual(m.evaluate_membership_evidence_horizon(**a)['membership_status'],'UNKNOWN')
    def test_nonmember_and_other_gates_are_not_inferred_from_absence(self):
        a=fixture();a['membership_evidence']['status']='NONMEMBER'
        self.assertEqual(m.evaluate_membership_evidence_horizon(**a)['eligibility_status'],'INELIGIBLE_NONMEMBER')
        a['membership_evidence']['authenticated']=False;self.assertIsNone(m.evaluate_membership_evidence_horizon(**a)['eligible'])
        a=fixture();a['eligibility_checks']['risk']=False;r=m.evaluate_membership_evidence_horizon(**a)
        self.assertEqual(r['membership_status'],'MEMBER_UNDER_SUPPLIED_ATTESTATIONS');self.assertEqual(r['eligibility_status'],'INELIGIBLE_OTHER_REQUIREMENT')
        a['eligibility_checks']['risk']=None;self.assertEqual(m.evaluate_membership_evidence_horizon(**a)['eligibility_status'],'UNKNOWN_OTHER_REQUIREMENT')
    def test_coverage_internal_gap_and_duplicate_intervals(self):
        a=fixture();a['event_coverage_evidence']['covered_intervals']=[dict(start='2026-03-19',end='2026-04-01'),dict(start='2026-04-03',end='2026-09-21')]
        r=m.evaluate_membership_evidence_horizon(**a);self.assertIn('EVENT_COVERAGE_HAS_UNCOVERED_INTERVAL',r['reasons']);self.assertIsNone(r['eligible'])
        a['event_coverage_evidence']['covered_intervals'][1]['start']='2026-04-01'
        with self.assertRaises(ValueError):m.evaluate_membership_evidence_horizon(**a)
    def test_strict_types_identity_and_conflicting_sources(self):
        for attack in ('bool','date','identity','source','unknown_scope'):
            a=fixture()
            if attack=='bool':a['baseline_evidence']['authenticated']=1
            elif attack=='date':a['decision_cutoff']=20260920
            elif attack=='identity':a['membership_evidence']['security_id']='OTHER_CLASS_SAME_ISSUER'
            elif attack=='source':a['membership_evidence']['source_reference']=dict(a['baseline_evidence']['source_reference'],sha256='c'*64)
            else:a['unresolved_cases']=[gral()];a['unresolved_cases'][0]['original_case']['scope_lock']='UNKNOWN'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.evaluate_membership_evidence_horizon(**a)

if __name__=='__main__':unittest.main()
