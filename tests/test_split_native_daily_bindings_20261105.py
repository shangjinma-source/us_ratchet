"""Reject stale or substituted native source reviews before risk is written."""
from copy import deepcopy
from datetime import timedelta
from tempfile import TemporaryDirectory
import json
import unittest
import test_split_native_month_daily_20261105 as fixture
from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_daily_session_capture import stamp
from docs.candidates.split_native_month_daily_20261105 import project_native_month_daily


class Tests(unittest.TestCase):
    def test_rehashed_timing_and_stale_account_cannot_advance_risk(self):
        with TemporaryDirectory(dir=fixture.ROOT/'tmp') as folder:
            _, account, _, _, arguments = fixture.Tests().case(folder)
            risk = MonthlyPeakExitStore(arguments['risk_path'])
            initial = risk.read(account.read()['account_id'])
            altered = deepcopy(arguments)
            review = json.loads(altered['review_bytes'])
            timing = review['timing_bundles']['split-B']['review']
            timing['tradable_evidence_received_at'] = (stamp(timing['tradable_evidence_received_at']) + timedelta(seconds=1)).isoformat()
            altered['review_bytes'] = canonical(review)
            altered['trusted_review_sha256'] = fixture.digest(altered['review_bytes'])
            with self.assertRaisesRegex(ValueError, 'NATIVE_TRAINING_TIMING_CHANGED'):
                project_native_month_daily(**altered)
            self.assertEqual(risk.read(account.read()['account_id']), initial)
            account.append(dict(event_id='changed-after-review',kind='CASH_CONFIRM',amount='80',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.read()['revision'])
            stale = dict(arguments, state=account.read())
            with self.assertRaisesRegex(ValueError, 'FRONTIER_REVIEW_BINDING'):
                project_native_month_daily(**stale)
            self.assertEqual(risk.read(account.read()['account_id']), initial)
            # A new action after selection cannot borrow the prior native target.
            account.clock = lambda: stamp(arguments['now'])
            account.append(dict(event_id='later-split-A',kind='SPLIT_CONFIRMED',action_id='later-split-A',security_id='A',ratio=2,effective_at='2026-11-03T13:30:00+00:00',broker_confirmed_at='2026-11-03T14:00:00+00:00',old_unit_id='unit-A',new_unit_id='unit-A2',evidence_sha256='b'*64),expected_revision=account.read()['revision'])
            with self.assertRaisesRegex(ValueError, 'NATIVE_TARGET_SPLIT_BINDING'):
                project_native_month_daily(**dict(arguments,state=account.read()))
            self.assertEqual(risk.read(account.read()['account_id']), initial)
            self.assertFalse((arguments['research_root']/'native-daily-evidence').exists())


if __name__ == '__main__': unittest.main()
