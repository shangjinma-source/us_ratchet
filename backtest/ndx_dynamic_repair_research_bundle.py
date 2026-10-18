"""Frozen fourteen-lane execution diagnostic, not a portfolio search or admission.

Capture checks upstream selection provenance once. Historical verification
replays archived execution inputs, not the complete training/PIT source world.
No production files, scheduler configuration, or trading advice are written.
"""
from __future__ import annotations

import base64
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile

import pandas as pd

from scripts import ndx_dynamic_walkforward as source
from backtest.ndx_dynamic_whole_lot_path import simulate_dynamic_security_id_whole_lot_path
from backtest.ndx_dynamic_whole_lot_repair_path import simulate_dynamic_security_id_conditional_repair_path
from backtest.ndx_equal_weight_schedule_extension_runner import _single_instance_lock

SOURCE_RELATIVE = Path("data/cache/research/ndx_dynamic_walkforward_v1")
OUTPUT_RELATIVE = Path("data/cache/research/dynrepair_v1")
SOURCE_MANIFEST_SHA256 = "b1b86ad649f141c680046b4064973c20064de9e720ec4a37716eb4f2d7716f6c"
SOURCE_INDEX_SHA256 = "1111ecf65b5d824c2844e857cac41e04b17ce48f23d553f8203e5d9afdb4d603"
CODE_FILES = (
    "backtest/ndx_dynamic_repair_research_bundle.py",
    "scripts/ndx_dynamic_repair_research_bundle.py",
    "backtest/ndx_dynamic_whole_lot_path.py",
    "backtest/ndx_dynamic_whole_lot_repair_path.py",
    "backtest/ndx_whole_lot_repair_diagnostic.py",
    "backtest/ndx_dynamic_candidate_policy.py",
    "scripts/ndx_dynamic_walkforward.py",
    "backtest/ndx_equal_weight_schedule_extension_runner.py",
)
COORDINATES = ("source_batch", "universe_track", "policy_role")
FRAMES = ("rebalances", "trades", "path", "daily_risk", "repair_events")
VERSION = "DYNAMIC_REPAIR_EXECUTION_DIAGNOSTIC_V1"
CAPTURE_FIELDS = {"version", "code_hashes", "tickers", "sources", "candidate_loader_consumed_hashes",
                  "selected_provenance_counts", "upstream_provenance_checked_at_capture_only"}
MANIFEST_FIELDS = {"version", "fingerprint", "capture_sha256", "results_sha256", "coverage",
                   "research_only", "promotion_allowed", "verification_scope"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":"), default=lambda item: item.item()) + "\n").encode()


def csv(raw):
    return pd.read_csv(io.BytesIO(raw), low_memory=False)


def frame_text(frame):
    return frame.to_csv(index=False, lineterminator="\n")


def lane_key(row):
    return "/".join(str(row[name]) for name in COORDINATES)


def code_hashes(root):
    return {name: sha((root / name).read_bytes()) for name in CODE_FILES}


class CapturedSources:
    def __init__(self, entries=None):
        self.entries = {} if entries is None else dict(entries)
        self.read_only = entries is not None

    def read(self, path, expected=None):
        key = Path(path).as_posix()
        if key not in self.entries:
            require(not self.read_only, f"Missing archived source: {key}")
            self.entries[key] = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        raw = base64.b64decode(self.entries[key], validate=True)
        require(expected is None or sha(raw) == expected, f"Source binding changed: {key}")
        return raw

    def document(self, descriptor):
        return json.loads(self.read(descriptor["path"], descriptor["sha256"]))


def source_contract(root, archive):
    manifest = json.loads(archive.read(root / SOURCE_RELATIVE / "manifest.json", SOURCE_MANIFEST_SHA256))
    for name in ("runner_script", "config", "capital_replay_manifest", "execution_price_manifest"):
        descriptor = manifest["inputs"][name]
        archive.read(descriptor["path"], descriptor["sha256"])
    descriptor = manifest["artifacts"]["unavailable_lanes"]
    archive.read(descriptor["path"], descriptor["sha256"])
    index_descriptor = manifest["artifacts"]["artifact_index"]
    require(index_descriptor["sha256"] == SOURCE_INDEX_SHA256, "Source index authority changed")
    index = csv(archive.read(index_descriptor["path"], SOURCE_INDEX_SHA256))
    require(len(index) == 119 and not index.duplicated(list(COORDINATES) + ["name"]).any(),
            "Frozen artifact coverage changed")
    for row in index.to_dict("records"):
        archive.read(row["path"], row["sha256"])
    selected = index[index.name == "selected_candidates"].copy()
    require(len(selected) == 14 and not selected.duplicated(list(COORDINATES)).any(),
            "All fourteen selected lanes are required")
    summary = csv(archive.read(manifest["artifacts"]["summary"]["path"],
                              manifest["artifacts"]["summary"]["sha256"]))
    whole = summary[summary.execution_track == "whole_lot"]
    require(len(whole) == 14 and set(whole.apply(lane_key, axis=1)) == set(selected.apply(lane_key, axis=1)),
            "Old whole-lot summary coverage mismatch")
    return manifest, index, selected, whole


