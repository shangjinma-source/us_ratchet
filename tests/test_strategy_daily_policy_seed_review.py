from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_daily_policy_seed_review import review_initial_policy_seed
import test_strategy_profiled_daily_packet_admission as fixtures


class PolicySeedReviewTests(unittest.TestCase):
    def fixture(self, directory):
        case = fixtures.ProfiledPacketTests().setup_case(directory)
        root = Path(directory)
        receipt = json.loads((root / "parent.json").read_bytes())
        receipt["release_sha256"] = None
        raw = canonical(receipt)
        release = (root / "release.json").read_bytes()
        return case, dict(
            state=case.state, target=case.target, now=case.clock[0].isoformat(),
            event_id="isolated-initial-policy-review",
            release_bytes=release, trusted_release_sha256=sha256(release).hexdigest(),
            receipt_bytes=raw, trusted_receipt_sha256=sha256(raw).hexdigest(),
            files={name: (root / name).read_bytes() for name in receipt["source_sha256"]},
            calendar_bytes=(root / "calendar.json").read_bytes(),
        )

    def test_explicit_review_retains_original_bytes_and_capture_time(self):
        with TemporaryDirectory() as directory:
            case, args = self.fixture(directory)
            saved = deepcopy(args)
            database = case.store.path.read_bytes()
            result = review_initial_policy_seed(**args)
            self.assertEqual(result["status"], "POLICY_BOUND_SEED_REVIEW_READY_NOT_PUBLISHED")
            self.assertFalse(result["published"])
            self.assertFalse(result["policy_approved"])
            self.assertEqual(result["receipt"]["release_sha256"], args["trusted_release_sha256"])
            self.assertEqual(result["source_received_at"],
                             json.loads(args["receipt_bytes"])["source_received_at"])
            self.assertEqual(result["files"]["server-parent/" +
                             args["trusted_receipt_sha256"] + ".json"], args["receipt_bytes"])
            self.assertEqual(args, saved)
            self.assertEqual(case.store.path.read_bytes(), database)

    def test_unapproved_release_or_changed_source_cannot_be_bound(self):
        with TemporaryDirectory() as directory:
            _, args = self.fixture(directory)
            changed = dict(args)
            release = json.loads(args["release_bytes"])
            release["approved"] = False
            changed["release_bytes"] = canonical(release)
            changed["trusted_release_sha256"] = sha256(changed["release_bytes"]).hexdigest()
            with self.assertRaisesRegex(ValueError, "PROFILE_RELEASE_NOT_APPROVED"):
                review_initial_policy_seed(**changed)
            changed = deepcopy(args)
            name = next(iter(changed["files"]))
            changed["files"][name] += b"tampered"
            with self.assertRaisesRegex(ValueError, "PARENT_SOURCE_HASH_MISMATCH"):
                review_initial_policy_seed(**changed)

    def test_bound_seed_cannot_silently_switch_policy(self):
        with TemporaryDirectory() as directory:
            _, args = self.fixture(directory)
            receipt = json.loads(args["receipt_bytes"])
            receipt["release_sha256"] = "f" * 64
            args["receipt_bytes"] = canonical(receipt)
            args["trusted_receipt_sha256"] = sha256(args["receipt_bytes"]).hexdigest()
            with self.assertRaisesRegex(ValueError, "INITIAL_POLICY_REVIEW_REQUIRES_UNBOUND_SEED"):
                review_initial_policy_seed(**args)


if __name__ == "__main__":
    unittest.main()
