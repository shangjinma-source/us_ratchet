from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.strategy_daily_preview import create_router
from data.strategy_daily_live_adapter import StrategyDailyLiveAdapter


class DailyLiveTests(unittest.TestCase):
    def setUp(self):
        self.state = dict(account_id="account", revision="a"*64, shares={"SNDK": 14})
        self.target = dict(target_id="b"*64, payload=dict(account_id="account",
                           target_month="2026-10", target_quantities={"SNDK": 21}))
        self.calls = []
        self.monthly = SimpleNamespace(accounts=SimpleNamespace(read=lambda: deepcopy(self.state)),
                                       current=lambda: deepcopy(self.target),
                                       validate_current_target_pins=lambda: None)

    def service(self, enabled=True, reader=None):
        def waiting(*args):
            self.calls.append(args)
            return dict(status="WAIT_POLICY_RELEASE", signal=None)
        return StrategyDailyLiveAdapter(monthly_service=self.monthly, evidence_reader=reader or waiting,
                                        clock=lambda: datetime.now(timezone.utc), enabled=enabled)

    def test_real_route_wait_binding_and_no_writes(self):
        app = FastAPI()
        app.include_router(create_router(service=self.service()))
        before = deepcopy((self.state, self.target))
        with TestClient(app) as client:
            response = client.post("/api/strategy-daily/preview",
                                   json=dict(expected_revision="a"*64, target_id="b"*64))
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["status"], "WAIT_POLICY_RELEASE")
            self.assertEqual(result["new_orders"], [])
            self.assertEqual(result["reference_quotes"], {})
            self.assertEqual(result["daily_gate"]["rows"][0]["action"], "WAIT")
            response = client.post("/api/strategy-daily/preview",
                                   json=dict(expected_revision="a"*64, target_id="b"*64, signal={}))
            self.assertEqual(response.status_code, 409)
        self.assertEqual(before, (self.state, self.target))

    def test_disabled_never_reads_evidence(self):
        self.assertEqual(self.service(False).preview(expected_revision="a"*64,
                         target_id="b"*64)["status"], "DAILY_PREVIEW_DISABLED")
        self.assertEqual(self.calls, [])

    def test_changed_account_rejected(self):
        def change(*args):
            self.state["revision"] = "c"*64
            return dict(status="WAIT_SIGNAL", signal=None)
        with self.assertRaisesRegex(ValueError, "ACCOUNT_CHANGED"):
            self.service(reader=change).preview(expected_revision="a"*64, target_id="b"*64)

    def test_policy_cannot_be_silently_enabled(self):
        with self.assertRaisesRegex(ValueError, "EXECUTION_NOT_ADMITTED"):
            self.service(reader=lambda *args: dict(status="READY", signal={})).preview(
                expected_revision="a"*64, target_id="b"*64)
