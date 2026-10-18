from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backtest.ndx_cardinality_capital_replay_pareto_summary import (
    NdxCardinalityCapitalReplayParetoSummaryError,
    build_capital_replay_pareto_summary,
    verify_pareto_bundle,
    write_pareto_bundle,
)
from backtest.ndx_cardinality_capital_replay_summary import (
    OUTPUT_RELATIVE as SOURCE_OUTPUT_RELATIVE,
    write_summary_bundle,
)
from test_ndx_cardinality_capital_replay_summary import (
    ReplayFixture,
    _sha,
    _write_csv,
    _write_json,
)


def _publish_v1(fixture: ReplayFixture) -> Path:
    write_summary_bundle(
        fixture.build_summary(), output_dir=fixture.root / SOURCE_OUTPUT_RELATIVE
    )
    return fixture.root / SOURCE_OUTPUT_RELATIVE / "manifest.json"


def _candidate_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _rebind_candidate(manifest_path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_path = Path(manifest["artifacts"]["candidates"]["path"])
    _write_csv(candidate_path, rows, fields)
    manifest["artifacts"]["candidates"]["rows"] = len(rows)
    manifest["artifacts"]["candidates"]["sha256"] = _sha(candidate_path)
    _write_json(manifest_path, manifest)


class NdxCapitalReplayParetoSummaryTests(unittest.TestCase):
    def test_direct_cli_help_bootstraps_repository_imports(self) -> None:
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(root / "scripts/ndx_cardinality_capital_replay_pareto_summary.py"),
                "--help",
            ],
            cwd=Path(tempfile.gettempdir()),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--dry-run", completed.stdout)

    def test_rebuilds_all_per_coordinate_pareto_without_cross_group_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            source = _publish_v1(fixture)
            report = build_capital_replay_pareto_summary(
                source, repository_root=fixture.root
            )
            self.assertEqual(report["verified_child_job_count"], 3)
            self.assertEqual(report["evaluator_group_count"], 2)
            self.assertTrue(
                report["all_nondominated_candidates_emitted_without_top_n_truncation"]
            )
            self.assertFalse(report["cross_selection_date_ranking_allowed"])
            self.assertEqual(
                report["rolling_return_metric_semantics"],
                "ANNUALIZED_ROLLING_WINDOW_RETURN_AS_FROZEN_BY_SOURCE_EVALUATOR",
            )
            starts = [
                start
                for group in report["evaluator_groups"]
                for start in group["per_start"]
            ]
            self.assertEqual(len(starts), 3)
            self.assertTrue(all(start["pareto_candidate_rows"] == 1 for start in starts))
            self.assertEqual(
                {start["source_reported_replay_eligible_rows"] for start in starts}, {1}
            )
            preference = next(
                start["user_preference_reference"]
                for start in starts
                if start["selection_date"] == "2024-01-02"
            )
            self.assertEqual(
                preference["status"], "PRESENT_SOURCE_REPORTED_REPLAY_ELIGIBLE"
            )
            self.assertTrue(preference["included_in_source_reported_eligible_pareto"])

    def test_dominated_candidate_is_excluded_but_full_nondominated_row_is_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            child = fixture.child_manifests[0]
            manifest = json.loads(child.read_text(encoding="utf-8"))
            path = Path(manifest["artifacts"]["candidates"]["path"])
            fields, rows = _candidate_rows(path)
            dominated = dict(rows[1])
            dominated["portfolio_id"] = "dominated"
            dominated.update(
                {
                    "declared_constraints_passed": "True",
                    "whole_lot_executable_all_windows": "True",
                    "whole_lot_constraints_preserved_all_days": "True",
                    "constraint_failure_reasons": "",
                    "return_p50": "0.01",
                    "return_p10": "-0.20",
                    "max_drawdown_p50": "0.30",
                    "max_drawdown_p90": "0.40",
                    "target_012922_distance": "0.80",
                    "turnover": "0.50",
                }
            )
            rows.append(dominated)
            _rebind_candidate(child, rows, fields)
            source = _publish_v1(fixture)
            report = build_capital_replay_pareto_summary(
                source, repository_root=fixture.root
            )
            start = next(
                start
                for group in report["evaluator_groups"]
                for start in group["per_start"]
                if start["selection_date"] == "2024-01-02"
            )
            self.assertEqual(start["source_reported_replay_eligible_rows"], 2)
            self.assertEqual(start["pareto_portfolio_ids"], ["p4"])
            emitted = start["pareto_candidates"][0]
            self.assertEqual(emitted["tickers"], ["AMAT", "AVGO", "CDNS", "GOOG"])
            self.assertEqual(emitted["weights"]["AMAT"], 0.25)
            self.assertIn("continuous_whole_lot_path", emitted)
            self.assertIn("rolling_training_statistics", emitted)

    def test_user_preference_is_retained_when_source_reports_it_ineligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            child = fixture.child_manifests[0]
            manifest = json.loads(child.read_text(encoding="utf-8"))
            path = Path(manifest["artifacts"]["candidates"]["path"])
            fields, rows = _candidate_rows(path)
            rows[0].update(
                {
                    "declared_constraints_passed": "False",
                    "whole_lot_executable_all_windows": "False",
                    "whole_lot_constraints_preserved_all_days": "False",
                    "constraint_failure_reasons": "WHOLE_LOT_EXECUTABILITY_FAILED",
                }
            )
            rows[1].update(
                {
                    "portfolio_id": "eligible_other",
                    "declared_constraints_passed": "True",
                    "whole_lot_executable_all_windows": "True",
                    "whole_lot_constraints_preserved_all_days": "True",
                    "constraint_failure_reasons": "",
                }
            )
            _rebind_candidate(child, rows, fields)
            source = _publish_v1(fixture)
            report = build_capital_replay_pareto_summary(
                source, repository_root=fixture.root
            )
            start = next(
                start
                for group in report["evaluator_groups"]
                for start in group["per_start"]
                if start["selection_date"] == "2024-01-02"
            )
            preference = start["user_preference_reference"]
            self.assertEqual(
                preference["status"], "PRESENT_SOURCE_REPORTED_REPLAY_INELIGIBLE"
            )
            self.assertFalse(preference["included_in_source_reported_eligible_pareto"])
            self.assertEqual(
                preference["candidate"]["failure_reasons"],
                ["WHOLE_LOT_EXECUTABILITY_FAILED"],
            )

    def test_v1_per_start_hash_binding_rejects_rebound_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary))
            source = _publish_v1(fixture)
            child = fixture.child_manifests[0]
            manifest = json.loads(child.read_text(encoding="utf-8"))
            path = Path(manifest["artifacts"]["candidates"]["path"])
            fields, rows = _candidate_rows(path)
            rows[0]["return_p50"] = "0.13"
            _rebind_candidate(child, rows, fields)
            with self.assertRaisesRegex(
                NdxCardinalityCapitalReplayParetoSummaryError,
                "published v1 child manifest binding changed",
            ):
                build_capital_replay_pareto_summary(
                    source, repository_root=fixture.root
                )

    def test_bundle_is_atomic_immutable_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary) / "repo")
            source = _publish_v1(fixture)
            report = build_capital_replay_pareto_summary(
                source, repository_root=fixture.root
            )
            output = Path(temporary) / "pareto"
            first = write_pareto_bundle(report, output_dir=output)
            second = write_pareto_bundle(report, output_dir=output)
            self.assertEqual(first, second)
            verify_pareto_bundle(output / "manifest.json", repository_root=fixture.root)
            (output / "summary.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxCardinalityCapitalReplayParetoSummaryError,
                "artifact hash changed",
            ):
                verify_pareto_bundle(
                    output / "manifest.json", repository_root=fixture.root
                )

    def test_resigned_false_pareto_result_is_rebuilt_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplayFixture(Path(temporary) / "repo")
            source = _publish_v1(fixture)
            report = build_capital_replay_pareto_summary(
                source, repository_root=fixture.root
            )
            output = Path(temporary) / "pareto"
            write_pareto_bundle(report, output_dir=output)
            summary_path = output / "summary.json"
            manifest_path = output / "manifest.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["evaluator_groups"][0]["per_start"][0][
                "pareto_portfolio_ids"
            ] = ["attacker-selected"]
            summary_raw = (
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            summary_path.write_bytes(summary_raw)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["summary_json"]["sha256"] = hashlib.sha256(
                summary_raw
            ).hexdigest()
            payload = dict(manifest)
            payload.pop("manifest_sha256")
            canonical = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            manifest["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
            _write_json(manifest_path, manifest)
            with self.assertRaisesRegex(
                NdxCardinalityCapitalReplayParetoSummaryError,
                "does not match a fresh rebuild",
            ):
                verify_pareto_bundle(
                    manifest_path, repository_root=fixture.root
                )


if __name__ == "__main__":
    unittest.main()
