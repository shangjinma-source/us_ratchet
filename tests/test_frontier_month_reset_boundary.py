import importlib.util
import json
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory

from test_saved_monthly_frontier_proposal import native_fixture
from test_monthly_cap_topup_packet import packet,DAYS
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.monthly_peak_exit_history import monthly_exit_observations
import data.saved_frontier_exit_packet_v1 as candidate

class BoundaryTests(unittest.TestCase):
    def check_case(self, *, authorized=True, decision='2026-09-30', old_month='2026-09', error=None):
        target=native_fixture();proposal=build_frontier_proposal(target=target)
        account=target['payload']['account_id']
        inputs=packet(target,{'A':[100,105,110],'B':[100,105,110]})
        inputs['base_target'].update(origin_reference=proposal['proposal_id'],quantities=proposal['payload']['proposed_target_quantities'])
        old=json.loads(json.dumps(inputs).replace('2026-10-','2026-09-'))
        text=json.dumps(inputs)
        for previous,new in zip(DAYS,['2026-09-30','2026-10-01','2026-10-02']):
            text=text.replace(previous,new)
        inputs=json.loads(text)
        if decision=='2026-09-29':
            inputs['session_dates'].insert(0,decision)
            inputs['session_close_times']['closes'][decision]=decision+'T20:00:00+00:00'
        with TemporaryDirectory() as folder:
            store=MonthlyPeakExitStore(Path(folder)/'risk.sqlite')
            store.advance(account_id=account,expected_previous_session=None,
                observations=monthly_exit_observations(**old),baseline_targets={'A':99,'B':99},target_month=old_month)
            before=store.read(account)
            kwargs=dict(target=target,proposal=proposal,inputs=inputs,risk_store=store,
                account_id=account,decision_date=decision,expected_previous_session='2026-09-22',
                authorized_monthly_reset=decision if authorized else None)
            if error:
                with self.assertRaisesRegex(ValueError,error):
                    candidate.apply_frontier_exit_packet(**kwargs)
                self.assertEqual(before,store.read(account))
            else:
                result=candidate.apply_frontier_exit_packet(**kwargs)
                self.assertEqual(result['state']['target_month'],'2026-10')
                self.assertEqual(result['state']['decision_date'],'2026-09-30')
                self.assertTrue(store.recorded_prices(account,'2026-09-20'))
    def test_preceding_close_allowed(self): self.check_case()
    def test_authorization_required(self): self.check_case(authorized=False,error='FRONTIER_MONTHLY_RESET_BINDING')
    def test_older_close_rejected(self): self.check_case(decision='2026-09-29',error='RISK_EPOCH_MONTH_BOUNDARY')
    def test_month_rollback_rejected(self): self.check_case(old_month='2026-11',error='FRONTIER_MONTHLY_RESET_BINDING')

if __name__=='__main__': unittest.main()
