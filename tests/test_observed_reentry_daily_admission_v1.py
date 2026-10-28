from copy import deepcopy
from types import SimpleNamespace
import unittest
import test_observed_frontier_daily_admission_v1 as original_fixture
from data.strategy_observed_reentry_daily_admission_v1 import ObservedReentryDailyAdmission
from core.reentry_buy_scope_v1 import digest


class ReentryObserverTests(unittest.TestCase):
    def setUp(self):
        self.fixture = original_fixture.ObserverTests()
        self.fixture.setUp()
        self.reference = dict(account_id='a', version=1, locks={})
        self.configuration = 'c' * 64
        self.fixture.response.update(policy_id='SAVED_FRONTIER_CAP50_EXIT20_REENTRY_V1',
            reference_projection=dict(schema='REFERENCE_PROJECTION_SUMMARY_V1',
                projection_sha256='a'*64, reference_version=1,
                reference_state_sha256=digest(self.reference), configuration_sha256=self.configuration,
                buy_status={'A':'ALLOW'}))
        old = self.fixture.observer
        self.observer = ObservedReentryDailyAdmission(service=old.service, monthly=old.monthly,
            journal=old.journal, clock=old.clock, validate_sources=old.validate_sources,
            policy_references=old.policy_references,
            reference_store=SimpleNamespace(read_reference=lambda account:deepcopy(self.reference)),
            configuration_reader=lambda:self.configuration)

    def preview(self):
        return self.observer.preview(expected_revision='r', target_id='t', expected_proposal_id='p')

    def assert_wait(self):
        result=self.preview()
        self.assertEqual(result['status'],'WAIT')
        self.assertEqual(result['new_orders'],[])
        self.assertEqual(result['reference_quotes'],{})
        self.assertEqual(result['difference'],{})
        return result

    def test_success_and_no_cached_result(self):
        self.assertEqual(self.preview()['status'],'READY')
        self.reference['version']+=1
        self.assert_wait()

    def test_lock_changes_during_each_journal_write(self):
        for hook in ('append_hook','return_hook'):
            for version_change in (True,False):
                self.setUp()
                def change():
                    if version_change:self.reference['version']+=1
                    else:self.reference['locks']['S']={'security_id':'S'}
                setattr(self.fixture,hook,change)
                self.assert_wait()

    def test_configuration_changed_after_return_record(self):
        self.fixture.return_hook=lambda:setattr(self,'configuration','d'*64)
        self.assert_wait()

    def test_expiry_after_return_record(self):
        from datetime import timedelta
        self.fixture.return_hook=lambda:setattr(self.fixture,'now',self.fixture.now+timedelta(seconds=31))
        self.assert_wait()

    def test_missing_or_injected_summary_never_leaks_nested_orders(self):
        for mutation in ('missing','extra','nested'):
            self.setUp()
            if mutation=='missing':self.fixture.response.pop('reference_projection')
            elif mutation=='extra':self.fixture.response['reference_projection']['candidate_orders']=[{'price':1}]
            else:self.fixture.response['reference_projection']['buy_status']={'A':{'price':1}}
            result=self.assert_wait()
            self.assertNotIn('reference_projection',result)

    def test_wrong_policy_and_account_change(self):
        self.fixture.response['policy_id']='SAVED_FRONTIER_CAP50_EXIT20_V1'
        self.assert_wait()
        self.setUp()
        self.fixture.return_hook=lambda:self.fixture.target.update(proposal_id='new')
        self.assert_wait()


if __name__=='__main__':unittest.main()
