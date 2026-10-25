from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import unittest

import test_strategy_daily_session_capture as fixtures
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from core.strategy_account_ledger import canonical
from data.strategy_daily_session_capture import encoded
from data.strategy_daily_continuity_normalizer import normalize_saved_capture, extend_reviewed_calendar, derive_identity_binding, NORMALIZATION_CODE_PATHS
ROOT = fixtures.ROOT


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.capture = fixtures.DailySessionCaptureTests()
        self.capture.setUp()
        self.addCleanup(self.capture.doCleanups)
        self.root = self.capture.root
        for name in NORMALIZATION_CODE_PATHS:
            raw=(ROOT/name).read_bytes()
            (self.root/name).parent.mkdir(parents=True,exist_ok=True)
            (self.root/name).write_bytes(raw)
            if name not in {r["path"] for r in self.capture.configuration["source_pins"]}:
                self.capture.configuration["source_pins"].append(dict(path=name,sha256=sha256(raw).hexdigest()))
        self.now = datetime.fromisoformat("2026-10-20T13:00:00+00:00")
        self.capture_day = "2026-10-20"
        path = "tmp/daily_signal_sndk_reviewed_20261020_v1/receipt.json"
        raw = (ROOT/path).read_bytes()
        self.parent = dict(path=path, sha256=sha256(raw).hexdigest())
        parent = json.loads(raw)
        for name in [path, *parent["source_sha256"]]:
            file = self.root/name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes((ROOT/name).read_bytes())
        self.accounts = StrategyAccountStore(self.root/"account.sqlite3", clock=lambda:self.now)
        self.accounts.initialize(parent["account_id"], operation_id="fixture-init")
        self.accounts.append(dict(kind="CASH_CONFIRM", event_id="fixture-cash", amount="20000",
                                  cash_basis="TOTAL_UNINVESTED"), expected_revision=self.accounts.read()["revision"])
        sid = self.capture.configuration["security"]["security_id"]
        binding = dict(training_cutoff_date="2026-10-14",
            historical_search_arguments=dict(decision_date="2026-10-14"),
            search_arguments=dict(decision_date="2026-10-20"),
            valuation_at=self.now.isoformat(), valuation_date="2026-10-20")
        decision = dict(input_binding=binding, input_id=sha256(canonical(binding)).hexdigest(),
                        target_quantities={sid:21})
        self.targets = StrategyMonthlyTargetStore(self.root/"target.sqlite3")
        self.target = self.targets.append(dict(schema="REAL_STRATEGY_MONTHLY_TARGET_V1",
            account_id=parent["account_id"], target_month="2026-10", created_at=self.now.isoformat(),
            previous_target_id=None, request=dict(event_id="fixture-target"),
            decision=dict(payload=decision,decision_id=sha256(canonical(decision)).hexdigest()),
            target_quantities={sid:21}))

    def normalize(self):
        return normalize_saved_capture(root=self.root, capture_directory="capture/"+self.capture_day,
            expected_configuration_sha256=sha256(encoded(self.capture.configuration)).hexdigest(),
            parent_reference=self.parent, state=self.accounts.read(), target=self.target,
            clock=lambda:self.now)

    def test_actual_saved_bytes_machine_normalization_policy_stays_null(self):
        raw=derive_identity_binding(root=self.root,parent_reference=self.parent,
            security_id=self.capture.configuration["security"]["security_id"])
        (self.root/"derived-identity.json").write_bytes(raw)
        self.capture.configuration["identity_review"]=dict(path="derived-identity.json",sha256=sha256(raw).hexdigest())
        self.assertFalse(json.loads(raw)["new_identity_approval"])
        self.capture.run_capture()
        before=self.accounts.path.read_bytes()
        result=self.normalize()
        self.assertEqual(result["status"], "CONDITIONAL_DAILY_EVIDENCE_READY_POLICY_UNCHANGED")
        receipt=result["receipt"]
        self.assertIsNone(receipt["release_sha256"])
        self.assertFalse(receipt["source_authenticated"])
        self.assertFalse(receipt["coverage_complete"])
        self.assertEqual(receipt["available_at"],self.now.isoformat())
        self.assertEqual(receipt["source_received_at"],"2026-10-20T12:00:00+00:00")
        self.assertEqual(self.accounts.path.read_bytes(),before)
        inputs=json.loads(result["files"][receipt["normalized_inputs_path"]])
        from backtest.partial_trend_exposure import partial_sma20_target
        self.assertIn("target_quantities",partial_sma20_target(**inputs))

    def test_parent_closure_tamper_blocks(self):
        self.capture.run_capture()
        file=self.root/"tmp/daily_signal_sndk_reviewed_20261020_v1/unit_review.json"
        file.write_bytes(file.read_bytes()+b" ")
        self.assertEqual(self.normalize()["reason"],"SOURCE_HASH_CHANGED")

    def test_overlap_change_even_with_new_capture_receipts_blocks(self):
        document=json.loads(self.capture.daily)
        series=document["chart"]["result"][0]
        series["indicators"]["quote"][0]["close"][0]+=1
        series["indicators"]["adjclose"][0]["adjclose"][0]+=1
        self.capture.daily=encoded(document)
        self.capture.run_capture()
        self.assertEqual(self.normalize()["reason"],"WAIT_PRICE_CONTINUITY_REVIEW")

    def test_later_day_never_relabels_old_capture(self):
        self.capture.run_capture()
        self.now=datetime.fromisoformat("2026-10-21T13:00:00+00:00")
        self.assertEqual(self.normalize()["reason"],"WAIT_CALENDAR_SESSION")

    def test_self_consistent_receipt_url_tamper_rejected(self):
        self.capture.run_capture()
        folder=self.root/"capture/2026-10-20"
        receipt=json.loads((folder/"daily.receipt.json").read_bytes())
        receipt["url"]="https://unrelated.invalid/forged-source"
        terminal=json.loads((folder/"terminal.json").read_bytes())
        terminal["results"]["daily"]=receipt
        (folder/"daily.receipt.json").write_bytes(encoded(receipt))
        (folder/"terminal.json").write_bytes(encoded(terminal))
        self.assertEqual(self.normalize()["reason"],"CAPTURE_SOURCE_URL_CHANGED")

    def test_future_terminal_time_rejected(self):
        self.capture.run_capture()
        file=self.root/"capture/2026-10-20/terminal.json"
        terminal=json.loads(file.read_bytes());terminal["finished_at"]="2026-10-20T14:00:00+00:00"
        file.write_bytes(encoded(terminal))
        self.assertEqual(self.normalize()["reason"],"CAPTURE_TERMINAL_TIME")

    def test_calendar_extension_uses_saved_schedule_and_exact_overlap(self):
        extension="research_contracts/nasdaq_regular_session_calendar_20261013_20261102_v1.json"
        source=json.loads((ROOT/extension).read_bytes())
        for name in [extension,*source["source_hashes"]]:
            file=self.root/name;file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes((ROOT/name).read_bytes())
        raw=extend_reviewed_calendar(root=self.root,
            previous=self.capture.configuration["calendar"],
            extension=dict(path=extension,sha256=sha256((ROOT/extension).read_bytes()).hexdigest()))
        calendar=json.loads(raw)
        self.assertEqual(calendar["sessions"][-1]["date"],"2026-11-02")
        self.assertTrue(calendar["sessions"][-1]["open"].endswith("-05:00"))

    def test_new_day_fresh_capture_rolls_window_and_preserves_null_policy(self):
        extension="research_contracts/nasdaq_regular_session_calendar_20261013_20261102_v1.json"
        source=json.loads((ROOT/extension).read_bytes())
        for name in [extension,*source["source_hashes"]]:
            file=self.root/name;file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes((ROOT/name).read_bytes())
        raw=extend_reviewed_calendar(root=self.root,previous=self.capture.configuration["calendar"],
            extension=dict(path=extension,sha256=sha256((ROOT/extension).read_bytes()).hexdigest()))
        (self.root/"extended-calendar.json").write_bytes(raw)
        self.capture.configuration["calendar"]=dict(path="extended-calendar.json",sha256=sha256(raw).hexdigest())
        document=json.loads(self.capture.daily);series=document["chart"]["result"][0]
        # Explicit synthetic fixture point, never a claimed market observation.
        series["timestamp"].append(int(datetime.fromisoformat("2026-10-20T13:30:00+00:00").timestamp()))
        series["indicators"]["quote"][0]["close"].append(1330.0)
        series["indicators"]["adjclose"][0]["adjclose"].append(1330.0)
        self.capture.daily=encoded(document)
        self.capture_day="2026-10-21"
        self.now=datetime.fromisoformat("2026-10-21T13:00:00+00:00")
        captured=self.capture.run_capture(clock=lambda:datetime.fromisoformat("2026-10-21T12:00:00+00:00"))
        self.assertEqual(captured["status"],"CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED")
        result=self.normalize()
        self.assertEqual(result["status"],"CONDITIONAL_DAILY_EVIDENCE_READY_POLICY_UNCHANGED")
        receipt=result["receipt"]
        inputs=json.loads(result["files"][receipt["normalized_inputs_path"]])
        self.assertEqual(inputs["signal_date"],"2026-10-20")
        self.assertEqual(len(next(iter(inputs["histories"].values()))["closes"]),20)
        self.assertEqual(receipt["execution_session"]["date"],"2026-10-21")
        self.assertEqual(receipt["source_received_at"],"2026-10-21T12:00:00+00:00")
        self.assertIsNone(receipt["release_sha256"])


if __name__=="__main__":
    unittest.main()
