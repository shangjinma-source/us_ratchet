"""Independent isolated HTTP review; no live transports or production stores."""
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from functools import partial
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_daily_preview import create_router
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
from data.strategy_account_execution_limits import build_execution_limits
from data.strategy_account_target_inputs import build_target_inputs
from data.strategy_daily_live_adapter import StrategyDailyLiveAdapter
import data.strategy_daily_preview_service as orchestration
import test_strategy_account_evidence_provider as fixtures


class IndependentReadyTests(unittest.TestCase):
    def setup_case(self, directory, held="B", effective=None, account_id="real-strategy"):
        provider, _, clock, _ = fixtures.ProviderTests().fixture(directory)
        store = StrategyAccountStore(Path(directory)/"independent.sqlite3", clock=lambda:clock[0])
        store.initialize(account_id, operation_id="init")
        identity = dict(ticker={"A":"AAA","B":"BBB"}[held], security_id=held,
                        source_references=["identity-only"], source_hashes={"identity-only":sha256(b"id").hexdigest()})
        store.append(dict(event_id="fill",kind="DIRECT_FILL",security_id=held,side="BUY",quantity=14,
                          price="10",fees="0",executed_at="2026-10-30T19:00:00Z",identity_evidence=identity),
                     expected_revision=store.read()["revision"])
        store.append(dict(event_id="cash",kind="CASH_CONFIRM",amount="0",cash_basis="TOTAL_UNINVESTED"),
                     expected_revision=store.read()["revision"])
        state = store.read()
        inputs = build_target_inputs(state=state,now=clock[0].isoformat(),maximum_mark_age_seconds=900,
                                     **provider.selection(state))
        payload = dict(input_binding=inputs["binding"],input_id=inputs["input_id"],target_quantities={"B":21})
        target = dict(target_id="b"*64,payload=dict(account_id=state["account_id"],target_month="2026-11",
                      target_quantities={"B":21},decision=dict(status="TARGET_READY",payload=payload,
                      decision_id=sha256(canonical(payload)).hexdigest())))
        cap_path = Path(directory)/"cap.sqlite3"
        caps = LazyPullbackCapStore(cap_path,clock=lambda:clock[0].isoformat(),max_history_rows=32,max_history_bytes=1024*1024)
        provider.limits = partial(build_execution_limits,cap_store=caps)
        monthly = SimpleNamespace(accounts=store,current=lambda:deepcopy(target),
                    validate_current_target_pins=lambda:None,selection=SimpleNamespace(fees="10"))
        signal = dict(account_id=state["account_id"],account_revision=state["revision"],target_id=target["target_id"],
                      policy_id="fixture-only",evidence_id="fixture",observed_at=(clock[0]-timedelta(days=1)).isoformat(),
                      available_at=(clock[0]-timedelta(hours=1)).isoformat(),
                      valid_from=(clock[0]-timedelta(minutes=10)).isoformat(),
                      valid_until=(clock[0]+timedelta(minutes=10)).isoformat(),
                      effective_target_quantities=effective or {"B":7})
        service = StrategyDailyLiveAdapter(monthly_service=monthly,
                    evidence_reader=lambda *args:dict(status="VERIFIED",signal=deepcopy(signal)),
                    clock=lambda:clock[0],enabled=True,policy_id="fixture-only",execution_provider=provider.execution)
        app = FastAPI(); app.include_router(create_router(service=service))
        return SimpleNamespace(provider=provider,store=store,state=state,target=target,monthly=monthly,
                               signal=signal,service=service,app=app,cap_path=cap_path,clock=clock)

    def post(self, case):
        with TestClient(case.app) as client:
            return client.post("/api/strategy-daily/preview",json=dict(
                expected_revision=case.state["revision"],target_id=case.target["target_id"]))

    def test_effective_same_in_real_limits_and_difference_and_old_holding_exit(self):
        for held,effective in (("B",{"B":7}),("A",{"A":0,"B":0})):
            with self.subTest(held=held), TemporaryDirectory() as directory:
                c=self.setup_case(directory,held,effective); before=c.store.path.read_bytes();target=deepcopy(c.target)
                seen=[]; real_limits=c.provider.limits; real_difference=orchestration.preview_scoped_account
                def limits(**kwargs):
                    seen.append(("limits",deepcopy(kwargs["target_quantities"])))
                    return real_limits(**kwargs)
                def difference(**kwargs):
                    seen.append(("difference",deepcopy(kwargs["target_quantities"])))
                    return real_difference(**kwargs)
                c.provider.limits=limits
                with patch.object(orchestration,"preview_scoped_account",difference): result=self.post(c)
                self.assertEqual(result.status_code,200,result.text)
                body=result.json(); self.assertEqual(body["status"],"CONDITIONAL_PREVIEW_READY")
                self.assertEqual([(o["security_id"],o["side"],o["quantity"]) for o in body["new_orders"]],
                                 [(held,"SELL",7 if held=="B" else 14)])
                self.assertEqual(seen,[("limits",{s:q for s,q in effective.items() if q}),("difference",effective)])
                self.assertEqual(c.store.path.read_bytes(),before);self.assertEqual(c.target,target)
                self.assertFalse(c.cap_path.exists())

    def test_expired_and_unreleased_never_capture(self):
        for mode in ("expired","unreleased"):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                c=self.setup_case(directory)
                if mode=="expired": c.signal["valid_until"]=c.clock[0].isoformat()
                else: c.service.evidence_reader=lambda *args:dict(status="WAIT_POLICY_RELEASE",signal=None)
                def forbidden(**kwargs): raise AssertionError("WAIT cannot fetch")
                c.provider.market.capture=forbidden
                response=self.post(c);self.assertEqual(response.status_code,200,response.text)
                body=response.json();self.assertEqual(body["new_orders"],[]);self.assertEqual(body["reference_quotes"],{})
                self.assertEqual(body["status"],"WAIT_FRESH_SIGNAL" if mode=="expired" else "WAIT_POLICY_RELEASE")

    def test_mutation_and_target_race_are_rejected(self):
        for mode in ("provider_mutation","target_race","pin_race","account_race"):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                c=self.setup_case(directory);real=c.provider.limits; drift=[False]
                def limits(**kwargs):
                    result=real(**kwargs)
                    if mode=="provider_mutation": kwargs["target_quantities"]["B"]=8
                    elif mode=="target_race": c.target["payload"]["target_quantities"]["B"]=22
                    elif mode=="account_race":
                        c.store.append(dict(event_id="concurrent-cash",kind="CASH_CONFIRM",amount="1",
                                            cash_basis="TOTAL_UNINVESTED"),expected_revision=c.state["revision"])
                    else: drift[0]=True
                    return result
                def gate():
                    if drift[0]: raise ValueError("SOURCE_CHANGED")
                c.provider.limits=limits;c.monthly.validate_current_target_pins=gate
                before=c.store.path.read_bytes()
                response=self.post(c);self.assertEqual(response.status_code,409,response.text)
                self.assertEqual(response.json()["new_orders"],[])
                if mode!="account_race": self.assertEqual(c.store.path.read_bytes(),before)
                else: self.assertNotEqual(c.store.read()["revision"],c.state["revision"])
