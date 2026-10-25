from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from contextlib import closing
from core.strategy_account_ledger import canonical
from core.strategy_capital_intent_journal import CapitalIntentJournal
from data.current_research_capital_decision_v2 import VERSION
import test_strategy_daily_evidence_rebind as fixtures


class CapitalIntentTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.RebindTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        f.event("CASH_CONFIRM",amount="1000",cash_basis="TOTAL_UNINVESTED")
        self.state=f.accounts.read();self.target=f.targets.current()
        confirmation=[r["payload"] for r in self.state["events"] if r["payload"]["kind"]=="CASH_CONFIRM"][-1]
        self.intent=dict(event_id="new-capital-1",account_id=self.state["account_id"],
            account_revision=self.state["revision"],previous_target_id=self.target["target_id"],
            contribution_amount="250",available_balance="1000",
            balance_confirmation_reference=dict(event_id=confirmation["event_id"],
                payload_sha256=sha256(canonical(confirmation)).hexdigest()))
        self.journal=CapitalIntentJournal(Path(f.temp.name)/"capital.sqlite3")

    def record(self):
        return self.journal.record(self.intent,account_state=self.state,previous_target=self.target)

    def claim(self):
        return self.journal.claim_selection_once(self.intent["event_id"],
            account_state=self.state,previous_target=self.target)

    def publish(self,request,decision=None):
        payload=deepcopy(self.target["payload"])
        payload.update(previous_target_id=self.target["target_id"],request=request)
        if decision is not None:
            payload.update(decision=decision,target_quantities=decision["payload"]["target_quantities"])
        return self.fixture.targets.append(payload)

    def prepared_arguments(self):
        files={"fixture-source":b"fixture-not-market-evidence"}
        pins={k:sha256(v).hexdigest() for k,v in files.items()}
        args=dict(decision_date=self.fixture.date,scenario_dates=[self.fixture.date],
            max_objective_evaluations=100,entered_cash="1000",fee_bps="0",minimum_cash_buffer="0",
            prices={"A":"100"},metadata={"A":{"issuer_id":"issuerA"}})
        binding=dict(account_id=self.state["account_id"],account_revision=self.state["revision"],
            strategy_shares=self.state["shares"],execution_context=dict(available_cash="1000"),
            total_uninvested_cash="1000",holding_market_values={},marks={},strategy_equity="1000",
            search_arguments=args,source_hashes=pins)
        result=dict(method_version=VERSION,status="BUDGET_STOPPED",
            **{k:args[k] for k in ("decision_date","scenario_dates","max_objective_evaluations",
                                 "entered_cash","fee_bps","minimum_cash_buffer")},
            selected=dict(quantities={"A":5},notional="500",fees="0",residual_cash="500",
                          actual_k=1,actual_weights={"A":"1/2"}))
        payload=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),
                     search_result=result,target_quantities={"A":5})
        return dict(decision=dict(status="TARGET_READY",payload=payload,decision_id=sha256(canonical(payload)).hexdigest()),
                    source_files=files,profile=dict(method_version=VERSION,max_objective_evaluations=100,source_pins=pins),
                    account_state=self.state,previous_target=self.target)

    def prepare(self):
        self.journal.prepare(self.intent["event_id"],**self.prepared_arguments())
        return self.journal.publication_candidate(self.intent["event_id"],account_state=self.state,previous_target=self.target)

    def test_balance_and_contribution_distinct_no_account_writes_and_idempotence(self):
        before=self.fixture.accounts.path.read_bytes()
        self.assertEqual(self.record(),self.record())
        self.assertEqual(self.fixture.accounts.read()["available_cash"],"1000")
        self.assertEqual(self.fixture.accounts.path.read_bytes(),before)
        changed=deepcopy(self.intent);changed["contribution_amount"]="251"
        with self.assertRaisesRegex(ValueError,"CAPITAL_EVENT_CONFLICT"):
            self.journal.record(changed,account_state=self.state,previous_target=self.target)

    def test_one_shot_claim_and_unknown_publication_never_reselect(self):
        self.record();first=self.claim();self.assertTrue(first["may_start_selection"])
        for _ in range(2):
            self.assertEqual(self.claim()["status"],"RECOVERY_REQUIRED")
            status=self.journal.reconcile(self.intent["event_id"],target_store=self.fixture.targets)
            self.assertEqual(status["status"],"RECOVERY_REQUIRED")
            self.assertFalse(status["may_start_selection"])

    def test_publication_is_consumption_authority_after_response_loss(self):
        self.record();self.claim();prepared=self.prepare()
        target=self.publish(prepared["request"],prepared["decision"])
        before=self.journal.path.read_bytes()
        for _ in range(2):
            result=self.journal.reconcile(self.intent["event_id"],target_store=self.fixture.targets)
            self.assertEqual(result["status"],"CONSUMED_BY_PUBLISHED_TARGET")
            self.assertEqual(result["target_id"],target["target_id"])
            self.assertFalse(result["may_start_selection"])
        self.assertEqual(self.journal.path.read_bytes(),before)

    def test_bad_confirmation_or_stale_claim_rejected(self):
        bad=deepcopy(self.intent);bad["balance_confirmation_reference"]["payload_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"CAPITAL_BALANCE_REFERENCE_MISMATCH"):
            self.journal.record(bad,account_state=self.state,previous_target=self.target)
        self.record()
        self.fixture.event("CASH_CONFIRM",amount="1000",cash_basis="TOTAL_UNINVESTED")
        with self.assertRaisesRegex(ValueError,"STALE_REVISION"):
            self.journal.claim_selection_once(self.intent["event_id"],
                account_state=self.fixture.accounts.read(),previous_target=self.target)
        self.assertEqual(self.journal.reconcile(self.intent["event_id"],target_store=self.fixture.targets)["status"],
                         "INTENT_RECORDED")

    def test_wrong_target_binding_not_consumed(self):
        self.record();self.claim();prepared=self.prepare();request=prepared["request"]
        request["capital_intent_sha256"]="f"*64
        self.publish(request,prepared["decision"])
        with self.assertRaisesRegex(ValueError,"CAPITAL_PUBLICATION_BINDING_MISMATCH"):
            self.journal.reconcile(self.intent["event_id"],target_store=self.fixture.targets)

    def test_ordinary_cash_confirmation_does_not_create_capital_intent(self):
        self.fixture.event("CASH_CONFIRM",amount="1100",cash_basis="TOTAL_UNINVESTED")
        self.assertFalse(self.journal.path.exists())
        self.assertEqual(self.journal.reconcile("absent",target_store=self.fixture.targets)["status"],"NOT_FOUND")

    def test_new_event_id_cannot_bypass_unresolved_claim_for_same_target(self):
        self.record();self.claim()
        other=deepcopy(self.intent);other["event_id"]="retry-with-new-id"
        self.journal.record(other,account_state=self.state,previous_target=self.target)
        with self.assertRaisesRegex(ValueError,"CAPITAL_TARGET_ALREADY_CLAIMED"):
            self.journal.claim_selection_once(other["event_id"],account_state=self.state,previous_target=self.target)

    def test_prepared_resume_publish_only_and_old_decision_cannot_consume(self):
        self.record();self.claim();prepared=self.prepare()
        self.assertEqual(self.journal.reconcile(self.intent["event_id"],target_store=self.fixture.targets)["status"],
                         "PREPARED_PUBLISH_ONLY")
        self.assertFalse(self.claim()["may_start_selection"])
        self.assertEqual(self.prepare(),prepared)
        self.publish(prepared["request"])  # Old decision, merely relabeled with new capital request.
        with self.assertRaisesRegex(ValueError,"CAPITAL_PUBLISHED_DECISION_MISMATCH"):
            self.journal.reconcile(self.intent["event_id"],target_store=self.fixture.targets)

    def test_bad_snapshot_profile_and_source_cannot_prepare(self):
        self.record();self.claim()
        for mode in ("account","revision","cash","status","profile","source"):
            with self.subTest(mode=mode):
                args=self.prepared_arguments();decision=args["decision"];payload=decision["payload"]
                binding=payload["input_binding"]
                if mode=="account":binding["account_id"]="other"
                elif mode=="revision":binding["account_revision"]="f"*64
                elif mode=="cash":binding["execution_context"]["available_cash"]="1250"
                elif mode=="status":decision["status"]="SEARCH_INCOMPLETE"
                elif mode=="profile":args["profile"]["max_objective_evaluations"]=101
                else:args["source_files"]["fixture-source"]=b"modified"
                payload["input_id"]=sha256(canonical(binding)).hexdigest()
                decision["decision_id"]=sha256(canonical(payload)).hexdigest()
                with self.assertRaises(ValueError):
                    self.journal.prepare(self.intent["event_id"],**args)
        self.assertEqual(self.journal.reconcile(self.intent["event_id"],target_store=self.fixture.targets)["status"],
                         "RECOVERY_REQUIRED")

    def test_prepared_result_is_immutable_and_fresh_revision_required_for_publish(self):
        self.record();self.claim();self.prepare()
        args=self.prepared_arguments();args["profile"]["source_pins"]={"other":"f"*64}
        with self.assertRaises(ValueError):self.journal.prepare(self.intent["event_id"],**args)
        self.fixture.event("CASH_CONFIRM",amount="1000",cash_basis="TOTAL_UNINVESTED")
        with self.assertRaisesRegex(ValueError,"STALE_REVISION"):
            self.journal.publication_candidate(self.intent["event_id"],
                account_state=self.fixture.accounts.read(),previous_target=self.target)

    def test_concurrent_claimers_allow_only_one_selection(self):
        self.record()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.claim(),range(2)))
        self.assertEqual(sum(r["may_start_selection"] for r in results),1)

    def test_prepared_corruption_preserved_and_refused(self):
        self.record();self.claim();self.prepare()
        with closing(sqlite3.connect(self.journal.path)) as con:
            con.execute("UPDATE prepared SET payload=? WHERE event_id=?",("{}",self.intent["event_id"]))
            con.commit()
        before=self.journal.path.read_bytes()
        with self.assertRaisesRegex(ValueError,"CAPITAL_PREPARED_CORRUPT"):
            self.journal.publication_candidate(self.intent["event_id"],account_state=self.state,previous_target=self.target)
        self.assertEqual(self.journal.path.read_bytes(),before)