def capture_loader_watchlist(manifest):
    """Enumerate only files actually consumed by the historical candidate loader."""
    descriptors = manifest["inputs"]
    replay_path = Path(descriptors["capital_replay_manifest"]["path"])
    replay = json.loads(replay_path.read_bytes())
    capital_path = Path(replay["inputs"]["capital_manifest"]["path"])
    capital = json.loads(capital_path.read_bytes())
    shortlist_path = Path(capital["artifacts"]["shortlist"]["path"])
    index_path = Path(replay["artifacts"]["job_index"]["path"])
    paths = {replay_path, capital_path, shortlist_path, index_path,
             Path(replay["inputs"]["shortlist"]["path"])}
    for row in pd.read_csv(index_path).to_dict("records"):
        child_path = Path(row["output_dir"]) / "manifest.json"
        child = json.loads(child_path.read_bytes())
        paths.update((child_path, Path(child["artifacts"]["candidates"]["path"])))
    return {path.as_posix(): sha(path.read_bytes()) for path in sorted(paths)}


def captured_prices(manifest, archive, tickers):
    price_manifest = archive.document(manifest["inputs"]["execution_price_manifest"])
    require(price_manifest.get("status") == "READY"
            and price_manifest.get("manifest_type") == "ndx_cardinality_whole_lot_execution_price_bundle",
            "Invalid execution-price contract")
    descriptor = price_manifest["artifacts"]["inventory"]
    inventory = csv(archive.read(descriptor["path"], descriptor["sha256"]))
    require(not inventory.ticker.duplicated().any(), "Duplicate price identity")
    inventory = inventory.set_index("ticker")
    opens, closes = [], []
    for ticker in sorted(tickers):
        require(ticker in inventory.index, f"Missing price ticker: {ticker}")
        row = inventory.loc[ticker]
        require(row["status"] == "FETCHED", "Unfetched price series")
        archive.read(row["sidecar_path"], row["sidecar_sha256"])
        prices = csv(archive.read(row["path"], row["sha256"]))
        require(len(prices) == int(row["rows"]), "Price row count changed")
        dates = pd.to_datetime(prices.Date, errors="raise")
        require(dates.equals(dates.dt.normalize()) and not dates.duplicated().any()
                and dates.is_monotonic_increasing, "Invalid nominal session dates")
        values = prices[["Open", "Close"]].apply(pd.to_numeric, errors="raise")
        require(values.map(lambda value: math.isfinite(value) and value > 0).all().all(),
                "Invalid nominal marks")
        opens.append(pd.Series(values.Open.to_numpy(), index=dates, name=ticker))
        closes.append(pd.Series(values.Close.to_numpy(), index=dates, name=ticker))
    execution = pd.concat(opens, axis=1, join="inner").sort_index()
    valuation = pd.concat(closes, axis=1, join="inner").sort_index()
    require(not execution.empty and execution.index.equals(valuation.index), "Empty common calendar")
    execution.index.name = valuation.index.name = None
    return execution, valuation


def derive_inputs(root, archive, tickers):
    manifest, index, selected_index, old_summary = source_contract(root, archive)
    opens, closes = captured_prices(manifest, archive, tickers)
    lanes = {}
    for record in selected_index.to_dict("records"):
        selected = csv(archive.read(record["path"], record["sha256"]))
        key = lane_key(record)
        expected_count = 11 if "bounded_v3" in record["source_batch"] else 14
        require(len(selected) == expected_count, "Frozen schedule cadence changed")
        chains = {}
        for row in selected.to_dict("records"):
            identities = row["security_ids"].split(";")
            risks = row["risk_chains"].split(";")
            require(len(identities) == len(risks) == len(set(identities)), "Risk mapping is ambiguous")
            require(row["decision_data_end"] not in chains, "Duplicate decision date")
            chains[row["decision_data_end"]] = dict(zip(identities, risks))
        subset = index[index.apply(lane_key, axis=1) == key]
        old = {}
        for name in ("rebalances", "trades", "path"):
            match = subset[subset.name == "whole_lot_" + name]
            require(len(match) == 1, "Missing old whole-lot trace")
            row = match.iloc[0]
            old[name] = archive.read(row["path"], row["sha256"]).decode("utf-8")
        matched_summary = old_summary[old_summary.apply(lane_key, axis=1) == key]
        require(len(matched_summary) == 1, "Ambiguous old summary")
        schedule = source.build_dynamic_policy_schedule(selected)
        for decision in schedule:
            for date_name in ("decision_date", "execution_date"):
                decision[date_name] = pd.Timestamp(decision[date_name]).date().isoformat()
        lanes[key] = dict(schedule=schedule,
                          risk_chains=chains, old_traces=old,
                          old_summary_csv=frame_text(matched_summary))
    return manifest, opens, closes, lanes


