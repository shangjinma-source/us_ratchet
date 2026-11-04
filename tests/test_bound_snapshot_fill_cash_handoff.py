"""Temporary ledger handoff through the deployed snapshot HTTP composition.

Reuses the real frontier engine with isolated synthetic market/risk evidence.
No production ledger, live quotes, broker fills or AI outcome certification.
"""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.strategy_account import StrategyAccountService
from api.strategy_frontier_daily_preview_v1 import create_router
from data.strategy_bound_preview_snapshot_v1 import BoundPreviewSnapshotV1
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_observed_frontier_daily_admission_v1 import ObservedFrontierDailyAdmission
import test_frontier_fill_cash_handoff as handoff


class BoundSnapshotFillCashHandoffTests(handoff.FrontierFillCashHandoffTests):
    def transport(self, service, monthly, case):
        # The lower-level fixture stores the raw target; the production monthly
        # view enriches it with the saved proposal before the HTTP UI projection.
        display_target = dict(deepcopy(case['target']),
            proposal_id=case['proposal']['proposal_id'],
            frontier_proposal=deepcopy(case['proposal']),
            risk_monthly_targets=deepcopy(case['proposal']['payload']['proposed_target_quantities']))
        monthly.current = lambda: deepcopy(display_target)
        monthly._month = lambda: case['target']['payload']['target_month']
        account = StrategyAccountService(database_path=case['accounts'].path,
            account_id=case['accounts'].read()['account_id'], resolver=lambda ticker: None,
            clock=lambda: case['clock'][0])
        observed = ObservedFrontierDailyAdmission(service=service, monthly=monthly,
            journal=DailyAdviceJournalV1(Path(case['root'])/'handoff-advice.sqlite3'),
            clock=lambda: case['clock'][0], validate_sources=lambda: None,
            policy_references={})
        bound = BoundPreviewSnapshotV1(observed=observed, project_account=account.project)
        app = FastAPI()
        app.include_router(create_router(service=bound))
        # Start Windows' event-loop socketpair before the fixture blocks network.
        # All tested HTTP requests still use the in-process ASGI transport.
        client = self.enterContext(TestClient(app))

        def preview(**binding):
            before = case['accounts'].read()
            response = client.post('/api/strategy-daily-v3/preview', json=binding)
            result = response.json()
            self.assertEqual(case['accounts'].read(), before)
            if response.status_code != 200:
                self.assertEqual(response.status_code, 409)
                self.assertEqual(result['new_orders'], [])
                self.assertEqual(result['reference_quotes'], {})
                self.assertNotIn('verified_snapshot', result)
                raise ValueError(result['reason'])
            snapshot = result['verified_snapshot']
            self.assertEqual(snapshot['schema'], 'BOUND_PREVIEW_SNAPSHOT_V1')
            self.assertEqual(snapshot['account'], account.project(before)['account'])
            self.assertEqual(snapshot['account']['revision'], result['account_revision'])
            self.assertEqual(snapshot['target']['target_id'], binding['target_id'])
            self.assertEqual(snapshot['target']['proposal_id'], binding['expected_proposal_id'])
            self.assertEqual(result['observation_record']['status'], 'SAVED')
            return result

        return SimpleNamespace(preview=preview)
