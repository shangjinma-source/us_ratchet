"""Pure, research-only task planning for newly covered security sets.

The supplied child hash is an identity commitment, not proof of provenance.
This module neither reads manifests nor trains or authorizes any portfolio.
"""
import hashlib
import json
import re

import pandas as pd

from backtest.ndx_two_stage_joint_coverage import select_joint_coverage_security_sets


SCHEMA_VERSION = "ndx_joint_weight_delta_v1"
COORDINATE_FIELDS = (
    "source_batch", "universe_track", "selection_date", "holding_count",
    "decision_data_end", "child_manifest_sha256",
)
SUPPORTED_WEIGHT_SPECS = (
    "constrained_fixed_shrinkage",
    "constrained_fixed_shrinkage_turnover_anchor",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def build_joint_weight_delta_plan(equal_weight_results, *, coordinate,
                                 second_stage_weight_specs,
                                 per_frontier_limit=16, pareto_block_size=256):
    """Expand real selector output into deterministic delta-set/spec jobs.

    All supplied equal-weight rows must belong to one explicit coordinate.
    Legacy selected sets are excluded regardless of their historical success:
    retrying failed legacy evaluations is a separate workflow.
    """
    _require(isinstance(coordinate, dict) and set(coordinate) == set(COORDINATE_FIELDS),
             "Coordinate must contain exactly the required identity fields")
    identity = dict(coordinate)
    for field in COORDINATE_FIELDS:
        value = identity[field]
        if field == "holding_count":
            _require(isinstance(value, int) and not isinstance(value, bool) and value > 0,
                     "holding_count must be a positive integer")
        else:
            _require(isinstance(value, str) and bool(value) and value == value.strip(),
                     f"Invalid coordinate field: {field}")
    _require(re.fullmatch(r"[0-9a-f]{64}", identity["child_manifest_sha256"]) is not None,
             "Child manifest hash must be canonical lowercase SHA256")
    _require(isinstance(second_stage_weight_specs, (list, tuple))
             and bool(second_stage_weight_specs), "Weight specs must be a nonempty list or tuple")
    _require(all(isinstance(spec, str) and spec in SUPPORTED_WEIGHT_SPECS
                 for spec in second_stage_weight_specs), "Unsupported weight spec")
    _require(len(set(second_stage_weight_specs)) == len(second_stage_weight_specs),
             "Duplicate weight specs")
    specs = sorted(second_stage_weight_specs)
    _require(isinstance(equal_weight_results, pd.DataFrame), "Expected equal-weight DataFrame")
    _require(not equal_weight_results.columns.duplicated().any(), "Duplicate columns")
    for field in COORDINATE_FIELDS:
        if field in equal_weight_results and field != "holding_count":
            _require(equal_weight_results[field].eq(identity[field]).fillna(False).all(),
                     f"Input coordinate mismatch: {field}")
    coverage = select_joint_coverage_security_sets(
        equal_weight_results, selection_date=identity["selection_date"],
        decision_data_end=identity["decision_data_end"],
        per_frontier_limit=per_frontier_limit, pareto_block_size=pareto_block_size)
    _require(coverage["audit"]["holding_count"] == identity["holding_count"],
             "Input holding_count differs from coordinate")
    legacy = set(coverage["legacy_control"].tickers)
    tasks = []
    for row in coverage["selected"].sort_values("tickers").itertuples(index=False):
        if row.tickers in legacy:
            continue
        for spec in specs:
            job_identity = dict(schema_version=SCHEMA_VERSION, **identity,
                                tickers=row.tickers, weight_spec=spec)
            encoded = json.dumps(job_identity, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
            tasks.append(dict(job_identity,
                              second_stage_selection_tags=row.second_stage_selection_tags,
                              job_id=hashlib.sha256(encoded).hexdigest()))
    audit = dict(coverage["audit"], schema_version=SCHEMA_VERSION,
                 coordinate=identity, second_stage_weight_specs=specs,
                 planned_task_count=len(tasks), legacy_evaluations_retried=False,
                 training_performed=False, source_authenticity_verified=False,
                 evaluation_context_bound=False, checkpoint_reuse_authorized=False,
                 job_id_scope="DECLARED_COORDINATE_SECURITY_SET_WEIGHT_SPEC_ONLY")
    return dict(tasks=tasks, audit=audit)