def capture(root):
    root = Path(root).resolve()
    archive = CapturedSources()
    manifest, _, selected_index, _ = source_contract(root, archive)
    code_before = code_hashes(root)
    replay = archive.document(manifest["inputs"]["capital_replay_manifest"])
    before = capture_loader_watchlist(manifest)
    candidates, _ = source._load_completed_replay_candidates(replay)
    candidates["selection_date"] = pd.to_datetime(candidates.selection_date)
    candidates = candidates[candidates.selection_date <= pd.Timestamp(manifest["valuation_end"])]
    tickers = sorted(set(source.ORIGINAL_8) | {ticker for text in candidates.tickers for ticker in text.split(";")})
    provenance = {}
    for descriptor in selected_index.to_dict("records"):
        selected = csv(archive.read(descriptor["path"], descriptor["sha256"]))
        for row in selected.to_dict("records"):
            match = candidates[(candidates.source_batch == row["source_batch"])
                               & (candidates.universe_track == row["universe_track"])
                               & (candidates.portfolio_id == row["portfolio_id"])
                               & (candidates.selection_date == pd.Timestamp(row["selection_date"]))]
            require(len(match) == 1, "Selected upstream source is not unique")
            for name in ("security_ids", "issuer_ids", "risk_chains", "tickers", "weights",
                         "decision_data_end", "holding_count", "weight_spec"):
                require(match.iloc[0][name] == row[name], "Selected upstream identity/weight mismatch")
        provenance[lane_key(descriptor)] = len(selected)
    require(before == capture_loader_watchlist(manifest), "Candidate sources changed during capture")
    derive_inputs(root, archive, tickers)
    for path, encoded in archive.entries.items():
        require(sha(Path(path).read_bytes()) == sha(base64.b64decode(encoded)), "Captured source changed")
    require(code_before == code_hashes(root), "Code changed during capture")
    return dict(version=VERSION, code_hashes=code_before, tickers=tickers, sources=archive.entries,
                candidate_loader_consumed_hashes=before, selected_provenance_counts=provenance,
                upstream_provenance_checked_at_capture_only=True)


def replay(root, captured):
    require(set(captured) == CAPTURE_FIELDS, "Capture schema changed")
    require(captured["version"] == VERSION, "Unsupported bundle version")
    require(captured["upstream_provenance_checked_at_capture_only"] is True,
            "Upstream provenance verification scope changed")
    tickers = captured["tickers"]
    require(isinstance(tickers, list) and tickers and all(isinstance(value, str) and value
            and value == value.strip() for value in tickers) and tickers == sorted(set(tickers)),
            "Captured diagnostic ticker set is invalid")
    require(captured["code_hashes"] == code_hashes(root), "Execution code binding changed")
    archive = CapturedSources(captured["sources"])
    manifest, opens, closes, lanes = derive_inputs(root, archive, captured["tickers"])
    require(captured["selected_provenance_counts"] == {
        key: len(lane["schedule"]) for key, lane in lanes.items()}, "Capture coverage mismatch")
    results = {}
    for key, lane in sorted(lanes.items()):
        arguments = dict(execution_prices=opens, require_separate_execution_prices=True,
                         require_next_session_execution=True, require_issuer_trace=True,
                         initial_cash_usd=25000., minimum_cash_buffer_usd=100.,
                         transaction_cost_bps=10., valuation_end_date=manifest["valuation_end"])
        summary, rebalances, trades, path = simulate_dynamic_security_id_whole_lot_path(
            closes, lane["schedule"], **arguments)
        for name, frame in zip(("rebalances", "trades", "path"), (rebalances, trades, path)):
            pd.testing.assert_frame_equal(csv(frame_text(frame).encode()),
                                          csv(lane["old_traces"][name].encode()), check_exact=True)
        old_summary = csv(lane["old_summary_csv"].encode()).iloc[0]
        for name in ("path_return_net", "path_annualized_return_net", "path_max_drawdown",
                     "total_transaction_cost_usd", "rebalance_count", "minimum_target_k", "maximum_target_k"):
            require(math.isclose(float(summary[name]), float(old_summary[name]), rel_tol=1e-12, abs_tol=1e-12),
                    f"Old summary economic mismatch: {key}/{name}")
        require(summary["path_trading_session_count"] == old_summary["trading_session_count"]
                and summary["k_path"] == json.loads(old_summary["k_path"]), "Old path coverage mismatch")
        result = simulate_dynamic_security_id_conditional_repair_path(
            closes, lane["schedule"], risk_chains_by_decision=lane["risk_chains"], **arguments)
        frames = {name: None if result[name] is None else frame_text(result[name]) for name in FRAMES}
        metadata = {name: value for name, value in result.items() if name not in FRAMES}
        require(result["promotion_allowed"] is False and result["order_creation_allowed"] is False,
                "Research boundary violation")
        if not result["path_complete"]:
            require(result["execution_eligible"] is False and result["summary"] is None,
                    "Incomplete result claimed eligible")
        results[key] = dict(inputs=lane, legacy_rebuilt_summary=summary,
                            result=metadata, frames=frames)
    require(captured["code_hashes"] == code_hashes(root), "Code changed during replay")
    return results


