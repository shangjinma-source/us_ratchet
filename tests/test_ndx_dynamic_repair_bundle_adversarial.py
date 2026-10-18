"""Independent bundle-envelope attacks; fixtures use real economic engines."""
import json
import unittest

from backtest import ndx_dynamic_repair_research_bundle as bundle
import test_ndx_dynamic_repair_research_bundle as owner


class DynamicRepairEnvelopeAttacks(unittest.TestCase):
    def setUp(self):
        self.fixture = owner.DynamicRepairBundleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_manifest_cannot_smuggle_live_authority(self):
        run = self.fixture.build()
        path = run / "manifest.json"
        original = json.loads(path.read_bytes())
        for field in ("admission_allowed", "live_mutation_allowed", "order_creation_allowed"):
            with self.subTest(field=field):
                forged = dict(original, **{field: True})
                path.write_bytes(bundle.json_bytes(forged))
                with self.assertRaisesRegex(ValueError, "[Ss]chema|[Mm]anifest"):
                    bundle.verify(self.fixture.root, run)

    def test_capture_cannot_overstate_verified_decisions(self):
        first = next(iter(self.fixture.captured["selected_provenance_counts"]))
        self.fixture.captured["selected_provenance_counts"][first] += 1
        with self.assertRaisesRegex(ValueError, "[Cc]overage|[Cc]ount|[Pp]rovenance"):
            self.fixture.build()


if __name__ == "__main__":
    unittest.main()
