from copy import deepcopy
import unittest
from scripts import ndx_forward_source_capture_20261002 as module


def fixture():
    refs={role:{'path':'synthetic/'+role,'sha256':'a'*64} for role in ('frontier','baseline_QQQ','baseline_SPY')}
    false=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','canonical_calendar_append_allowed',
        'point_in_time_verified','promotion_allowed','oos_recovery_completed'),False)
    frontier={'schema':'OBSERVATION_GAP_FRONTIER_RESEARCH_V1','last_observed_session':'2026-09-24',
        'last_accounted_gap_session':'2026-10-01','last_accounted_session':'2026-10-01',
        'known_accounted_rows':[{'session':str(i)} for i in range(65)],'unaccounted_source_dates':[],
        'source_hashes':{},'input_references':{ticker:refs['baseline_'+ticker] for ticker in ('QQQ','SPY')},**false}
    receipt={'schema':'OBSERVATION_GAP_FRONTIER_PUBLICATION_V1','status':'PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY',
        'frontier_reference':refs['frontier'],'source_hashes':{},**false}
    return frontier,receipt,refs


class CaptureWrapperTests(unittest.TestCase):
    def test_exact_parent_and_baseline_bindings(self):
        f,p,r=fixture(); original=deepcopy(f); module.validate_parent(f,p,r); self.assertEqual(f,original)
        for change in ('source','receipt','permission'):
            f,p,r=fixture()
            if change=='source': r['baseline_QQQ']={'path':'other','sha256':'b'*64}
            elif change=='receipt': p['frontier_reference']={'path':'other','sha256':'b'*64}
            else: p['candidate_seal_allowed']=0
            with self.subTest(change=change),self.assertRaises(ValueError): module.validate_parent(f,p,r)

    def test_result_bytes_clocks_and_strict_permissions(self):
        f,_,_=fixture(); current={'QQQ':b'q','SPY':b's'}; raw={'baseline_QQQ':b'oldq','baseline_SPY':b'olds','tzif':b'tzif'}
        start='2026-10-02T14:00:00+00:00'; end='2026-10-02T14:00:01+00:00'
        result={'schema':'FORWARD_SOURCE_CAPTURE_PLANNING_V1','capture_started_at_utc':start,'observed_at_utc':end,
            'source_sha256':{k:module.sha(v) for k,v in current.items()},
            'baseline_sha256':{k:module.sha(raw['baseline_'+k]) for k in current},'tzif_sha256':module.sha(raw['tzif']),
            'accounted_prefix_dates':[r['session'] for r in f['known_accounted_rows']],
            'last_observed_session_unchanged':f['last_observed_session'],'last_accounted_session_unchanged':f['last_accounted_session'],
            'month_first_semantics':'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE','classifications':[],'timeliness_candidate':None,
            **dict.fromkeys(module.PLAN_FALSE,False)}
        module.validate_result(result,f,current,raw,start,end)
        for field,value in [('fresh_observation',0),('tzif_sha256','b'*64),('observed_at_utc',start)]:
            bad=deepcopy(result); bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): module.validate_result(bad,f,current,raw,start,end)


if __name__=='__main__': unittest.main()
