import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.strategy_latest_display_charts_v1 import LatestDisplayChartsV1, monthly_display_context
from api.strategy_latest_display_charts_v1 import create_router


class DisplayTests(unittest.TestCase):
    def setup_case(self, folder):
        now = datetime(2026, 10, 20, 15, tzinfo=timezone.utc)
        days = [datetime(2026, 10, 12+i, 13, 30, tzinfo=timezone.utc)
                for i in range(9)]
        meta = dict(symbol="SNDK", currency="USD", instrumentType="EQUITY",
                    exchangeTimezoneName="America/New_York", dataGranularity="1d",
                    exchangeName="NMS", regularMarketPrice=11, regularMarketTime=int(now.timestamp()),
                    currentTradingPeriod=dict(regular=dict(start=int(days[-1].timestamp()),
                    end=int(now.replace(hour=20).timestamp()))))
        def raw(count):
            return canonical(dict(chart=dict(error=None, result=[dict(meta=meta,
                timestamp=[int(d.timestamp()) for d in days[:count]],
                indicators=dict(quote=[dict(open=[10]*count, high=[12]*count,
                    low=[9]*count, close=[11]*count, volume=[100]*count)]))])))
        baseline = raw(8)
        context = dict(security_id="SID", ticker="SNDK", baseline=baseline,
                       baseline_sha256=sha256(baseline).hexdigest(),
                       account_revision="a"*64, target_id="b"*64)
        body = [raw(9)]
        clock = [now]
        service = LatestDisplayChartsV1(context_reader=lambda sid: deepcopy(context),
            validate_sources=lambda: None, output_root=Path(folder)/"display",
            clock=lambda: clock[0], fetch=lambda ticker: body[0])
        return service, context, body, clock

    def test_latest_day_partial_and_week_month(self):
        with tempfile.TemporaryDirectory() as folder:
            service, context, body, clock = self.setup_case(folder)
            for interval in ("day", "week", "month"):
                result = service.bars(security_id="SID", interval=interval)
                self.assertEqual(result["as_of"], "2026-10-20")
                self.assertFalse(result["bars"][-1]["complete"])
                self.assertFalse(result["executable"])
                self.assertTrue((Path(result["evidence_directory"])/"provider.raw").is_file())
            clock[0] = clock[0].replace(hour=21)
            self.assertTrue(service.bars(security_id="SID")["current_bar_complete"])

    def test_units_identity_future_and_snapshot_rejected(self):
        for kind in ("units", "identity", "future", "future_bar", "race"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                service, context, body, clock = self.setup_case(folder)
                value = json.loads(body[0])
                channel = value["chart"]["result"][0]
                if kind == "units":
                    channel["indicators"]["quote"][0]["close"][0] = 10
                elif kind == "identity":
                    channel["meta"]["currency"] = "CAD"
                elif kind == "future":
                    channel["meta"]["regularMarketTime"] += 3600
                elif kind == "future_bar":
                    channel["timestamp"][-1] = int(clock[0].replace(hour=18).timestamp())
                else:
                    original = service.fetch
                    def change(ticker):
                        context["account_revision"] = "c"*64
                        return original(ticker)
                    service.fetch = change
                body[0] = canonical(value)
                with self.assertRaises(ValueError):
                    service.bars(security_id="SID")
                self.assertEqual(len(list((Path(folder)/"display").glob("*/failed.json"))), 1)

    def test_integer_quote_time_waits_without_refetch_and_preserves_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            service, context, body, clock = self.setup_case(folder)
            received=clock[0]
            doc=json.loads(body[0]);doc["chart"]["result"][0]["meta"]["regularMarketTime"]+=1
            body[0]=canonical(doc);calls=[]
            original=service.fetch
            def fetch(ticker):calls.append(ticker);return original(ticker)
            service.fetch=fetch
            service.sleep=lambda seconds:clock.__setitem__(0,clock[0]+timedelta(seconds=seconds))
            result=service.bars(security_id="SID")
            self.assertEqual(result["received_at"],received.isoformat())
            self.assertGreater(datetime.fromisoformat(result["verified_at"]),received)
            self.assertEqual(calls,["SNDK"])

    def test_wait_rejects_frozen_rollback_or_excessively_delayed_clock(self):
        for seconds in (0,-1,3):
            with self.subTest(seconds=seconds),tempfile.TemporaryDirectory() as folder:
                service,context,body,clock=self.setup_case(folder)
                doc=json.loads(body[0]);doc["chart"]["result"][0]["meta"]["regularMarketTime"]+=1
                body[0]=canonical(doc)
                service.sleep=lambda _:clock.__setitem__(0,clock[0]+timedelta(seconds=seconds))
                with self.assertRaises(ValueError):service.bars(security_id="SID")

    def test_http_readonly_query(self):
        with tempfile.TemporaryDirectory() as folder:
            service, context, body, clock = self.setup_case(folder)
            app = FastAPI()
            app.include_router(create_router(service=service))
            with TestClient(app) as client:
                response = client.get("/api/strategy-display/latest-bars?security_id=SID")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store")
                response = client.get("/api/strategy-display/latest-bars?security_id=SID&ticker=OTHER")
                self.assertEqual(response.status_code, 409)

    def test_actual_monthly_context_is_readonly_and_scoped(self):
        import test_strategy_saved_target_valuation_v1 as fixture
        with tempfile.TemporaryDirectory() as folder:
            c, monthly, service, provider = fixture.SavedValuationTests().setup_case(folder)
            before = monthly.accounts.path.read_bytes()
            target_before = monthly.targets.path.read_bytes()
            sid = next(s for s, q in monthly.accounts.read()["shares"].items() if q)
            context = monthly_display_context(monthly, sid)
            self.assertEqual(context["security_id"], sid)
            self.assertEqual(sha256(context["baseline"]).hexdigest(), context["baseline_sha256"])
            with self.assertRaisesRegex(ValueError, "NOT_HELD_OR_SELECTED"):
                monthly_display_context(monthly, "UNSELECTED")
            self.assertEqual(monthly.accounts.path.read_bytes(), before)
            self.assertEqual(monthly.targets.path.read_bytes(), target_before)


if __name__ == "__main__":
    unittest.main()
