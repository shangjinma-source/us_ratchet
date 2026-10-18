"""Read-only economic re-evaluation of captured joint-weight checkpoints.

This verifies outputs against the captured context, not external authenticity
or independent market data. It does not run the candidate selection again.
"""
import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest import ndx_joint_weight_runner as runner
from backtest.ndx_joint_weight_evaluation import evaluate_joint_weight_task


def _restore(value):
    if isinstance(value, dict):
        if set(value) == {"mapping"}:
            return {key: _restore(item) for key, item in value["mapping"].items()}
        if set(value) == {"float_hex"}:
            return float.fromhex(value["float_hex"])
        if set(value) == {"timestamp"}:
            return pd.Timestamp(value["timestamp"])
        if set(value) == {"sequence_type", "items"}:
            items = [_restore(item) for item in value["items"]]
            if value["sequence_type"] == "list":
                return items
            if value["sequence_type"] == "tuple":
                return tuple(items)
        raise ValueError("Unknown captured value encoding")
    if value is None or type(value) in (str, bool, int):
        return value
    raise ValueError("Unexpected unencoded context value")


def _restore_input(captured):
    if not isinstance(captured, dict) or set(captured) != {"kind", "payload"}:
        raise ValueError("Invalid input container encoding")
    value = _restore(captured["payload"])
    if captured["kind"] == "non_panel":
        result = value
    elif captured["kind"] == "panel":
        index = pd.Index(value["index"], dtype=value["index_dtype"])
        index.names = value["index_names"]
        columns = value["columns"]
        if len(columns) != len(set(columns)):
            raise ValueError("Duplicate captured columns")
        result = pd.DataFrame({column: pd.Series(values, index=index, dtype=dtype)
                               for column, values, dtype in zip(columns, value["column_values"], value["dtypes"])},
                              index=index, columns=columns)
        if value["container_type"] == "Series":
            if len(columns) != 1:
                raise ValueError("Captured Series must have one column")
            result = result.iloc[:, 0].rename(value["series_name"])
        elif value["container_type"] != "DataFrame":
            raise ValueError("Unsupported captured panel class")
    else:
        raise ValueError("Unknown captured input kind")
    if runner._json_bytes(runner._panel_context(result)) != runner._json_bytes(captured):
        raise ValueError("Captured input does not round-trip exactly")
    return result


def verify_context(directory, *, expected_context_sha256):
    directory = Path(directory)
    captured_bytes = {}
    def read(path):
        raw = path.read_bytes()
        value = json.loads(raw)
        if runner._json_bytes(value) != raw:
            raise ValueError("Noncanonical checkpoint/context JSON")
        captured_bytes[path] = raw
        return value
    context = read(directory / "context.json")
    if runner._sha(context) != expected_context_sha256 or directory.name != expected_context_sha256:
        raise ValueError("Expected context identity mismatch")
    if context.get("schema") != "ndx_joint_weight_checkpoint_v1":
        raise ValueError("Unsupported checkpoint schema")
    sources = runner._source_hashes()
    if sources != context["numerical_sources"] or sources != runner._LOADED_SOURCE_HASHES:
        raise ValueError("Captured numerical sources differ from current evaluator")
    inputs = {key: _restore_input(value) for key, value in context["prepared_inputs"].items()}
    tasks = context["tasks"]
    if not tasks or len({task['job_id'] for task in tasks}) != len(tasks):
        raise ValueError("Missing or duplicated captured tasks")
    expected_files = {"context.json"} | {task["job_id"] + ".json" for task in tasks}
    if {path.name for path in directory.glob('*.json')} != expected_files:
        raise ValueError("Incomplete or extra checkpoint set")
    declared_passed = joint_noninferior = 0
    return_fields = ["return_p50_vs_012922", "return_p10_vs_012922",
                     "paired_return_p50_vs_incumbent", "paired_return_p10_vs_incumbent"]
    drawdown_fields = ["max_drawdown_p50_vs_012922", "max_drawdown_p90_vs_012922",
                       "paired_drawdown_cost_p50_vs_incumbent", "paired_drawdown_cost_p90_vs_incumbent"]
    for task in tasks:
        runner._validate_task(task)
        checkpoint = read(directory / (task["job_id"] + ".json"))
        digest = checkpoint.pop("checkpoint_sha256", None)
        if (digest != runner._sha(checkpoint) or checkpoint.get("context_sha256") != expected_context_sha256
                or runner._json_bytes(checkpoint.get("task")) != runner._json_bytes(task)
                or checkpoint.get("status") != "EVALUATED"
                or set(checkpoint) != {"context_sha256", "task", "status", "result"}):
            raise ValueError("Checkpoint binding/integrity mismatch")
        calculated = evaluate_joint_weight_task(task, **inputs)
        if runner._json_bytes(runner._normalize(calculated)) != runner._json_bytes(checkpoint["result"]):
            raise ValueError("Economic checkpoint result does not recompute: " + task["job_id"])
        declared_passed += bool(calculated["declared_constraints_passed"])
        joint_noninferior += (all(calculated[field] >= 0 for field in return_fields)
                             and all(calculated[field] <= 0 for field in drawdown_fields))
    if runner._source_hashes() != sources:
        raise ValueError("Numerical source changed during verification")
    for path, raw in captured_bytes.items():
        if path.read_bytes() != raw:
            raise ValueError("Captured artifact changed during verification")
    if {path.name for path in directory.glob('*.json')} != expected_files:
        raise ValueError("Checkpoint set changed during verification")
    return dict(status="ECONOMIC_RECOMPUTATION_MATCHED_CAPTURED_CONTEXT", context_sha256=expected_context_sha256,
                checked=len(tasks), declared_constraints_passed=declared_passed,
                joint_eight_component_noninferior=joint_noninferior,
                source_authenticity_verified=False, independent_economic_algorithm=False,
                historical_source_equivalence_proven=False, promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--expected-context-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(verify_context(args.directory, expected_context_sha256=args.expected_context_sha256)))
