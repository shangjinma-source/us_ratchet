"""Candidate-v3/fresh-v4 daily adapter; activation5 is mandatory.

This preserves the existing research controller's output namespace and math.
It neither installs tasks nor activates a replacement runtime implicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ndx_dynamic_shadow_daily_v3 as previous
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance
from backtest import ndx_dynamic_shadow_daily_v3 as reviewed
from backtest.ndx_dynamic_shadow_daily import NdxDynamicShadowDailyError
from data.versioning import file_sha256

engine = previous.engine
ACTIVATION = ROOT / "data/cache/research/ndx_dynamic_shadow_activation_v5/manifest.json"
GENERATOR_SCRIPT = ROOT / "scripts/ndx_dynamic_shadow_candidate_generator_v3.py"
FRESH_SCRIPT = ROOT / "scripts/ndx_dynamic_shadow_fresh_search_v4.py"


class _RoundTripPriceCsv:
    """Module-local pandas view; preserve exact stored floats on price replay.

    Do not mutate pandas globally or relax the frozen source/combined byte check.
    This view exists only while the borrowed nominal-price function is running.
    """
    def __init__(self, pandas_module):
        self._pandas = pandas_module

    def __getattr__(self, name):
        return getattr(self._pandas, name)

    def read_csv(self, *args, **kwargs):
        kwargs.setdefault("float_precision", "round_trip")
        return self._pandas.read_csv(*args, **kwargs)


def _verify_activation(*, static_only):
    # Deliberately no fallback: a missing module/manifest blocks before refresh.
    from backtest.ndx_dynamic_shadow_activation_v5 import (
        verify_activation_v5_manifest, verify_activation_v5_static_sources,
    )
    verifier = verify_activation_v5_static_sources if static_only else verify_activation_v5_manifest
    return verifier(ACTIVATION, repository_root=ROOT)


def _generator_command(decision_date):
    command = previous._generator_command(decision_date)
    command[2] = str(GENERATOR_SCRIPT)
    return command


def _fresh_command(decision_date, *, max_jobs=0):
    del max_jobs
    return [sys.executable, "-B", str(FRESH_SCRIPT), "--execute",
            "--snapshot-manifest", str(engine.INPUT_ROOT / decision_date / "manifest.json")]


def _verify_input_seal(decision_date):
    previous._run_checked([sys.executable, "-B", str(GENERATOR_SCRIPT), "--verify",
                           str(engine.INPUT_ROOT / decision_date / "manifest.json")])


def verify_accepted_final(path):
    """Return verified receipt only for this exact canonical final artifact."""
    final_path = Path(path).resolve()
    decision = acceptance.decision_date(final_path.parent.name)
    expected = (ROOT / acceptance.SEARCH / "final" / decision / "manifest.json").resolve()
    if final_path != expected:
        raise NdxDynamicShadowDailyError("daily4 final path is not canonical")
    receipt = acceptance.verify_acceptance(ROOT / acceptance.ACCEPTANCE / decision / "receipt.json")
    if (receipt["decision_date"] != decision
            or Path(receipt["final_binding"]["path"]).resolve() != final_path
            or receipt["final_binding"]["sha256"] != file_sha256(final_path)):
        raise NdxDynamicShadowDailyError("daily4 final acceptance binding changed")
    return receipt


def verified_realized_batch_count():
    """Return cumulative verified batches, matching the cumulative run inventory."""
    realized_root = ROOT / reviewed.RUN_RELATIVE.parent / "realized_decisions"
    registered = {}
    if realized_root.is_dir():
        for directory in sorted(realized_root.iterdir()):
            if directory.is_dir() and not directory.name.startswith("."):
                path = directory / "batch_manifest.json"
                registered[directory.name] = {"path": path.as_posix(), "sha256": file_sha256(path)}
    reviewed._verify_realized_acceptance(
        {"research_artifacts": {"realized_batch_manifests": registered}}, ROOT,
    )
    return len(registered)


def _adapter_bindings():
    bindings = previous._adapter_bindings()
    old_inventory = bindings["_daily_artifact_inventory"]
    old_final = engine.verify_final_candidate_snapshot
    old_role = engine.verify_final_role_seal_record
    old_builder = engine.build_realized_lane_decisions
    old_realize = engine._realize_ready_decisions
    old_nominal = engine._nominal_price_evidence

    def nominal(*args, **kwargs):
        with previous.scoped_engine_bindings({"pd": _RoundTripPriceCsv(engine.pd)}):
            return old_nominal(*args, **kwargs)

    def guarded(call):
        def invoke(path, *args, **kwargs):
            before = verify_accepted_final(path)
            result = call(path, *args, **kwargs)
            if verify_accepted_final(path) != before:
                raise NdxDynamicShadowDailyError("daily4 acceptance changed during final consumption")
            return result
        return invoke

    def realize(sessions):
        # Validate old batches even if the frozen engine skips completed decisions.
        verified_realized_batch_count()
        old_realize(sessions)
        return verified_realized_batch_count()

    def inventory(path_update):
        result = old_inventory(path_update)
        for key, path in (
            ("daily_script", Path(__file__).resolve()),
            ("daily_engine", ROOT / "backtest/ndx_dynamic_shadow_daily_v3.py"),
        ):
            result[key] = {"path": path.as_posix(), "sha256": file_sha256(path)}
        return result

    bindings.update({
        "_verify_activation_before_execute": lambda: _verify_activation(static_only=False),
        "candidate_generator_command": _generator_command,
        "fresh_search_command": _fresh_command,
        "_verify_input_seal": _verify_input_seal,
        "verify_final_candidate_snapshot": guarded(old_final),
        "verify_final_role_seal_record": guarded(old_role),
        "build_realized_lane_decisions": guarded(old_builder),
        "_realize_ready_decisions": realize,
        "_nominal_price_evidence": nominal,
        "_daily_artifact_inventory": inventory,
        "verify_daily_run_manifest": reviewed.verify_daily_run_manifest,
    })
    return bindings


def execute():
    with engine.single_instance_lock():
        before = engine._protected_hashes()
        try:
            _verify_activation(static_only=True)
            previous._refresh_calendar()
            _verify_activation(static_only=False)
            with previous.scoped_engine_bindings(_adapter_bindings()):
                return engine.execute(max_search_jobs=0)
        finally:
            if engine._protected_hashes() != before:
                raise NdxDynamicShadowDailyError("protected live files changed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("--execute is required")
    try:
        result = execute()
    except previous.ResearchStageFailure as exc:
        print(f"daily4 research stage stopped: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        print(f"daily4 fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
