from __future__ import annotations

import shutil
import unittest
from argparse import Namespace
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

import scripts.ndx_dynamic_shadow_daily as daily_cli

from backtest.ndx_dynamic_shadow_activation_v2 import (
    ACTIVATION_MANIFEST,
    NdxDynamicShadowActivationV2Error,
    SYNTHETIC_E2E_MANIFEST,
    build_activation_v2_readiness,
    validate_versioned_activation_contracts,
    verify_activation_v2_manifest,
    verify_append_only_calendar_prefix,
    verify_synthetic_e2e_manifest,
)
from backtest.ndx_dynamic_shadow_daily import canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = (
    "ndx_portfolio_objective_v1.yaml",
    "ndx_portfolio_objective_v2.yaml",
    "ndx_dynamic_shadow_selector_registry_v1.yaml",
    "ndx_dynamic_shadow_selector_registry_v2.yaml",
    "ndx_dynamic_shadow_runner_v1.yaml",
    "ndx_dynamic_shadow_runner_v2.yaml",
)


def _contract_fixture(directory: str) -> Path:
    root = Path(directory)
    target = root / "config"
    target.mkdir(parents=True)
    for name in CONTRACTS:
        shutil.copy2(ROOT / "config" / name, target / name)
    return root


class DynamicShadowActivationV2Tests(unittest.TestCase):
    def test_calendar_activation_prefix_allows_only_tail_extension(self) -> None:
        records = [
            {"session_date": "2026-09-01", "record_sha256": "a" * 64},
            {"session_date": "2026-09-02", "record_sha256": "b" * 64},
            {"session_date": "2026-09-03", "record_sha256": "c" * 64},
        ]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.jsonl"
            current = root / "current.jsonl"
            prefix.write_text(
                "\n".join(__import__("json").dumps(value, sort_keys=True) for value in records[:2]) + "\n",
                encoding="utf-8",
            )
            current.write_text(
                "\n".join(__import__("json").dumps(value, sort_keys=True) for value in records) + "\n",
                encoding="utf-8",
            )
            audit = verify_append_only_calendar_prefix(prefix, current)
            self.assertEqual(audit["appended_rows"], 1)
            changed = [dict(records[0]), records[1], records[2]]
            changed[0]["session_date"] = "2026-08-31"
            current.write_text(
                "\n".join(__import__("json").dumps(value, sort_keys=True) for value in changed) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                NdxDynamicShadowActivationV2Error, "prefix changed"
            ):
                verify_append_only_calendar_prefix(prefix, current)

    def test_scheduled_daily_execute_reverifies_activation_before_running(self) -> None:
        order: list[str] = []

        def verified(*args, **kwargs):
            order.append("activation")
            return {"status": "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION"}

        def executed(*args, **kwargs):
            order.append("daily")
            return {"status": "RESEARCH_DAILY_COMPLETE"}

        with patch.object(
            daily_cli, "parse_args",
            return_value=Namespace(execute=True, readiness=False, max_search_jobs=0),
        ), patch.object(daily_cli, "single_instance_lock", return_value=nullcontext()), patch(
            "backtest.ndx_dynamic_shadow_activation_v2.verify_activation_v2_manifest",
            side_effect=verified,
        ), patch.object(daily_cli, "execute", side_effect=executed):
            self.assertEqual(daily_cli.main(), 0)
        self.assertEqual(order, ["activation", "daily"])

    def test_activation_with_healthy_calendar_fixture(self) -> None:
        synthetic = verify_synthetic_e2e_manifest(
            ROOT / SYNTHETIC_E2E_MANIFEST, repository_root=ROOT,
        )
        self.assertEqual(synthetic["scenario"]["dynamic_holding_counts"], [1, 2])
        self.assertEqual(synthetic["scenario"]["selector_lane_count"], 10)
        healthy_calendar_fixture = {
            "verified": True,
            "decision_eligible_session_count": 0,
            "error": None,
        }
        with patch(
            "backtest.ndx_dynamic_shadow_activation_v2."
            "verify_observed_session_calendar_manifest",
            return_value=healthy_calendar_fixture,
        ):
            activation = verify_activation_v2_manifest(
                ROOT / ACTIVATION_MANIFEST, repository_root=ROOT,
            )
        self.assertEqual(
            activation["status"], "READY_FOR_RESEARCH_AUTOMATION_REGISTRATION"
        )
        self.assertEqual(
            activation["prospective_evidence"]["status_at_activation"],
            "NOT_DUE_AT_ACTIVATION",
        )
        self.assertEqual(activation["runtime_verification"]["status"], "NOT_DUE_YET")
        self.assertTrue(activation["research_automation_registration_allowed"])
        self.assertFalse(activation["promotion_allowed"])
        self.assertFalse(activation["live_mutation_allowed"])

    def test_resigned_synthetic_permission_tamper_is_rejected(self) -> None:
        source = ROOT / SYNTHETIC_E2E_MANIFEST
        with TemporaryDirectory(dir=ROOT / "data/cache/research") as directory:
            path = Path(directory) / "manifest.json"
            value = yaml.safe_load(source.read_text(encoding="utf-8"))
            value["promotion_allowed"] = True
            unsigned = dict(value)
            unsigned.pop("manifest_sha256", None)
            value["manifest_sha256"] = canonical_sha256(unsigned)
            path.write_text(
                __import__("json").dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                NdxDynamicShadowActivationV2Error, "boundary changed"
            ):
                verify_synthetic_e2e_manifest(path, repository_root=ROOT)

    def test_v2_contracts_preserve_v1_semantics_and_live_boundary(self) -> None:
        result = validate_versioned_activation_contracts(ROOT)
        self.assertEqual(result["status"], "VERSIONED_ACTIVATION_CONTRACTS_VERIFIED")
        self.assertFalse(result["objective_semantics_changed"])
        self.assertFalse(result["selection_semantics_changed"])
        self.assertFalse(result["runner_semantics_changed"])
        self.assertEqual(result["research_track"], "portfolio_optimization")
        self.assertFalse(result["migration_control_included"])
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["live_mutation_allowed"])

    def test_componentwise_gate_or_dynamic_k_cannot_be_relaxed(self) -> None:
        with TemporaryDirectory() as directory:
            root = _contract_fixture(directory)
            path = root / "config/ndx_portfolio_objective_v2.yaml"
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            value["objective_semantics"]["formal_target_gate"] = "scalar_l1"
            path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(
                NdxDynamicShadowActivationV2Error, "benchmark semantics"
            ):
                validate_versioned_activation_contracts(root)

        with TemporaryDirectory() as directory:
            root = _contract_fixture(directory)
            path = root / "config/ndx_portfolio_objective_v2.yaml"
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            value["portfolio_optimization"]["cardinality"] = "8"
            path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(
                NdxDynamicShadowActivationV2Error, "dynamic portfolio semantics"
            ):
                validate_versioned_activation_contracts(root)

    def test_v1_hash_change_or_live_permission_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = _contract_fixture(directory)
            path = root / "config/ndx_portfolio_objective_v1.yaml"
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxDynamicShadowActivationV2Error, "locked v1 contract hash changed"
            ):
                validate_versioned_activation_contracts(root)

        with TemporaryDirectory() as directory:
            root = _contract_fixture(directory)
            path = root / "config/ndx_dynamic_shadow_runner_v2.yaml"
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            value["activation_gate"]["promotion_allowed"] = True
            path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(
                NdxDynamicShadowActivationV2Error, "activation boundary"
            ):
                validate_versioned_activation_contracts(root)

    def test_not_yet_due_real_prefix_does_not_create_registration_cycle(self) -> None:
        with patch(
            "backtest.ndx_dynamic_shadow_activation_v2.verify_synthetic_e2e_manifest",
            side_effect=NdxDynamicShadowActivationV2Error("missing fixture"),
        ):
            result = build_activation_v2_readiness(ROOT, as_of_date="2026-09-05")
        self.assertEqual(result["implementation_readiness"], "BLOCKED")
        self.assertIn(
            "REBUILDABLE_SYNTHETIC_E2E_EVIDENCE_MISSING",
            result["implementation_blockers"],
        )
        self.assertFalse(result["prospective_evidence_due"])
        self.assertEqual(result["prospective_evidence_status"], "NOT_DUE_YET")
        self.assertNotIn(
            "PROSPECTIVE_DAILY_DOUBLE_BENCHMARK_PREFIX_NOT_YET_VERIFIED",
            result["blockers"],
        )
        self.assertFalse(result["research_automation_registration_allowed"])
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["live_mutation_allowed"])

    def test_due_date_requires_real_prefix_without_widening_live_authority(self) -> None:
        with patch(
            "backtest.ndx_dynamic_shadow_activation_v2.verify_observed_session_calendar_manifest",
            return_value={"verified": True, "decision_eligible_session_count": 1},
        ), patch(
            "backtest.ndx_dynamic_shadow_activation_v2.verify_synthetic_e2e_manifest",
            return_value={"status": "REBUILDABLE_SYNTHETIC_E2E_COMPLETE_RESEARCH_ONLY"},
        ), patch(
            "backtest.ndx_dynamic_shadow_daily.verify_daily_run_manifest",
            side_effect=ValueError("missing due prefix"),
        ):
            result = build_activation_v2_readiness(ROOT, as_of_date="2026-10-01")
        self.assertTrue(result["prospective_evidence_due"])
        self.assertIn(
            "PROSPECTIVE_DAILY_DOUBLE_BENCHMARK_PREFIX_NOT_YET_VERIFIED",
            result["blockers"],
        )
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["live_mutation_allowed"])


if __name__ == "__main__":
    unittest.main()
