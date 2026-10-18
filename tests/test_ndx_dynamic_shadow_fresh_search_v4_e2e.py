"""Real same-source candidate/controller/leaf/final acceptance with a process bridge."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

import fixture_fresh_search_v4_e2e as fixture
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance


class SameSourceFreshSearchE2ETests(unittest.TestCase):
    def test_eight_real_shards_acceptance_resume_and_corrupt_checkpoint(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            path, watched = fixture.prepare(root)
            calls = []
            fixture.bindings(stack, root, calls)
            contract = "config/ndx_dynamic_shadow_fresh_search_v1.yaml"
            self.assertEqual((root / contract).read_bytes(), (fixture.REAL_ROOT / contract).read_bytes())
            eligible = pd.read_csv(path.parent / "eligible_securities.csv", keep_default_na=False)
            exact = eligible.loc[eligible.ticker.ne("NEW")]
            self.assertEqual(set(exact.ticker), {"O000", "O001", "O002"})
            self.assertTrue(exact.ticker_lifecycle_rule_id.eq("").all())
            result = acceptance.execute(path)
            self.assertTrue(result["v4_verified"])
            self.assertEqual(len(calls), 8)
            checkpoints = list((root / acceptance.SEARCH).rglob("checkpoint.json"))
            self.assertEqual(len(checkpoints), 8)
            final_root = root / acceptance.SEARCH / "final" / "2026-10-01"
            jobs = pd.read_csv(final_root / "job_plan.csv")
            for track in ("strict_technology", "technology_plus_adjacent"):
                self.assertEqual(sorted(jobs.loc[jobs.universe_track == track, "holding_count"]), [1, 2, 3, 4])
            candidates = pd.read_csv(final_root / "candidates.csv")
            below_four = candidates.loc[candidates.holding_count.lt(4)]
            self.assertEqual(set(below_four.holding_count), {1, 2, 3})
            self.assertTrue(below_four.declared_constraints_passed.eq(False).all())
            self.assertTrue(below_four.declared_security_top3_weight_passed.eq(False).all())
            self.assertTrue(candidates.loc[candidates.holding_count.eq(4), "declared_constraints_passed"].eq(True).all())
            roles = pd.read_csv(final_root / "role_lock.csv")
            selected = roles.loc[roles.policy_role.ne("USER_PREFERENCE")]
            self.assertEqual(len(selected), 8)
            self.assertTrue(selected.holding_count.eq(4).all())
            self.assertTrue(roles.loc[roles.policy_role.eq("USER_PREFERENCE"), "status"].eq("REFERENCE_UNAVAILABLE_NOT_REPLACED").all())
            receipt = Path(result["receipt_path"])
            before = receipt.read_bytes()
            self.assertTrue(acceptance.execute(path)["v4_verified"])
            self.assertEqual(len(calls), 8)
            self.assertEqual(receipt.read_bytes(), before)
            # Test the actual controller's checkpoint validator, not an acceptance
            # shortcut (an already verified receipt intentionally skips the controller).
            checkpoints[0].write_bytes(b"corrupt checkpoint")
            with self.assertRaisesRegex(fixture.search.NdxDynamicShadowFreshSearchError, "cannot read shard checkpoint"):
                fixture.controller.execute(path)
            self.assertEqual(len(calls), 8)
            for source, digest in watched.items():
                self.assertEqual(acceptance.digest(source), digest)


if __name__ == "__main__":
    unittest.main()
