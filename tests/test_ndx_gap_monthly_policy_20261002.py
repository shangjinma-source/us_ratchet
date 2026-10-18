from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest.ndx_gap_monthly_observation_policy_research import monthly_observation_coordinates
from scripts import ndx_gap_monthly_policy_20261002 as module


def fixture():
    day=date(2026,7,1); days=[]
    while day<=date(2026,10,1):
        if day.weekday()<5 and str(day) not in ('2026-07-03','2026-09-07'): days.append(str(day))
        day+=timedelta(days=1)
    assert len(days)==65
    rows=[{'session':day,'kind':'SEALED_PARENT_OBSERVED_SESSION' if index<60 else 'MISSED_OBSERVATION',
           'counts_as_observed_session':False,'decision_eligible':False} for index,day in enumerate(days)]
    f={'schema':'OBSERVATION_GAP_FRONTIER_RESEARCH_V1','last_observed_session':'2026-09-24',
        'last_accounted_session':'2026-10-01','month_first_semantics':'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE',
        'known_accounted_rows':rows}
    refs={role:{'path':'synthetic/'+role,'sha256':'a'*64} for role in ('frontier','user_choice')}
    return f,refs


class PolicyWrapperTests(unittest.TestCase):
    def test_observed_unknown_and_gap_not_observed(self):
        f,refs=fixture(); before=deepcopy(f)
        result=module.assemble(f,refs,monthly_observation_coordinates)
        self.assertEqual(result['prospective_monthly_coordinate_count'],0)
        self.assertEqual(result['projection']['months'][-1]['first_observed_session'],None)
        self.assertEqual({row['seal_status'] for row in result['projection_inputs']['known_rows'][:60]},{'UNKNOWN'})
        self.assertEqual(f,before)

    def test_missing_full_sequence_or_gap_privilege_rejected(self):
        for kind in ('missing','privilege','role'):
            f,refs=fixture()
            if kind=='missing': f['known_accounted_rows'].pop(30)
            elif kind=='privilege': f['known_accounted_rows'][-1]['decision_eligible']=True
            else: f['known_accounted_rows'][-1]['kind']='SEALED_PARENT_OBSERVED_SESSION'
            with self.subTest(kind=kind),self.assertRaises(ValueError): module.prepare(f,refs['frontier'])

    def test_result_cannot_grant_seal_authority(self):
        f,refs=fixture()
        def corrupt(**kwargs):
            result=monthly_observation_coordinates(**kwargs); result['candidate_seal_allowed']=0; return result
        with self.assertRaises(ValueError): module.assemble(f,refs,corrupt)


if __name__=='__main__': unittest.main()
