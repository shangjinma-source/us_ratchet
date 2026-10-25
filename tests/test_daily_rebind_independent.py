"""Independent review of same-session data rebinding, isolated stores only."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import unittest
from core.strategy_account_ledger import canonical
import test_strategy_daily_evidence_rebind as fixtures


class IndependentRebindTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.RebindTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_same_day_rebind_preserves_raw_units_received_and_policy(self):
        c=self.case
        original_files=deepcopy(c.files);parent=c.parent_bytes
        c.event("DIRECT_FILL",security_id="A",side="BUY",quantity=14,price="100",fees="0",
                executed_at=c.clock.isoformat())
        c.event("CASH_CONFIRM",amount="0",cash_basis="TOTAL_UNINVESTED")
        c.publish({"A":7})
        before=(c.accounts.path.read_bytes(),c.targets.path.read_bytes())
        now=c.clock+timedelta(minutes=1)
        result=c.run_rebind(now=now.isoformat());receipt=result["receipt"]
        self.assertEqual(result["status"],"REBOUND_EVIDENCE_READY_POLICY_UNCHANGED")
        self.assertIsNone(result["release_sha256"]);self.assertEqual(receipt["release_sha256"],None)
        self.assertEqual(receipt["source_received_at"],c.receipt["source_received_at"])
        self.assertEqual(receipt["available_at"],now.isoformat())
        normalized=json.loads(result["files"][receipt["normalized_inputs_path"]])
        old=json.loads(c.files[c.receipt["normalized_inputs_path"]])
        self.assertEqual(normalized["histories"],old["histories"])
        self.assertEqual(normalized["base_target"]["quantities"],{"A":7})
        for path,raw in original_files.items(): self.assertEqual(result["files"][path],raw)
        self.assertEqual(result["files"]["server-parent/"+c.parent_sha+".json"],parent)
        self.assertEqual((c.accounts.path.read_bytes(),c.targets.path.read_bytes()),before)
        self.assertEqual(c.files,original_files)

    def test_closed_cross_date_and_held_unknown_fail_without_receipt(self):
        c=self.case
        for time in (c.receipt["execution_session"]["close"],(c.clock+timedelta(days=1)).isoformat()):
            result=c.run_rebind(now=time)
            self.assertEqual(result["status"],"WAIT_NEW_SESSION_EVIDENCE")
            self.assertIsNone(result["receipt"]);self.assertIsNone(result["files"])
        c.event("DIRECT_FILL",security_id="UNKNOWN",side="BUY",quantity=1,price="1",fees="0",
                executed_at=c.clock.isoformat())
        result=c.run_rebind();self.assertEqual(result["status"],"WAIT_NEW_SECURITY_EVIDENCE")
        self.assertIsNone(result["receipt"])

    def test_rehashed_target_still_checks_input_id_and_pinned_parent(self):
        c=self.case
        target=deepcopy(c.targets.current())
        target["payload"]["decision"]["payload"]["input_id"]="f"*64
        decision=target["payload"]["decision"]
        decision["decision_id"]=sha256(canonical(decision["payload"])).hexdigest()
        target["target_id"]=sha256(canonical(target["payload"])).hexdigest()
        with self.assertRaisesRegex(ValueError,"REBIND_TARGET_INPUT_MISMATCH"):
            c.run_rebind(target=target)
        modified=deepcopy(c.receipt);modified["release_sha256"]="a"*64
        with self.assertRaisesRegex(ValueError,"PARENT_DAILY_RECEIPT_HASH_MISMATCH"):
            c.run_rebind(receipt_bytes=canonical(modified))

    def test_final_count_budget_includes_new_receipt_and_normalization(self):
        c=self.case
        files=deepcopy(c.files)
        for index in range(1999-len(files)): files["extra"+str(index)]=b"x"
        parent=deepcopy(c.receipt);parent["source_sha256"]={p:sha256(b).hexdigest() for p,b in files.items()}
        raw=canonical(parent)
        with self.assertRaisesRegex(ValueError,"REBOUND_SOURCE_DOMAIN_OR_BUDGET"):
            c.run_rebind(files=files,receipt_bytes=raw,trusted_receipt_sha256=sha256(raw).hexdigest())
