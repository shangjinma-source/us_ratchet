import unittest
from scripts import ndx_adobe_event_endpoint_crosscheck_20260919 as module


class IndependentReview(unittest.TestCase):
    def test_offsetting_missing_events_cannot_be_certified_by_equal_endpoints(self):
        before=['T'+str(i) for i in range(100)]
        def event(identifier,day,action,ticker):
            return dict(event_id=identifier,effective_date=day,action=action,ticker=ticker,event_status='effective')
        full=[event('one','2023-02-01','remove','T0'),event('one','2023-02-01','add','TEMP'),event('two','2023-04-01','remove','TEMP'),event('two','2023-04-01','add','T0')]
        for rows in (full,[]):
            result=module.crosscheck(before,before,rows)
            self.assertTrue(result['endpoint_ticker_sets_equal'])
            for key in ('event_coverage_complete','intermediate_membership_verified','exact_security_membership_verified','point_in_time_verified','promotion_allowed'):
                self.assertIs(result[key],False)
            self.assertTrue(result['endpoint_agreement_cannot_exclude_offsetting_omitted_events'])

    def test_real_full_source_closure_and_no_security_seed_claim(self):
        report=module.build()
        self.assertEqual(report['observed_event_rows'],21)
        self.assertTrue(report['issuer_table_mirror_not_index_provider_baseline'])
        for path,sha in report['source_hashes'].items():
            self.assertEqual(module.digest(module.Path(path).read_bytes()),sha)


if __name__=='__main__':unittest.main()
