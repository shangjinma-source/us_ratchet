import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_joint_weight_runner as runner
from backtest.ndx_joint_weight_delta import SCHEMA_VERSION
from test_ndx_joint_weight_evaluation import fixture


def prepared():
    base, inputs = fixture()
    tasks = []
    for spec in ("constrained_fixed_shrinkage", "constrained_fixed_shrinkage_turnover_anchor"):
        identity = dict(base, schema_version=SCHEMA_VERSION, weight_spec=spec,
                        source_batch="SYNTHETIC", universe_track="strict_technology",
                        child_manifest_sha256="a" * 64)
        tasks.append(dict(identity, job_id=runner._sha(identity), second_stage_selection_tags="TEST"))
    return tasks, inputs


class JointWeightRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root_patch = patch.object(runner, "CHECKPOINT_ROOT", Path(self.temporary.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def run_tasks(self, tasks, inputs, **kwargs):
        return runner.run_joint_weight_tasks(tasks, prepared_inputs=inputs,
                                             source_evidence={"kind": "SYNTHETIC_TEST"}, **kwargs)

    def test_actual_budgeted_run_resume_keeps_denominator_and_does_not_recompute(self):
        tasks, inputs = prepared()
        first = self.run_tasks(tasks, inputs, max_tasks=1)
        self.assertEqual((first["planned"], first["completed"], first["attempted"]), (2, 1, 1))
        self.assertEqual(first["status"], "PARTIAL")
        second = self.run_tasks(tasks, inputs, max_tasks=1)
        self.assertEqual((second["completed"], second["attempted"], second["resumed"]), (2, 1, 1))
        with patch.object(runner, "evaluate_joint_weight_task", side_effect=AssertionError("Must resume")):
            third = self.run_tasks(tasks, inputs)
        self.assertEqual((third["completed"], third["attempted"], third["resumed"]), (2, 0, 2))
        self.assertFalse(third["promotion_allowed"])

    def test_same_task_different_cash_data_or_incumbent_does_not_reuse(self):
        tasks, inputs = prepared()
        first = self.run_tasks(tasks[:1], inputs)
        for kind in ("cash", "returns", "incumbent"):
            changed = copy.deepcopy(inputs)
            if kind == "cash":
                changed["contract"]["portfolio_cash_usd"] = 25000.
            elif kind == "returns":
                changed["returns"].iloc[0, 0] += 1e-15
            else:
                changed["incumbent_weights"] = {"ALFA": .4, "BETA": .3, "GAMM": .3}
            result = self.run_tasks(tasks[:1], changed)
            self.assertNotEqual(result["context_sha256"], first["context_sha256"])
            self.assertEqual(result["attempted"], 1)

    def test_exception_leaves_previous_job_resumable(self):
        tasks, inputs = prepared()
        actual = runner.evaluate_joint_weight_task
        count = 0
        def interrupted(task, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("Interrupted computation")
            return actual(task, **kwargs)
        with patch.object(runner, "evaluate_joint_weight_task", side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                self.run_tasks(tasks, inputs)
        result = self.run_tasks(tasks, inputs)
        self.assertEqual((result["completed"], result["resumed"], result["attempted"]), (2, 1, 1))

    def test_corrupted_checkpoint_and_task_identity_rejected_without_repair(self):
        tasks, inputs = prepared()
        first = self.run_tasks(tasks[:1], inputs)
        path = Path(first["output_dir"]) / (tasks[0]["job_id"] + ".json")
        original = path.read_bytes()
        path.write_bytes(original[:-7])
        with self.assertRaises(ValueError):
            self.run_tasks(tasks[:1], inputs)
        self.assertEqual(path.read_bytes(), original[:-7])
        tasks[0]["weight_spec"] = "equal_weight"
        with self.assertRaisesRegex(ValueError, "identity"):
            self.run_tasks(tasks[:1], inputs)

    def test_code_drift_after_import_is_rejected(self):
        tasks, inputs = prepared()
        hashes = runner._source_hashes()
        hashes["backtest/weights.py"] = "b" * 64
        with patch.object(runner, "_source_hashes", return_value=hashes):
            with self.assertRaisesRegex(ValueError, "since import"):
                self.run_tasks(tasks, inputs)

    def test_container_type_changes_cannot_collide_with_completed_context(self):
        tasks, inputs = prepared()
        self.run_tasks(tasks[:1], inputs)
        for kind in ("series_to_frame", "dict_for_float", "dict_for_panel"):
            changed = copy.deepcopy(inputs)
            if kind == "series_to_frame":
                changed["target_returns"] = changed["target_returns"].to_frame()
            elif kind == "dict_for_float":
                changed["contract"]["portfolio_cash_usd"] = {"float_hex": float(inputs["contract"]["portfolio_cash_usd"]).hex()}
            else:
                value = changed["returns"]
                changed["returns"] = dict(container_type=type(value).__name__, series_name=None,
                    columns=value.columns.tolist(), index=value.index.tolist(),
                    index_names=list(value.index.names), index_dtype=str(value.index.dtype),
                    dtypes=[str(dtype) for dtype in value.dtypes],
                    column_values=[value.iloc[:, index].tolist() for index in range(len(value.columns))])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.run_tasks(tasks[:1], changed)


if __name__ == "__main__":
    unittest.main()
