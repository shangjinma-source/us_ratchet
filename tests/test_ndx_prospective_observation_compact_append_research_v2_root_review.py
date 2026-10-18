"""Compare complete new-format append with the frozen independent arithmetic."""
import base64
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from backtest import ndx_prospective_observation_compact_append_research_v2 as producer
from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view
from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy
from backtest import ndx_capture_source_csv_independent_reconstruction_research_v1 as csv_reader
from scripts import ndx_registered_compact_history_independent_readback_20261009_v1 as independent
from test_ndx_prospective_observation_compact_append_research_v2 import fixture, next_actual


class IndependentWholeCompactFormulaReview(unittest.TestCase):
    def test_true_v5_and_following_v4_entire_results_equal_independent_formula(self):
        data, raw_arguments = fixture()
        for phase in ("true_v5", "following_v4"):
            with self.subTest(phase=phase):
                before = deepcopy(data)
                view = parent_view.inspect_parent_history_v5(data["parent"])
                payload = data["observation"]["payload"]
                blobs = {payload["tzif_reference"]["path"]: base64.b64decode(payload["tzif_bytes_base64"])}
                for ticker, parts in payload["full_original_sources_preserved"].items():
                    for part in parts.values(): blobs[part["reference"]["path"]] = base64.b64decode(part["original_csv_bytes_base64"])
                    if view["baseline_references"][ticker]["path"] not in blobs:
                        blobs[view["baseline_references"][ticker]["path"]] = raw_arguments["actual_baseline_bytes"][ticker]
                # Adapt the inspector API name only; the real envelope and parent schema are untouched.
                checker = SimpleNamespace(inspect_parent_history_v4=parent_view.inspect_parent_history_v5)
                with patch.object(producer, "append_observation_history", side_effect=AssertionError("Producer called by independent formula")), patch.object(legacy, "append_observation_history_v4", side_effect=AssertionError("Legacy producer called")):
                    expected = independent.reconstruct_history(parent=data["parent"], observation=data["observation"], parent_checker=checker, csv_rows=csv_reader.csv_rows, blobs=blobs)
                actual = producer.append_observation_history(**data)
                self.assertEqual(independent.encode(actual), independent.encode(expected))
                self.assertEqual(data, before)
                self.assertEqual(actual["parent_references"], {key: data["parent"][key] for key in producer.ROLES})
                self.assertEqual(actual["observations"][:-1], view["observations"])
                self.assertEqual(actual["gap_count"], view["gap_count"])
                if phase == "true_v5": data = next_actual(actual, data["observation"])


if __name__ == "__main__": unittest.main()
