from copy import deepcopy
from datetime import date,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.strategy_daily_signal_verifier import POLICY,CODE_PATHS,ROOT
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
from data.strategy_daily_composition_v3 import DailyCompositionV3
from api.strategy_daily_preview_v3 import create_router
import test_daily_ready_independent as providers
from test_current_quantity_v2_risk_overlays import fixture as history_fixture


class CompositionTests(unittest.TestCase):
    def setup_case(self, directory, held="B"):
        c=providers.IndependentReadyTests().setup_case(directory,held)
        c.target["payload"]["created_at"]=c.clock[0].isoformat()
        c.target["target_id"]=sha256(canonical(c.target["payload"])).hexdigest()
        days=[];day=date(2026,10,30)
        while len(days)<20:
            if day.weekday()<5:days.append(day.isoformat())
            day-=timedelta(days=1)
        days.reverse()
        inputs=history_fixture({"B":[100]*20},quantities={"B":21})
        inputs.update(signal_date=days[-1],observed_at=days[-1]+"T16:00:00-04:00",session_dates=days)
        inputs["base_target"].update(monthly_decision_date=days[-1])
        inputs["session_close_times"]["closes"]={d:d+"T16:00:00-04:00" for d in days}
        inputs["histories"]["B"]["units"]["unit_asof"]=days[-1]
        inputs["histories"]["B"]["closes"]=[dict(date=d,completed_at=d+"T16:00:00-04:00",close="100") for d in days]
        # Existing old holding needs reviewed history too, although overlay uses only monthly B.
        if held=="A":inputs["histories"]["A"]=deepcopy(inputs["histories"]["B"])
        session=dict(date="2026-11-02",open="2026-11-02T09:30:00-05:00",close="2026-11-02T16:00:00-05:00")
        calendar=canonical(dict(schema="FIXED_EXCHANGE_SESSIONS_V1",exchange="NASDAQ",
            sessions=[dict(date=d,open=d+"T09:30:00-04:00",close=d+"T16:00:00-04:00") for d in days]+[session]))
        release=canonical(dict(schema="SERVER_DAILY_POLICY_RELEASE_V1",approved=True,policy_id=POLICY,
            approved_at="2026-01-01T00:00:00Z",calendar_sha256=sha256(calendar).hexdigest(),
            code_sha256={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CODE_PATHS},fixture_only=True))
        files={"normalized.json":canonical(inputs),"raw.json":b'{"fixture_only":true}'}
        receipt=canonical(dict(schema="SERVER_REVIEWED_DAILY_EVIDENCE_V1",normalization_reviewed=True,
            unresolved_units=[],pending_rights=[],account_id=c.state["account_id"],
            account_revision=c.state["revision"],target_id=c.target["target_id"],
            release_sha256=sha256(release).hexdigest(),source_sha256={p:sha256(b).hexdigest() for p,b in files.items()},
            normalized_inputs_path="normalized.json",raw_source_paths=["raw.json"],
            market_asof=inputs["observed_at"],source_received_at="2026-11-02T14:00:00Z",
            available_at="2026-11-02T14:01:00Z",valid_from=session["open"],valid_until=session["close"],
            execution_session=session,research_observed_at_semantics="MARKET_ASOF_NOT_RECEIPT"))
        root=Path(directory)
        for p,b in dict(files,**{"parent.json":receipt,"release.json":release,"calendar.json":calendar}).items():
            (root/p).write_bytes(b)
        c.reader=ArchivedRebindingDailyEvidenceReader(root=root,archive_root=root/"archive",
            parent_receipt_path="parent.json",trusted_parent_sha256=sha256(receipt).hexdigest(),
            source_paths={p:p for p in files},release_path="release.json",
            trusted_release_sha256=sha256(release).hexdigest(),calendar_path="calendar.json")
        c.service=DailyCompositionV3(monthly_service=c.monthly,evidence_reader=c.reader,
            execution_provider=c.provider.execution,clock=lambda:c.clock[0],policy_execution_enabled=True,
            policy_id=POLICY,fee_bps="10")
        app=FastAPI();app.include_router(create_router(service=c.service));c.app=app
        return c

    def post(self,c):
        with TestClient(c.app) as client:return client.post("/api/strategy-daily-v3/preview",
            json=dict(expected_revision=c.state["revision"],target_id=c.target["target_id"]))

    def test_actual_half_and_mixed_real_http_provider(self):
        for held,cash in (("A","0"),("B","0"),("B","100")):
            with self.subTest(held=held,cash=cash),TemporaryDirectory() as directory:
                c=self.setup_case(directory,held)
                if cash!="0":
                    c.store.append(dict(event_id="cash-refresh",kind="CASH_CONFIRM",amount=cash,
                        cash_basis="TOTAL_UNINVESTED"),expected_revision=c.state["revision"])
                    c.state=c.store.read()
                before=c.store.path.read_bytes();target=deepcopy(c.target)
                response=self.post(c);self.assertEqual(response.status_code,200,response.text)
                result=response.json();self.assertEqual(result["status"],"READY")
                self.assertEqual(result["effective_target_quantities"]["B"],10)
                self.assertEqual([(o["side"],o["quantity"]) for o in result["new_orders"]],
                                 [("SELL",14 if held=="A" else 4)])
                if held=="A":self.assertEqual(result["waiting_cash"][0]["quantity"],10)
                self.assertTrue(Path(result["evidence_archive"]["receipt_path"]).is_file())
                import json
                receipt=json.loads(Path(result["evidence_archive"]["receipt_path"]).read_bytes())
                configuration=receipt["target_configuration"]
                self.assertEqual(configuration["training_cutoff"],"2026-10-30")
                self.assertEqual(configuration["valuation_date"],"2026-11-02")
                self.assertEqual(configuration["monthly_target_created_at"],c.clock[0].isoformat())
                self.assertEqual(configuration["monthly_decision_date_semantics"],
                                 "HISTORICAL_TRAINING_ANCHOR_NOT_CONFIGURATION_TIME")
                self.assertEqual(c.store.path.read_bytes(),before);self.assertEqual(c.target,target)
                self.assertFalse(c.cap_path.exists())

    def test_disabled_unreleased_and_archive_failure_no_orders(self):
        for mode in ("disabled","unreleased","archive_failure"):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                c=self.setup_case(directory)
                if mode=="disabled":c.service.enabled=False
                elif mode=="unreleased":c.reader.release_sha=None
                with patch("data.strategy_daily_rebinding_reader.archive_rebound_evidence",
                           side_effect=OSError("archive blocked")) as archive:
                    response=self.post(c)
                self.assertEqual(response.status_code,409 if mode=="archive_failure" else 200)
                self.assertEqual(response.json()["status"],"WAIT")
                self.assertEqual(response.json()["new_orders"],[])
                self.assertEqual(archive.call_count,1 if mode=="archive_failure" else 0)

    def test_future_configuration_refused_before_archive(self):
        with TemporaryDirectory() as directory:
            c=self.setup_case(directory)
            c.target["payload"]["created_at"]=(c.clock[0]+timedelta(seconds=1)).isoformat()
            c.target["target_id"]=sha256(canonical(c.target["payload"])).hexdigest()
            response=self.post(c)
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()["reason"],"REBIND_TARGET_TIME_FUTURE_OR_INVERTED")
            self.assertFalse((Path(directory)/"archive").exists())
