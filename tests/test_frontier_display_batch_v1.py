import json
import tempfile
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import patch

from core.strategy_account_ledger import canonical, require
from data.strategy_frontier_display_batch_v1 import FrontierDisplayBatchV1
from test_strategy_latest_display_charts_v1 import DisplayTests


class BatchTests(unittest.TestCase):
    def fixture(self, folder):
        original, context, bodies, clock = DisplayTests().setup_case(folder)
        state = dict(opens=0, depth=0, revision="a" * 64, proposal="p", gate=0)
        lock = RLock()

        @contextmanager
        def operation():
            with lock:
                if not state["depth"]:
                    state["opens"] += 1
                state["depth"] += 1
                try:
                    yield {}
                finally:
                    state["depth"] -= 1

        def resolver(view, identifier, proposal):
            with operation():
                require(proposal == state["proposal"], "STALE_FRONTIER_PROPOSAL")
                return dict(deepcopy(context), security_id=identifier,
                            account_revision=state["revision"], proposal_id=proposal)

        def fetch(ticker):
            self.assertEqual(state["depth"], 0, "network must not hold snapshot lock")
            return bodies[0]

        def gate():
            state["gate"] += 1

        view = SimpleNamespace(monthly=SimpleNamespace(snapshot_operation=operation))
        service = FrontierDisplayBatchV1(view=view, validate_sources=gate,
            output_root=original.output, clock=original.clock, fetch=fetch)
        self.enterContext(patch("data.strategy_frontier_display_batch_v1.frontier_display_context", resolver))
        return service, state, bodies

    def test_two_members_share_two_snapshots_and_keep_per_stock_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            service, state, bodies = self.fixture(folder)
            result = service.bars(security_ids=["SID", "SID2"], expected_proposal_id="p")
            self.assertEqual(state["opens"], 2)
            self.assertEqual([row["security_id"] for row in result["charts"]], ["SID", "SID2"])
            self.assertTrue(all(row["bars"][-1]["close"] == 11 for row in result["charts"]))
            self.assertFalse(result["executable"])
            self.assertEqual(len(list(Path(folder).glob("display/*/complete.json"))), 2)

    def test_account_or_proposal_change_rejects_entire_batch_without_completes(self):
        for key in ("revision", "proposal"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                service, state, bodies = self.fixture(folder)
                def change(ticker):
                    state[key] = "changed"
                    return bodies[0]
                service.display_options["fetch"] = change
                with self.assertRaises(Exception):
                    service.bars(security_ids=["SID", "SID2"], expected_proposal_id="p")
                self.assertFalse(list(Path(folder).glob("display/*/complete.json")))

    def test_transport_failure_breaks_rendezvous_without_hanging(self):
        with tempfile.TemporaryDirectory() as folder:
            service, state, bodies = self.fixture(folder)
            def fail(ticker):
                raise ValueError("DISPLAY_TRANSPORT_INVALID")
            service.display_options["fetch"] = fail
            with self.assertRaises(Exception):
                service.bars(security_ids=["SID", "SID2"], expected_proposal_id="p")
            self.assertFalse(list(Path(folder).glob("display/*/complete.json")))

    def test_one_failed_member_cancels_healthy_peer_and_next_request_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            service, state, bodies = self.fixture(folder)
            calls = []
            lock = RLock()
            def mixed(ticker):
                with lock:
                    calls.append(ticker)
                    number = len(calls)
                if number == 2:
                    raise ValueError("DISPLAY_TRANSPORT_INVALID")
                return bodies[0]
            service.display_options["fetch"] = mixed
            with self.assertRaises(Exception):
                service.bars(security_ids=["SID", "SID2"], expected_proposal_id="p")
            self.assertFalse(list(Path(folder).glob("display/*/complete.json")))
            service.display_options["fetch"] = lambda ticker: bodies[0]
            result = service.bars(security_ids=["SID", "SID2"], expected_proposal_id="p")
            self.assertEqual(len(result["charts"]), 2)

    def test_bad_price_units_cannot_pass_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            service, state, bodies = self.fixture(folder)
            body = json.loads(bodies[0])
            body["chart"]["result"][0]["indicators"]["quote"][0]["close"][0] = 55
            bodies[0] = canonical(body)
            with self.assertRaises(Exception):
                service.bars(security_ids=["SID", "SID2"], expected_proposal_id="p")
            self.assertFalse(list(Path(folder).glob("display/*/complete.json")))

    def test_bad_batch_arguments_do_not_open_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            service, state, bodies = self.fixture(folder)
            for identifiers in ([], ["SID", "SID"], [str(n) for n in range(9)], [None]):
                with self.assertRaisesRegex(ValueError, "DISPLAY_BATCH_ARGUMENTS"):
                    service.bars(security_ids=identifiers, expected_proposal_id="p")
            self.assertEqual(state["opens"], 0)

    def test_http_batch_is_readonly_and_rejects_ambiguous_parameters(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.strategy_frontier_display_batch_v1 import create_router
        with tempfile.TemporaryDirectory() as folder:
            service, state, bodies = self.fixture(folder)
            app = FastAPI()
            app.include_router(create_router(service=service))
            with TestClient(app) as client:
                path = "/api/strategy-display/latest-batch"
                query = "?security_id=SID&security_id=SID2&expected_proposal_id=p"
                response = client.get(path + query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()["charts"]), 2)
                self.assertEqual(response.headers["cache-control"], "no-store")
                for extra in ("&expected_proposal_id=q", "&ticker=SNDK", "&bars=0"):
                    response = client.get(path + query + extra)
                    self.assertEqual(response.status_code, 409)
                    self.assertNotIn("charts", response.json())
                self.assertEqual(client.post(path + query).status_code, 405)


if __name__ == "__main__":
    unittest.main()
