"""Independent fail-closed checks for the historical capital replay summary."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from backtest.ndx_cardinality_capital_replay_summary import (
    NdxCardinalityCapitalReplaySummaryError,
)
from test_ndx_cardinality_capital_replay_summary import (
    ReplayFixture,
    _sha,
    _write_csv,
    _write_json,
)


class CapitalReplaySummaryAdversarialTests(unittest.TestCase):
    def _mutated_summary(
        self,
        root: Path,
        *,
        candidate_updates: dict[str, str] | None = None,
        manifest_updates: dict[str, object] | None = None,
    ) -> dict[str, object]:
        fixture = ReplayFixture(root)
        # Prove the unmodified fixture is admissible before attributing a later
        # rejection to the adversarial mutation under test.
        fixture.build_summary()
        manifest_path = fixture.child_manifests[0]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        candidate_path = Path(manifest["artifacts"]["candidates"]["path"])
        with candidate_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        fields = list(rows[0])
        rows[0].update(candidate_updates or {})
        manifest.update(manifest_updates or {})
        _write_csv(candidate_path, rows, fields)
        manifest["artifacts"]["candidates"]["sha256"] = _sha(candidate_path)
        manifest["artifacts"]["candidates"]["rows"] = len(rows)
        _write_json(manifest_path, manifest)
        return fixture.build_summary()

    def test_impossible_execution_accounting_cannot_be_source_reported_eligible(self) -> None:
        attacks = (
            {"whole_lot_min_cash_usd": "-500"},
            {"whole_lot_rebalance_count": "1.5"},
            {"whole_lot_share_change_count": "2.5"},
            {"whole_lot_total_trade_notional_usd": "-1"},
            {"whole_lot_total_transaction_cost_usd": "-12"},
            {"whole_lot_terminal_value_usd": "-1"},
            {"whole_lot_path_max_drawdown": "-0.1"},
            {"whole_lot_path_max_drawdown": "1.1"},
            {"whole_lot_path_return_net": "-1.1"},
        )
        for updates in attacks:
            with self.subTest(updates=updates), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(NdxCardinalityCapitalReplaySummaryError):
                    self._mutated_summary(Path(temporary), candidate_updates=updates)

    def test_fee_model_and_trace_digest_are_not_caller_assertions(self) -> None:
        for updates in (
            {"whole_lot_total_transaction_cost_usd": "999"},
            {"whole_lot_rebalance_trace_sha256": "z" * 64},
        ):
            with self.subTest(updates=updates), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(NdxCardinalityCapitalReplaySummaryError):
                    self._mutated_summary(Path(temporary), candidate_updates=updates)

    def test_declared_aggregate_gate_cannot_override_failed_component(self) -> None:
        component_fields = (
            "declared_max_single_passed",
            "declared_security_top3_weight_passed",
            "declared_risk_chain_top1_weight_passed",
            "declared_effective_n_passed",
        )
        for field in component_fields:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(NdxCardinalityCapitalReplaySummaryError):
                    self._mutated_summary(
                        Path(temporary),
                        candidate_updates={field: "False", "declared_constraints_passed": "True"},
                    )

    def test_all_zero_whole_lot_path_cannot_be_reported_executable(self) -> None:
        zero_shares = "AMAT:0;AVGO:0;CDNS:0;GOOG:0"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(NdxCardinalityCapitalReplaySummaryError):
                self._mutated_summary(
                    Path(temporary),
                    candidate_updates={
                        "whole_lot_initial_shares": zero_shares,
                        "whole_lot_terminal_shares": zero_shares,
                    },
                )

    def test_fit_flags_cannot_mask_future_training_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(NdxCardinalityCapitalReplaySummaryError):
                self._mutated_summary(
                    Path(temporary),
                    manifest_updates={"training_end": "2025-12-29"},
                    candidate_updates={
                        "decision_data_end": "2025-12-29",
                        "last_fit_evaluation_boundary": "2025-12-29",
                        "fit_strictly_before_evaluation": "True",
                    },
                )


if __name__ == "__main__":
    unittest.main()
