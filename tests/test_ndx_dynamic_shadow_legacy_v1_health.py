from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backtest.ndx_dynamic_shadow_legacy_v1_health import (
    DEGRADED_STATUS,
    HEALTHY_STATUS,
    build_legacy_v1_health,
)


class LegacyV1HealthTests(unittest.TestCase):
    def test_healthy_diagnostic_never_grants_registration_or_live_authority(self) -> None:
        with TemporaryDirectory() as directory:
            payload = build_legacy_v1_health(
                Path(directory),
                calendar_verifier=lambda *_: {"verified": True, "error": None},
                activation_verifier=lambda *_args, **_kwargs: {
                    "status": "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION",
                },
                runner_readiness_builder=lambda *_args, **_kwargs: {
                    "status": "BLOCKED_FAIL_CLOSED",
                    "observed_session_calendar": {"verified": True, "error": None},
                    "blockers": [{"blocker_id": "FUTURE_INPUT_NOT_DUE"}],
                },
                registration_probe=lambda *_: {
                    "passed": True, "returncode": 0, "reason": None,
                },
            )
        self.assertEqual(payload["status"], HEALTHY_STATUS)
        self.assertEqual(
            payload["health_scope"],
            "legacy_calendar_and_activation_evidence_only",
        )
        self.assertTrue(payload["legacy_evidence_chain_currently_reproducible"])
        self.assertFalse(payload["runner_execution_ready"])
        self.assertFalse(payload["authoritative_for_task_registration"])
        self.assertFalse(payload["research_automation_registration_allowed"])
        self.assertFalse(payload["promotion_allowed"])
        self.assertFalse(payload["live_mutation_allowed"])

    def test_arbitrary_runtime_failure_is_preserved_without_hardcoded_ticker_or_date(self) -> None:
        reason = "vendor evidence changed at an arbitrary future coordinate"
        with TemporaryDirectory() as directory:
            payload = build_legacy_v1_health(
                Path(directory),
                calendar_verifier=lambda *_: {"verified": False, "error": reason},
                activation_verifier=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    ValueError("activation consumes unhealthy legacy evidence")
                ),
                runner_readiness_builder=lambda *_args, **_kwargs: {
                    "status": "BLOCKED_FAIL_CLOSED",
                    "observed_session_calendar": {"verified": False, "error": reason},
                    "blockers": [{
                        "blocker_id": "VERIFIED_US_SESSION_CALENDAR_MANIFEST_MISSING_OR_INVALID",
                    }],
                },
                registration_probe=lambda *_: {
                    "passed": False, "returncode": 2,
                    "reason": "registration verifier rejected legacy runtime",
                },
            )
        self.assertEqual(payload["status"], DEGRADED_STATUS)
        self.assertFalse(payload["legacy_evidence_chain_currently_reproducible"])
        self.assertFalse(payload["runner_execution_ready"])
        self.assertEqual(
            payload["checks"]["observed_calendar_v1_current_runtime"]["reason"],
            reason,
        )
        self.assertIn(
            "activation consumes unhealthy legacy evidence",
            payload["checks"]["activation_v2_current_runtime"]["reason"],
        )
        self.assertFalse(payload["research_automation_registration_allowed"])


if __name__ == "__main__":
    unittest.main()
