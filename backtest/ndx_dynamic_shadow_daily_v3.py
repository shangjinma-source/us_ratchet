"""Daily4 runtime provenance adapter, preserving the reviewed v2 math verifier.

All three repository-dependent checks omitted by v2's root-independent mode
are performed here with the new runtime paths. This is not task activation or
a substitute for the daily4 executor's fresh-search acceptance guards.
"""
from pathlib import Path
import json

from backtest import ndx_dynamic_shadow_daily_v2 as reviewed
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance


class NdxDynamicShadowDailyV3Error(reviewed.NdxDynamicShadowDailyV2Error):
    """The daily4 runtime provenance is incomplete or inconsistent."""


RUN_RELATIVE = Path("data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json")
RUNTIME_PATHS = {
    "daily_contract": Path("config/ndx_dynamic_shadow_daily_v1.yaml"),
    "daily_engine": Path("backtest/ndx_dynamic_shadow_daily_v3.py"),
    "daily_script": Path("scripts/ndx_dynamic_shadow_daily_v4.py"),
    "observed_calendar_manifest": reviewed.CALENDAR_RELATIVE,
}


def _verify_realized_acceptance(manifest, root):
    realized_root = root / RUN_RELATIVE.parent / "realized_decisions"
    registered = manifest["research_artifacts"]["realized_batch_manifests"]
    discovered = {
        directory.name for directory in realized_root.iterdir()
        if directory.is_dir() and not directory.name.startswith(".")
    } if realized_root.is_dir() else set()
    if set(registered) != discovered:
        raise NdxDynamicShadowDailyV3Error("daily4 realized batch inventory is incomplete")
    for decision, descriptor in registered.items():
        decision = acceptance.decision_date(decision)
        directory = root / RUN_RELATIVE.parent / "realized_decisions" / decision
        if Path(descriptor["path"]).resolve() != (directory / "batch_manifest.json").resolve():
            raise NdxDynamicShadowDailyV3Error("daily4 realized batch path changed")
        batch = reviewed.v1.verify_realized_decision_batch(directory)
        if batch["decision_date"] != decision:
            raise NdxDynamicShadowDailyV3Error("daily4 realized batch decision changed")
        receipt = acceptance.verify_acceptance(root / acceptance.ACCEPTANCE / decision / "receipt.json")
        expected_final = (root / acceptance.SEARCH / "final" / decision / "manifest.json").resolve()
        if Path(receipt["final_binding"]["path"]).resolve() != expected_final:
            raise NdxDynamicShadowDailyV3Error("daily4 acceptance final path changed")
        for filename in batch["artifacts"]:
            lane = json.loads((directory / filename).read_bytes())
            provenance = lane["provenance"]
            if (Path(provenance["candidate_manifest_path"]).resolve() != expected_final
                    or provenance["candidate_manifest_sha256"] != receipt["final_binding"]["sha256"]
                    or provenance["snapshot_manifest_sha256"] != receipt["input_binding"]["snapshot_sha256"]
                    or provenance["snapshot_fingerprint"] != receipt["input_binding"]["snapshot_fingerprint"]):
                raise NdxDynamicShadowDailyV3Error("daily4 realized lane acceptance binding changed")
        if reviewed.v1.verify_realized_decision_batch(directory) != batch:
            raise NdxDynamicShadowDailyV3Error("daily4 realized batch changed during verification")
        if acceptance.verify_acceptance(root / acceptance.ACCEPTANCE / decision / "receipt.json") != receipt:
            raise NdxDynamicShadowDailyV3Error("daily4 acceptance changed during verification")


def verify_daily_run_manifest(path, *, repository_root):
    root = Path(repository_root).resolve()
    manifest_path = Path(path).resolve()
    if manifest_path != (root / RUN_RELATIVE).resolve():
        raise NdxDynamicShadowDailyV3Error("daily4 run manifest path is not canonical")
    raw = manifest_path.read_bytes()
    manifest = reviewed.verify_daily_run_manifest(manifest_path, repository_root=None)
    # v2 checks schema, artifact/ledger integrity, alignment, and boundaries.
    # Economic reconstruction is separate; hashes alone do not prove the path.
    artifacts = manifest["research_artifacts"]
    for name, relative in RUNTIME_PATHS.items():
        actual = Path(artifacts[name]["path"]).resolve()
        if actual != (root / relative).resolve():
            raise NdxDynamicShadowDailyV3Error(f"daily4 runtime provenance changed: {name}")
    calendar_path = root / reviewed.CALENDAR_RELATIVE
    _, _, projection = reviewed.load_reviewed_calendar_projection(calendar_path, repository_root=root)
    if projection.empty or projection.iloc[-1]["session_date"].date().isoformat() != manifest["latest_observed_session"]:
        raise NdxDynamicShadowDailyV3Error("daily4 latest observed session changed")
    _verify_realized_acceptance(manifest, root)
    if manifest["independent_lane_count"] or manifest["realized_decision_batches"]:
        from backtest.ndx_dynamic_shadow_daily_economic_replay import verify_daily_economic_replay
        verify_daily_economic_replay(manifest, repository_root=root)
    # Check the bytes again after the calendar proof and repeat all bound artifact
    # checks, so a source change during the cross-check is not silently accepted.
    repeated = reviewed.verify_daily_run_manifest(manifest_path, repository_root=None)
    if repeated != manifest or manifest_path.read_bytes() != raw or json.loads(raw) != manifest:
        raise NdxDynamicShadowDailyV3Error("daily4 manifest changed during verification")
    return manifest
