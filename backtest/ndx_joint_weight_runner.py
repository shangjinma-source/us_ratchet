"""Research-only per-task restart checkpoints for explicit prepared inputs.

Checkpoints provide local integrity/reuse, not independent economic validation
or authenticity of caller-supplied source evidence. No live inputs are read.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile

import numpy as np
import pandas as pd
import scipy

from backtest.ndx_joint_weight_delta import SCHEMA_VERSION, COORDINATE_FIELDS
from backtest.ndx_joint_weight_evaluation import evaluate_joint_weight_task


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_ROOT = REPOSITORY_ROOT / "data/cache/research/ndx_joint_weight_runs_v1"
NUMERICAL_SOURCES = (
    "backtest/ndx_joint_weight_runner.py", "backtest/ndx_joint_weight_evaluation.py",
    "backtest/ndx_joint_weight_delta.py", "backtest/ndx_two_stage_joint_coverage.py",
    "backtest/ndx_cardinality_discovery.py", "backtest/ndx_whole_lot_rebalance.py",
    "backtest/weights.py",
)


def _normalize(value):
    if isinstance(value, np.generic):
        return _normalize(value.item())
    if isinstance(value, pd.Timestamp):
        return {"timestamp": value.isoformat()}
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("Nonfinite context/result")
        return {"float_hex": value.hex()}
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Context keys must be strings")
        return {"mapping": {key: _normalize(item) for key, item in value.items()}}
    if isinstance(value, (list, tuple)):
        return {"sequence_type": type(value).__name__, "items": [_normalize(item) for item in value]}
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("Unsupported context value: " + type(value).__name__)


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _panel_context(value):
    container_type = type(value).__name__
    series_name = value.name if isinstance(value, pd.Series) else None
    if isinstance(value, pd.Series):
        value = value.to_frame()
    if not isinstance(value, pd.DataFrame):
        return {"kind": "non_panel", "payload": _normalize(value)}
    return {"kind": "panel", "payload": _normalize({"container_type": container_type, "series_name": series_name,
                       "columns": value.columns.tolist(), "index": value.index.tolist(),
                       "index_names": list(value.index.names),
                       "index_dtype": str(value.index.dtype),
                       "dtypes": [str(dtype) for dtype in value.dtypes],
                       "column_values": [value.iloc[:, index].tolist() for index in range(len(value.columns))]})}


def _source_hashes():
    return {path: hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest()
            for path in NUMERICAL_SOURCES}


def _validate_task(task):
    fields = {"schema_version", *COORDINATE_FIELDS, "tickers", "weight_spec",
              "second_stage_selection_tags", "job_id"}
    if not isinstance(task, dict) or set(task) != fields or task["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Task is not a delta plan task")
    identity = {key: value for key, value in task.items()
                if key not in ("second_stage_selection_tags", "job_id")}
    if _sha(identity) != task["job_id"]:
        raise ValueError("Task identity changed")


@contextmanager
def _lock(path):
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _publish(path, payload):
    raw = _json_bytes(payload)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Existing artifact differs; refusing overwrite: " + str(path))
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def run_joint_weight_tasks(tasks, *, prepared_inputs, source_evidence, max_tasks=None):
    """Run up to max_tasks *new* evaluations; keep the full plan denominator.

    Failed computations leave earlier checkpoints intact and propagate. Retry
    with exactly the same inputs resumes them; changed capital/data/code creates
    a distinct context. A missing final summary never erases completed jobs.
    """
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Nonempty complete task plan required")
    if max_tasks is not None and (type(max_tasks) is not int or max_tasks <= 0):
        raise ValueError("max_tasks must be a positive integer")
    if not isinstance(source_evidence, dict) or not source_evidence:
        raise ValueError("Explicit source evidence required")
    tasks = copy.deepcopy(tasks)
    prepared_inputs = copy.deepcopy(prepared_inputs)
    source_evidence = copy.deepcopy(source_evidence)
    for task in tasks:
        _validate_task(task)
    if len({task["job_id"] for task in tasks}) != len(tasks):
        raise ValueError("Duplicate task identity")
    sources = _source_hashes()
    if sources != _LOADED_SOURCE_HASHES:
        raise ValueError("Numerical source files changed since import; restart process")
    context = {"schema": "ndx_joint_weight_checkpoint_v1", "tasks": tasks,
               "prepared_inputs": {key: _panel_context(value) for key, value in prepared_inputs.items()},
               "source_evidence": _normalize(source_evidence), "numerical_sources": sources,
               "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                           "pandas": pd.__version__, "scipy": scipy.__version__}}
    context_hash = _sha(context)
    destination = CHECKPOINT_ROOT / context_hash
    destination.mkdir(parents=True, exist_ok=True)
    attempted = resumed = completed = 0
    with _lock(destination / ".lock"):
        _publish(destination / "context.json", context)
        for task in tasks:
            path = destination / (task["job_id"] + ".json")
            if path.exists():
                raw = path.read_bytes()
                checkpoint = json.loads(raw)
                digest = checkpoint.pop("checkpoint_sha256", None)
                if (_json_bytes({**checkpoint, "checkpoint_sha256": digest}) != raw
                        or digest != _sha(checkpoint) or checkpoint.get("context_sha256") != context_hash
                        or checkpoint.get("task") != task or checkpoint.get("status") != "EVALUATED"
                        or set(checkpoint) != {"context_sha256", "task", "status", "result"}):
                    raise ValueError("Checkpoint integrity/context mismatch")
                resumed += 1
                completed += 1
                continue
            if max_tasks is not None and attempted >= max_tasks:
                continue
            attempted += 1
            result = evaluate_joint_weight_task(task, **prepared_inputs)
            if _source_hashes() != sources:
                raise ValueError("Numerical sources changed during evaluation")
            checkpoint = {"context_sha256": context_hash, "task": task, "status": "EVALUATED",
                          "result": _normalize(result)}
            checkpoint["checkpoint_sha256"] = _sha(checkpoint)
            _publish(path, checkpoint)
            completed += 1
        if _source_hashes() != sources:
            raise ValueError("Numerical sources changed during run")
    return {"context_sha256": context_hash, "output_dir": str(destination),
            "planned": len(tasks), "attempted": attempted, "resumed": resumed, "completed": completed,
            "status": "COMPLETE" if completed == len(tasks) else "PARTIAL",
            "promotion_allowed": False, "independent_economic_verification": False,
            "source_authenticity_verified_by_runner": False}


_LOADED_SOURCE_HASHES = _source_hashes()
