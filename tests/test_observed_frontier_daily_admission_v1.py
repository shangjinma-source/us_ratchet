from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from data.strategy_observed_frontier_daily_admission_v1 import ObservedFrontierDailyAdmission


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        self.target = dict(target_id='t', proposal_id='p', payload=dict(target_month='2026-10'))
        self.response = dict(status='READY', account_revision='r', target_id='t', proposal_id='p',
            risk_valid_from=self.now.isoformat(), risk_valid_until=(self.now + timedelta(seconds=60)).isoformat(),
            new_orders=[dict(security_id='A')], difference=dict(new_orders=[dict(security_id='A')]),
            reference_quotes={'A': dict(observed_at=self.now.isoformat(),
                                       reference_valid_until=(self.now + timedelta(seconds=30)).isoformat())})
        self.compute_hook = self.append_hook = self.return_hook = lambda: None
        self.events = []

        def compute(**arguments):
            self.assertEqual(arguments['expected_proposal_id'], 'p')
            self.compute_hook()
            return deepcopy(self.response)

        def append(event, **kwargs):
            self.events.append(deepcopy(event))
            self.append_hook()

        monthly = SimpleNamespace(snapshot_operation=nullcontext,
            accounts=SimpleNamespace(read=lambda: dict(account_id='a', revision='r')),
            current=lambda: deepcopy(self.target))
        self.observer = ObservedFrontierDailyAdmission(service=SimpleNamespace(preview=compute),
            monthly=monthly, journal=SimpleNamespace(append=append,
                record_return=lambda *args: self.return_hook()), clock=lambda: self.now,
            validate_sources=lambda: None, policy_references={})

    def run_preview(self):
        return self.observer.preview(expected_revision='r', target_id='t', expected_proposal_id='p')

    def test_success_journals_proposal(self):
        result = self.run_preview()
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(self.events[0]['response']['proposal_id'], 'p')

    def test_proposal_change_during_compute_or_journal(self):
        for hook in ('compute_hook', 'append_hook', 'return_hook'):
            with self.subTest(hook=hook):
                self.setUp()
                setattr(self, hook, lambda: self.target.update(proposal_id='changed'))
                result = self.run_preview()
                self.assertEqual(result['status'], 'WAIT')
                self.assertEqual(result['new_orders'], [])
                self.assertEqual(result['difference']['new_orders'], [])

    def test_quote_expiry_after_record_return(self):
        self.return_hook = lambda: setattr(self, 'now', self.now + timedelta(seconds=31))
        self.assertEqual(self.run_preview()['new_orders'], [])

    def test_risk_expiry_after_record_return(self):
        self.response['risk_valid_until'] = (self.now + timedelta(seconds=5)).isoformat()
        self.return_hook = lambda: setattr(self, 'now', self.now + timedelta(seconds=6))
        self.assertEqual(self.run_preview()['status'], 'WAIT')

    def test_nonready_cannot_leak_nested_orders_or_quotes(self):
        for status in ('WAIT', 'HOLD'):
            for field in ('difference', 'reference_quotes'):
                with self.subTest(status=status, field=field):
                    self.setUp()
                    self.response['status'] = status
                    self.response['new_orders'] = []
                    if field == 'difference':
                        self.response['reference_quotes'] = {}
                    else:
                        self.response['difference']['new_orders'] = []
                    result = self.run_preview()
                    self.assertEqual(result['status'], 'WAIT')
                    self.assertEqual(result['reference_quotes'], {})
                    self.assertEqual(result['difference']['new_orders'], [])


if __name__ == '__main__':
    unittest.main()
