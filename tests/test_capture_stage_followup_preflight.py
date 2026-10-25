"""Saved-byte-only tests; neither the old attempts nor publication index is written."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.preflight_capture_stage_followup_recovery import preflight, CALENDAR

ROOT = Path(__file__).resolve().parents[1]
EVENT = "data/quantity_v2_observations/events/2026-10-16/05b9d3d0dcb949c09dd3b0fc720a3295.json"
NOW = datetime.fromisoformat("2026-10-20T12:50:00+00:00")


def saved_request():
    def ref(path):
        return dict(path=path, sha256=sha256((ROOT/path).read_bytes()).hexdigest())
    event = ref(EVENT)
    attempt = "data/quantity_v2_followup/attempts/"+event["sha256"]+"/2026-10-19"
    paths = dict(event=EVENT, started=attempt+"/started.json", failed=attempt+"/failed.json",
                 completion=attempt+"/daily-0/completion_index.json",
                 original_raw=attempt+"/daily-0/SNDK.response.bin",
                 original_receipt=attempt+"/daily-0/SNDK.receipt.json",
                 original_decoded=attempt+"/daily-0/SNDK.decoded.json",
                 later_raw="tmp/daily_signal_sndk_source_capture_20261020_v1/daily.response.bin",
                 later_receipt="tmp/daily_signal_sndk_source_capture_20261020_v1/daily.receipt.json")
    return dict(schema="CAPTURE_STAGE_FOLLOWUP_REVIEW_V1", target_session="2026-10-19",
                references={k: ref(v) for k, v in paths.items()},
                attempt_source_hashes={p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest()
                                      for p in (ROOT/attempt).rglob("*") if p.is_file()})


class CaptureStagePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request = saved_request()
        names = set(self.request["attempt_source_hashes"])
        names |= {r["path"] for r in self.request["references"].values()}
        calendar = json.loads((ROOT/CALENDAR).read_bytes())
        names |= set(calendar["source_hashes"]) | {CALENDAR}
        event = json.loads((ROOT/EVENT).read_bytes())
        names |= {"data/quantity_v2_observations/"+r["path"] for r in event["captures"]}
        for name in names:
            dest = self.root/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT/name).read_bytes())

    def evaluate(self):
        return preflight(root=self.root, request=self.request, now=NOW)

    def test_complete_bar_revision_candidate_keeps_missing_reviews_and_no_writes(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.evaluate()
        self.assertEqual(result["status"], "ADMISSIBLE_FOR_REVIEW", result)
        self.assertEqual(result["differences"]["open"]["kind"], "PROVIDER_REVISION")
        self.assertEqual(result["differences"]["close"]["kind"], "MISSING_VALUE")
        self.assertFalse(result["known_at_original_event"])
        self.assertFalse(result["publication_allowed"])
        self.assertIn("FOLLOWUP_IDENTITY_AND_UNIT_REVIEW", result["unresolved"])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes()
                                 for p in self.root.rglob("*") if p.is_file()})

    def test_changed_bytes_missing_closure_and_wrong_security_block(self):
        original = deepcopy(self.request)
        self.request["references"]["later_raw"]["sha256"] = "0"*64
        self.assertEqual(self.evaluate()["reason"], "SOURCE_CHANGED")
        self.request = deepcopy(original)
        self.request["attempt_source_hashes"].pop(next(iter(self.request["attempt_source_hashes"])))
        self.assertEqual(self.evaluate()["reason"], "ATTEMPT_CLOSURE")
        self.request = original
        ref = self.request["references"]["later_raw"]
        raw = json.loads((self.root/ref["path"]).read_bytes())
        raw["chart"]["result"][0]["meta"]["symbol"] = "OTHER"
        body = json.dumps(raw).encode()
        (self.root/ref["path"]).write_bytes(body); ref["sha256"] = sha256(body).hexdigest()
        receipt_ref = self.request["references"]["later_receipt"]
        receipt = json.loads((self.root/receipt_ref["path"]).read_bytes())
        receipt.update(sha256=ref["sha256"], bytes=len(body))
        body = json.dumps(receipt).encode()
        (self.root/receipt_ref["path"]).write_bytes(body)
        receipt_ref["sha256"] = sha256(body).hexdigest()
        self.assertEqual(self.evaluate()["reason"], "PRICE_COORDINATE")

    def test_future_receipt_and_missing_original_do_not_promote(self):
        ref = self.request["references"]["later_receipt"]
        receipt = json.loads((self.root/ref["path"]).read_bytes())
        receipt["received_at"] = "2026-10-21T12:00:00+00:00"
        body = json.dumps(receipt).encode()
        (self.root/ref["path"]).write_bytes(body); ref["sha256"] = sha256(body).hexdigest()
        self.assertEqual(self.evaluate()["reason"], "CAPTURE_TIME")
        (self.root/self.request["references"]["failed"]["path"]).unlink()
        self.assertEqual(self.evaluate()["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
