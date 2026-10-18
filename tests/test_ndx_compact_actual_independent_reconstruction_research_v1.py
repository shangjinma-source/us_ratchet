"""Independent compact reconstruction: full equality, raw identity and no producer IO."""
import ast
import base64
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_compact_actual_independent_reconstruction_research_v1 as module
from backtest import ndx_prospective_observation_compact_append_research_v2 as producer
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_capture_source_csv_independent_reconstruction_research_v1 as csv_reader
from scripts import ndx_registered_compact_history_independent_readback_20261009_v1 as independent
from test_ndx_prospective_observation_compact_append_research_v2 import fixture, next_actual


def arguments(data=None, actual_bytes=None):
    if data is None:
        data, original = fixture()
        actual_bytes = original["actual_baseline_bytes"]
    parent = view.inspect_parent_history_v5(data["parent"])
    payload = data["observation"]["payload"]
    blobs = {payload["tzif_reference"]["path"]: base64.b64decode(payload["tzif_bytes_base64"])}
    for ticker, parts in payload["full_original_sources_preserved"].items():
        for part in parts.values(): blobs[part["reference"]["path"]] = base64.b64decode(part["original_csv_bytes_base64"])
        if parent["baseline_references"][ticker]["path"] not in blobs:
            blobs[parent["baseline_references"][ticker]["path"]] = actual_bytes[ticker]
    return dict(**data, blobs=blobs, parent_checker=view, csv_rows=csv_reader.csv_rows, independent_formula=independent)


class IndependentCompactReconstructionTests(unittest.TestCase):
    def test_complete_true_v5_then_v4_results_match_without_producer_or_io(self):
        data, original = fixture()
        for phase in ("v5", "v4"):
            with self.subTest(phase=phase):
                expected = producer.append_observation_history(**deepcopy(data))
                args = arguments(data, original["actual_baseline_bytes"])
                before = deepcopy(data)
                with patch.object(Path, "read_bytes", side_effect=AssertionError("Pure IO")), patch.object(producer, "append_observation_history", side_effect=AssertionError("Producer executed")):
                    actual = module.reconstruct_compact_actual(**args)
                self.assertEqual(module.encode(actual), module.encode(expected))
                self.assertEqual(data, before)
                if phase == "v5": data = next_actual(actual, data["observation"])

    def test_selected_price_row_location_adapter_and_clock_are_independently_checked(self):
        args = arguments()
        for attack in ("price", "index", "index_bool", "adapter", "parent_schema", "clock"):
            with self.subTest(attack=attack):
                observation = deepcopy(args["observation"])
                payload = observation["payload"]
                if attack == "price": payload["selected_original_rows"]["QQQ"]["Close"] = "999999"
                elif attack == "index": payload["source_row_locations"]["QQQ"]["original_data_row_index"] += 1
                elif attack == "index_bool": payload["source_row_locations"]["QQQ"]["original_data_row_index"] = True
                elif attack == "adapter": observation["audit"]["writer_adapter_schema"] = "REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V4"
                elif attack == "parent_schema": observation["receipt"]["actual_parent_schema"] = "PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4"
                else: payload["capture_started_at_utc"] = "2026-10-12T19:00:00+00:00"
                with patch.object(independent, "reconstruct_history", side_effect=AssertionError("Should fail before shared independent formula")):
                    with self.assertRaises(ValueError): module.reconstruct_compact_actual(**dict(args, observation=observation))

    def test_no_project_imports_and_declared_formula_dependency_is_independent(self):
        source = Path(module.__file__).read_text(encoding="utf-8")
        imports = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import): imports.extend(item.name for item in node.names)
            if isinstance(node, ast.ImportFrom): imports.append(node.module or "")
        self.assertFalse(any(name.startswith(("backtest", "scripts")) for name in imports))
        self.assertEqual(module.DEPENDENCY_SHA256["independent_formula"], "6a17d3ad5758ff72feeaa653088b3b94819d5096b5ec005690351a6981917e0f")


if __name__ == "__main__": unittest.main()