def coverage(results):
    return dict(lane_count=len(results),
                statuses=dict(Counter(row["result"]["status"] for row in results.values())),
                schedule_counts={key: len(row["inputs"]["schedule"]) for key, row in results.items()},
                user_preference_track_rows=sum(key.endswith("/USER_PREFERENCE") for key in results),
                user_preference_rows_are_not_independent_samples=True,
                frozen_runner_tracks_not_merged=True,
                bounded_shorter_schedule_preserved=True,
                source_scope="SEALED_AVAILABLE_DEGRADED_RESEARCH_LANES_NOT_FULL_SEARCH_SPACE",
                calendar_scope="CAPTURED_DIAGNOSTIC_COMMON_CALENDAR_NOT_REVALIDATED_FULL_TRAINING_UNIVERSE",
                all_lanes_are_execution_diagnostics_not_admissions=True)


def run_lock(output, fingerprint):
    return _single_instance_lock(output / (fingerprint + ".lock"))


def build(repository_root):
    root = Path(repository_root).resolve()
    captured = capture(root)
    raw = json_bytes(captured)
    fingerprint = sha(raw)
    output = root / OUTPUT_RELATIVE
    output.mkdir(parents=True, exist_ok=True)
    final = output / fingerprint
    with run_lock(output, fingerprint):
        require(not final.exists(), "Immutable run already exists; use verify")
        staging = Path(tempfile.mkdtemp(prefix="pending_", dir=output))
        (staging / "capture.json").write_bytes(raw)
        results = replay(root, captured)
        results_raw = json_bytes(results)
        (staging / "results.json").write_bytes(results_raw)
        manifest = dict(version=VERSION, fingerprint=fingerprint, capture_sha256=sha(raw),
                        results_sha256=sha(results_raw), coverage=coverage(results),
                        research_only=True, promotion_allowed=False,
                        verification_scope="ARCHIVED_EXECUTION_REPLAY_NOT_FULL_TRAINING_PIT_REVALIDATION")
        (staging / "manifest.json").write_bytes(json_bytes(manifest))
        require(code_hashes(root) == captured["code_hashes"], "Code changed during build")
        staging.rename(final)
    return dict(status="RESEARCH_BUNDLE_BUILT", run_directory=final.as_posix(), **manifest)


def verify(repository_root, run_directory):
    root = Path(repository_root).resolve()
    run = Path(run_directory).resolve()
    require(run.parent == (root / OUTPUT_RELATIVE).resolve(), "Noncanonical run directory")
    require({path.name for path in run.iterdir()} == {"capture.json", "results.json", "manifest.json"},
            "Bundle file coverage changed")
    manifest = json.loads((run / "manifest.json").read_bytes())
    require(set(manifest) == MANIFEST_FIELDS, "Manifest schema changed")
    raw = (run / "capture.json").read_bytes()
    results_raw = (run / "results.json").read_bytes()
    require(sha(raw) == manifest["capture_sha256"] == manifest["fingerprint"] == run.name,
            "Capture fingerprint mismatch")
    require(sha(results_raw) == manifest["results_sha256"], "Results binding mismatch")
    captured = json.loads(raw)
    rebuilt = replay(root, captured)
    require(json_bytes(rebuilt) == results_raw, "Economic replay or lane coverage mismatch")
    require(manifest["coverage"] == coverage(rebuilt) and manifest["version"] == VERSION
            and manifest["research_only"] is True and manifest["promotion_allowed"] is False
            and manifest["verification_scope"] == "ARCHIVED_EXECUTION_REPLAY_NOT_FULL_TRAINING_PIT_REVALIDATION",
            "Manifest claims changed")
    return dict(status="VERIFIED_ARCHIVED_EXECUTION_REPLAY", **manifest)
