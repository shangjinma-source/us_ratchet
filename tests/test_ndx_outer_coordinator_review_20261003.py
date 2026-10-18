import unittest
from copy import deepcopy
import test_ndx_outer_lane_refit_coordinator_20261003 as f

m=f.m

class Review(unittest.TestCase):
    def test_risk_cache_preserves_all48_without_refitting_failed_numeric(self):
        args,docs,names,calls,read=f.fixture(risk=True)
        result=read(m.execute_full48(**args))
        self.assertEqual([i for i,_ in calls],[4,5,6,7])
        self.assertEqual(sum(origin is None for _,origin in calls),1)
        self.assertEqual(len(result['rows']),48)
        self.assertEqual(result['summary']['outcome_counts']['AUDITED_REUSED_RISK_FAILURE'],3)
        self.assertEqual(result['summary']['outcome_counts']['NO_REFIT_INPUT_OR_ADJACENT_PRIOR'],20)
        self.assertFalse(result['all48_successfully_refitted'])

    def test_wrong_external_audit_stops_before_any_prior_advance(self):
        args,docs,names,calls,read=f.fixture();inspect=args['inspect_saved']
        def malicious(ref):
            r=inspect(ref);body=read(r);body['reader_sha256']='0'*64
            return args['persist']('wrong_audit.json',body)
        args['inspect_saved']=malicious
        result=read(m.execute_full48(**args))
        self.assertEqual(len(calls),1);self.assertEqual(len(result['rows']),48)
        self.assertEqual(result['rows'][4]['outcome'],'UNRESOLVED_DISPATCH')
        self.assertEqual(result['summary']['audited_success_count'],0)
        self.assertEqual(result['accepted_evidence_references'],[])

    def test_unknown_call_and_resource_pre_dispatch_do_not_invent_fit(self):
        args,docs,names,calls,read=f.fixture()
        def unknown(*args):raise RuntimeError('No returned post or actual fit fact')
        args['dispatch']=unknown
        result=read(m.execute_full48(**args))
        self.assertIsNone(result['rows'][4]['fit_call_invoked']);self.assertTrue(result['rows'][4]['dispatch_invoked'])
        self.assertEqual(result['summary']['fit_invoked_coordinate_count'],0)
        args,docs,names,calls,read=f.fixture(free=True)
        result=read(m.execute_full48(**args));self.assertFalse(calls)
        self.assertEqual(result['summary']['unprocessed_coordinate_count'],48)

if __name__=='__main__':unittest.main()
