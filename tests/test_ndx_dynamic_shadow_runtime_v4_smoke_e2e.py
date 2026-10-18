"""Artifact smoke on an actual synthetic daily4 economic run, not a task smoke."""
import unittest
from unittest.mock import patch

import test_ndx_dynamic_shadow_daily_v4_execution_e2e as execution_fixture
from scripts import ndx_dynamic_shadow_runtime_v4_smoke as smoke


class RuntimeV4SmokeE2ETests(unittest.TestCase):
    def test_actual_daily_output_passes_independent_artifact_smoke(self):
        daily = execution_fixture.daily
        execute = daily.execute
        proofs = []

        def observed_execute():
            # The economic fixture has no broker/state input. Supply explicit
            # synthetic empty protected files in its temporary root only.
            self.assertNotEqual(daily.ROOT, smoke.ROOT)
            for relative in ("data/state.json", "data/broker_positions.json"):
                path = daily.ROOT / relative
                if not path.exists():
                    path.write_text("{}", encoding="utf-8")
            before = smoke.snapshot(daily.ROOT)
            result = execute()
            proof = smoke.verify(daily.ROOT, before=before)
            self.assertEqual(proof["evidence_level"], "ECONOMIC_PATHS_VERIFIED")
            self.assertEqual(proof["economic_replay"]["economic_lane_count"], 11)
            self.assertIs(proof["task_execution_verified_by_this_tool"], False)
            self.assertEqual(smoke.verify(daily.ROOT, expected=proof), proof)
            proofs.append(proof)
            return result

        with patch.object(smoke, "datetime", execution_fixture.ExecutionClock), \
                patch.object(daily, "execute", side_effect=observed_execute):
            execution_fixture.Daily4ExecutionE2ETests().exercise(verify_restart=False)
        self.assertEqual(len(proofs), 1)


if __name__ == "__main__":
    unittest.main()
