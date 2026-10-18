from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backtest import ndx_equal_weight_schedule_extension_summary as summary


ROOT = Path(__file__).resolve().parents[1]


def _row(track: str, index: int, transition: str, *, preference: bool = False):
    before_failed = transition.startswith("FAIL")
    after_failed = transition.endswith("FAIL")
    tickers = ["AMAT", "AVGO", "CDNS", "GOOG"] if preference else [
        f"{track[:1].upper()}{index:03d}A",
        f"{track[:1].upper()}{index:03d}B",
        f"{track[:1].upper()}{index:03d}C",
        f"{track[:1].upper()}{index:03d}D",
    ]
    candidate_key = f"{0 if track == 'strict_technology' else 1:x}{index:023x}"
    return_change = 0.01 if (
        (track == "strict_technology" and index < 18)
        or (track == "technology_plus_adjacent" and index < 115)
    ) else -0.01
    dd_change = 0.0
    if track == "strict_technology" and index == 104:
        dd_change = 0.006549759633092567
    elif index < (2 if track == "strict_technology" else 3):
        dd_change = -0.001
    nonworse = (
        (track == "strict_technology" and index < 18)
        or (track == "technology_plus_adjacent" and index < 115)
    )
    if after_failed:
        if track == "strict_technology":
            reason = "RISK_CHAIN_TOP1_WEIGHT" if index == 104 else "SECURITY_TOP3_WEIGHT"
        else:
            reason = "RISK_CHAIN_TOP1_WEIGHT" if index == 217 else "MIN_SINGLE_WEIGHT"
        reasons = {reason: 2}
    else:
        reasons = {}
    before_audit = {
        "failure_session_count": 2 if before_failed else 0,
        "failure_reason_counts": {"MIN_SINGLE_WEIGHT": 2} if before_failed else {},
        "corrected_drawdown_with_initial_capital_peak": 0.10,
    }
    after_audit = {
        "failure_session_count": 2 if after_failed else 0,
        "failure_reason_counts": reasons,
        "corrected_drawdown_with_initial_capital_peak": 0.10 + dd_change,
    }
    return {
        "candidate_key": candidate_key,
        "candidate_identity_sha256": candidate_key + "a" * 40,
        "portfolio_id": f"portfolio-{track}-{index}",
        "holding_count": 4,
        "tickers": tickers,
        "weights": {ticker: 0.25 for ticker in tickers},
        "source_failure_class": (
            "SOURCE_REPORTED_ELIGIBLE"
            if not before_failed
            else "WHOLE_LOT_EXECUTABILITY_FAILED_ONLY"
        ),
        "source_coordinate": {
            "source_batch": "ndx_cardinality_real_runner_p2_exact_v3",
            "job_search_class": "EXACT_ENUMERATION",
            "evaluation_semantics_sha256": summary.runner.EVALUATOR_SHA256,
            "universe_track": track,
            "selection_date": "2024-06-03",
        },
        "stored_identity_weights_trace_and_13_summary_reproduced_before_a": True,
        "original_schedule_b": {
            "summary": {
                "whole_lot_path_return_net": 1.0,
                "whole_lot_total_transaction_cost_usd": 30.0,
                "whole_lot_terminal_value_usd": 50_000.0,
            },
            "daily_risk_audit": before_audit,
        },
        "continued_schedule_a": {
            "summary": {
                "whole_lot_path_return_net": 1.0 + return_change,
                "whole_lot_total_transaction_cost_usd": 45.0,
                "whole_lot_terminal_value_usd": 50_000.0 + return_change * 25_000.0,
            },
            "daily_risk_audit": after_audit,
            "added_rebalance_dates": ["2024-01-02"],
        },
        "ab_comparison": {
            "cumulative_path_return_change": return_change,
            "corrected_path_max_drawdown_change": dd_change,
            "transaction_cost_usd_change": 15.0,
            "a_nonworse_return_and_corrected_drawdown": nonworse,
            "ranking_score_computed": False,
        },
        "candidate_set_or_weight_search_run": False,
        "threshold_changed": False,
        "portfolio_cash_changed": False,
        "transaction_cost_changed": False,
        "fresh_oos_consumed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


def _fixture_results():
    rows = []
    layouts = {
        "strict_technology": [("PASS_TO_PASS", 82), ("FAIL_TO_PASS", 19), ("FAIL_TO_FAIL", 4)],
        "technology_plus_adjacent": [("PASS_TO_PASS", 131), ("FAIL_TO_PASS", 43), ("FAIL_TO_FAIL", 44)],
    }
    for track, layout in layouts.items():
        index = 0
        preference_index = layout[0][1]
        for transition, count in layout:
            for _ in range(count):
                rows.append(
                    _row(
                        track,
                        index,
                        transition,
                        preference=index == preference_index,
                    )
                )
                index += 1
    return {
        "schema_version": 1,
        "result_type": "ndx_equal_weight_schedule_extension_full_ab_report",
        "status": "COMPLETE",
        "cross_track_or_evaluator_ranking_performed": False,
        "candidate_set_or_weight_search_run": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
        "results": rows,
    }


class EqualWeightScheduleExtensionSummaryTest(unittest.TestCase):
    def test_full_fixture_reports_expected_counts_and_downside(self):
        result = summary.summarize_verified_results(
            _fixture_results(), source_evidence={"source_results_file_sha256": "a" * 64}
        )
        self.assertEqual(
            result["aggregate_audit"]["risk_status_transitions"],
            summary.EXPECTED_TRANSITIONS,
        )
        self.assertEqual(
            result["aggregate_audit"][
                "a_nonworse_return_and_corrected_drawdown_rows"
            ],
            133,
        )
        self.assertEqual(len(result["all_candidate_references"]), 323)
        self.assertEqual(len(result["user_preference_reference"]), 2)
        self.assertEqual(len(result["corrected_drawdown_degradation_examples"]), 1)
        self.assertFalse(result["aggregate_audit"]["blanket_win_claimed"])

    def test_track_loss_or_ranking_claim_is_rejected(self):
        payload = _fixture_results()
        payload["results"][0]["source_coordinate"][
            "universe_track"
        ] = "technology_plus_adjacent"
        with self.assertRaisesRegex(
            summary.NdxEqualWeightScheduleExtensionSummaryError,
            "track coverage changed",
        ):
            summary.summarize_verified_results(
                payload, source_evidence={"source_results_file_sha256": "a" * 64}
            )
        payload = _fixture_results()
        payload["cross_track_or_evaluator_ranking_performed"] = True
        with self.assertRaisesRegex(
            summary.NdxEqualWeightScheduleExtensionSummaryError,
            "full result contract changed",
        ):
            summary.summarize_verified_results(
                payload, source_evidence={"source_results_file_sha256": "a" * 64}
            )

    def test_markdown_is_honest_about_downside_and_user_reference(self):
        result = summary.summarize_verified_results(
            _fixture_results(), source_evidence={"source_results_file_sha256": "a" * 64}
        )
        report = summary.render_summary_markdown(result)
        self.assertIn("明确下行样本", report)
        self.assertIn("不代表整体胜出", report)
        self.assertIn("不是固定答案", report)
        self.assertIn("48 个延续后仍失败", report)

    def test_immutable_bundle_rebuild_rejects_resigned_summary(self):
        result = summary.summarize_verified_results(
            _fixture_results(), source_evidence={"source_results_file_sha256": "a" * 64}
        )
        with tempfile.TemporaryDirectory(dir=ROOT / "data/cache/research") as name:
            output = Path(name)
            relative = output.relative_to(ROOT)
            with patch.object(summary, "OUTPUT_RELATIVE", relative), patch.object(
                summary, "build_extension_summary", return_value=result
            ):
                summary.write_summary_bundle(result, output_dir=output)
                summary.verify_summary_bundle(
                    output / "manifest.json", repository_root=ROOT
                )
                changed = json.loads((output / "summary.json").read_text(encoding="utf-8"))
                changed["aggregate_audit"]["blanket_win_claimed"] = True
                changed_raw = summary._json_bytes(changed)
                (output / "summary.json").write_bytes(changed_raw)
                manifest = json.loads(
                    (output / "manifest.json").read_text(encoding="utf-8")
                )
                manifest["artifacts"]["summary_json"]["sha256"] = summary._sha256(
                    changed_raw
                )
                unsigned = dict(manifest)
                unsigned.pop("manifest_sha256")
                manifest["manifest_sha256"] = summary._canonical_sha256(unsigned)
                (output / "manifest.json").write_bytes(summary._json_bytes(manifest))
                with self.assertRaisesRegex(
                    summary.NdxEqualWeightScheduleExtensionSummaryError,
                    "does not rebuild",
                ):
                    summary.verify_summary_bundle(
                        output / "manifest.json", repository_root=ROOT
                    )

    def test_cli_help_runs(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts/ndx_equal_weight_schedule_extension_summary.py"),
                "--help",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--verify", completed.stdout)


if __name__ == "__main__":
    unittest.main()
