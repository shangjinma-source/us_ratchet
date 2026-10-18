"""Immutable-source economic replay for the v5 forward evaluation gate.

The existing v5 evaluator archives its result tables and a path/hash inventory,
but deliberately leaves the (mutable) price and 012922 source files outside the
evaluation run.  This module adds a research-only, fail-closed companion:

* freeze exact source bytes only while they still match the evaluation run;
* verify the frozen bundle without consulting current caches;
* rebuild candidate, original-eight and 012922 metrics with the production pure
  evaluator; and
* compare the rebuilt raw rows with the immutable evaluation artifact.

It never changes the v5 registry/specification or any live state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from backtest.ndx_challenger_forward_evaluation import (
    annotate_paired_execution_evidence,
    evaluate_candidate_pair,
    summarize_forward_readiness,
    summarize_research_tracks,
)
from backtest.ndx_challenger_forward_cohort import _constraints
from backtest.ndx_challenger_forward_registry import (
    validate_forward_spec,
    validate_registry_spec_binding,
)
from backtest.ndx_local_action_execution import evaluate_local_action_execution
from backtest.ndx_marginal_forward import read_cohort_index
from data.versioning import file_sha256


class NdxDynamicShadowP4ReplayError(ValueError):
    """Raised when immutable economic replay evidence is incomplete or changed."""


EVALUATION_ROOT_RELATIVE = Path("data/cache/research/ndx_challenger_forward_v5")
LATEST_RELATIVE = EVALUATION_ROOT_RELATIVE / "latest_evaluation/manifest.json"
BUNDLE_ROOT_RELATIVE = Path(
    "data/cache/research/ndx_dynamic_shadow_p4_replay_inputs_v1"
)
SPEC_RELATIVE = Path("config/ndx_challenger_forward_v5.yaml")
REGISTRY_RELATIVE = Path(
    "data/cache/research/ndx_challenger_forward_registry_v5/manifest.json"
)
ACTIVE_REGISTRY_RELATIVE = Path(
    "data/cache/research/ndx_challenger_forward_registry_v5/active_forward_registry.csv"
)
TARGET_RELATIVE = Path("data/cache/funds/012922.csv")
MANIFEST_TYPE = "ndx_dynamic_shadow_p4_replay_source_bundle"
MANIFEST_FIELDS = {
    "schema_version", "manifest_type", "evaluation_run_id", "created_at_utc",
    "status", "inputs", "artifacts", "boundaries", "manifest_sha256",
}
SOURCE_FIELDS = {
    "ticker", "source_path", "source_sha256", "frozen_path", "frozen_sha256",
    "rows",
}
BOUNDARIES = {
    "research_only": True,
    "current_cache_read_during_replay": False,
    "source_refetch_allowed": False,
    "historical_backfill_allowed": False,
    "promotion_allowed": False,
    "live_config_changed": False,
    "state_changed": False,
    "broker_snapshot_changed": False,
    "today_advice_changed": False,
    "orders_created": False,
}
IDENTITY_COLUMNS = (
    "registry_entry_id", "candidate_id", "selection_role", "action_scope",
    "research_track", "holding_count_interpretation", "holding_count",
    "candidate_tickers", "frozen_target_weights", "selection_rationale",
)


@dataclass(frozen=True)
class VerifiedReplayBundle:
    manifest: dict[str, Any]
    manifest_path: Path
    evaluation_run: dict[str, Any]
    evaluation_run_path: Path
    prices: dict[str, pd.DataFrame]
    target_012922: pd.DataFrame


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowP4ReplayError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise NdxDynamicShadowP4ReplayError(f"{label} must be a mapping")
    return payload


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    clean = dict(payload)
    clean.pop("manifest_sha256", None)
    encoded = json.dumps(
        clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_csv(path: Path, *, rows: int, label: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, low_memory=False, keep_default_na=False)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        if isinstance(exc, pd.errors.EmptyDataError) and rows == 0:
            return pd.DataFrame()
        raise NdxDynamicShadowP4ReplayError(f"cannot read {label}: {path}") from exc
    if len(frame) != int(rows):
        raise NdxDynamicShadowP4ReplayError(f"{label} row count changed")
    return frame


def _safe_ticker(value: Any) -> str:
    ticker = str(value).strip().upper()
    if not ticker or re.fullmatch(r"[A-Z0-9._-]+", ticker) is None:
        raise NdxDynamicShadowP4ReplayError(f"unsafe ticker in price inventory: {value}")
    return ticker


def _assert_file_binding(item: Mapping[str, Any], expected: Path, label: str) -> Path:
    if set(item) != {"path", "sha256"}:
        raise NdxDynamicShadowP4ReplayError(f"{label} binding fields changed")
    path = Path(str(item.get("path") or "")).resolve()
    if path != expected.resolve() or not path.is_file():
        raise NdxDynamicShadowP4ReplayError(f"{label} path is not canonical")
    if str(item.get("sha256")) != file_sha256(path):
        raise NdxDynamicShadowP4ReplayError(f"{label} hash changed")
    return path


def _validate_evaluation_run(
    run_path: Path, *, repository_root: Path,
) -> dict[str, Any]:
    root = repository_root.resolve()
    run_path = run_path.resolve()
    expected_parent = (root / EVALUATION_ROOT_RELATIVE / "evaluation_runs").resolve()
    if run_path.name != "manifest.json" or run_path.parent.parent != expected_parent:
        raise NdxDynamicShadowP4ReplayError("evaluation run path is not canonical")
    run = _load_json(run_path, "immutable v5 evaluation run")
    run_id = str(run.get("evaluation_run_id") or "")
    if (
        run.get("schema_version") != 1
        or run.get("manifest_type") != "ndx_challenger_forward_evaluation_run"
        or run_path.parent.name != run_id
        or run.get("promotion_allowed") is not False
        or run.get("live_config_changed") is not False
        or run.get("state_changed") is not False
        or run.get("today_advice_changed") is not False
    ):
        raise NdxDynamicShadowP4ReplayError("evaluation run identity or safety boundary changed")
    if int(run.get("registered_cohorts", -1)) <= 0:
        raise NdxDynamicShadowP4ReplayError("NO_COHORTS_NO_REPLAY_SOURCE_BUNDLE")
    _assert_file_binding(
        run.get("spec") or {}, root / SPEC_RELATIVE, "v5 forward spec",
    )
    _assert_file_binding(
        run.get("registry_manifest") or {}, root / REGISTRY_RELATIVE,
        "v5 registry manifest",
    )
    return run


def _price_inventory(run: Mapping[str, Any], run_path: Path) -> tuple[Path, pd.DataFrame]:
    item = (run.get("artifacts") or {}).get("price_inputs") or {}
    if set(item) != {"path", "rows", "sha256"}:
        raise NdxDynamicShadowP4ReplayError("price inventory binding fields changed")
    path = Path(str(item.get("path") or "")).resolve()
    expected = run_path.parent / "price_inputs.csv"
    if path != expected.resolve() or not path.is_file() or file_sha256(path) != item.get("sha256"):
        raise NdxDynamicShadowP4ReplayError("immutable price inventory changed")
    frame = _read_csv(path, rows=int(item.get("rows", -1)), label="price inventory")
    if set(frame.columns) != {"ticker", "path", "sha256"} or frame.empty:
        raise NdxDynamicShadowP4ReplayError("price inventory schema is incomplete")
    frame = frame.copy()
    frame["ticker"] = frame["ticker"].map(_safe_ticker)
    if frame["ticker"].duplicated().any() or "QQQ" not in set(frame["ticker"]):
        raise NdxDynamicShadowP4ReplayError("price inventory is duplicated or lacks QQQ")
    return path, frame.sort_values("ticker").reset_index(drop=True)


def _parse_target_bytes(raw: bytes) -> pd.DataFrame:
    try:
        frame = pd.read_csv(io.BytesIO(raw))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise NdxDynamicShadowP4ReplayError("cannot read frozen 012922 NAV") from exc
    required = {"Date", "Close"}
    if not required.issubset(frame.columns):
        raise NdxDynamicShadowP4ReplayError("frozen 012922 NAV columns are incomplete")
    frame = frame.copy()
    if not frame["Date"].astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise NdxDynamicShadowP4ReplayError("frozen 012922 NAV Date must be YYYY-MM-DD")
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    if (
        frame.empty or frame[["Date", "Close"]].isna().any().any()
        or frame["Date"].duplicated().any()
        or not frame["Close"].map(math.isfinite).all()
        or (frame["Close"] <= 0).any()
    ):
        raise NdxDynamicShadowP4ReplayError(
            "frozen 012922 NAV has invalid or duplicated source rows"
        )
    frame = frame.sort_values("Date")
    return frame.set_index("Date")


def _read_target(path: Path) -> pd.DataFrame:
    try:
        return _parse_target_bytes(path.read_bytes())
    except OSError as exc:
        raise NdxDynamicShadowP4ReplayError("cannot read frozen 012922 NAV") from exc


def _parse_price_bytes(raw: bytes, label: str) -> pd.DataFrame:
    """Parse the same bytes whose digest is recorded, avoiding source TOCTOU."""
    try:
        frame = pd.read_csv(io.BytesIO(raw))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise NdxDynamicShadowP4ReplayError(f"cannot parse {label} price bytes") from exc
    if not {"Date", "Open", "Close"}.issubset(frame.columns):
        raise NdxDynamicShadowP4ReplayError(f"{label} price columns are incomplete")
    frame = frame.copy()
    if not frame["Date"].astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise NdxDynamicShadowP4ReplayError(f"{label} Date must be YYYY-MM-DD")
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    for column in ("Open", "Close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if (
        frame.empty or frame[["Date", "Open", "Close"]].isna().any().any()
        or frame["Date"].duplicated().any()
        or not frame["Open"].map(math.isfinite).all()
        or not frame["Close"].map(math.isfinite).all()
        or (frame[["Open", "Close"]] <= 0).any().any()
    ):
        raise NdxDynamicShadowP4ReplayError(
            f"{label} price history has invalid or duplicated source rows"
        )
    frame = frame.sort_values("Date").set_index("Date")
    return frame


def _read_hashed_bytes(path: Path, expected_sha256: str, label: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise NdxDynamicShadowP4ReplayError(f"cannot read {label}: {path}") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise NdxDynamicShadowP4ReplayError(f"{label} bytes do not match archived hash")
    return raw


def canonical_replay_bundle_path(
    evaluation_run_id: str, *, repository_root: str | Path,
) -> Path:
    if re.fullmatch(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z", evaluation_run_id) is None:
        raise NdxDynamicShadowP4ReplayError("evaluation run id is invalid")
    return Path(repository_root).resolve() / BUNDLE_ROOT_RELATIVE / evaluation_run_id / "manifest.json"


def freeze_p4_replay_source_bundle(
    evaluation_run_manifest: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Copy exact still-matching source bytes into one immutable research bundle."""

    root = Path(repository_root).resolve()
    run_path = Path(evaluation_run_manifest).resolve()
    run = _validate_evaluation_run(run_path, repository_root=root)
    run_id = str(run["evaluation_run_id"])
    final_manifest = canonical_replay_bundle_path(run_id, repository_root=root)
    if final_manifest.exists():
        return verify_p4_replay_source_bundle(final_manifest, repository_root=root).manifest

    inventory_path, inventory = _price_inventory(run, run_path)
    target_binding = run.get("target_012922_version")
    if not isinstance(target_binding, Mapping):
        raise NdxDynamicShadowP4ReplayError("evaluation run has no 012922 source binding")
    target_source = Path(str(target_binding.get("path") or "")).resolve()
    expected_target = (root / TARGET_RELATIVE).resolve()
    if target_source != expected_target or not target_source.is_file():
        raise NdxDynamicShadowP4ReplayError("012922 source path is not canonical")
    target_bytes = _read_hashed_bytes(
        target_source, str(target_binding.get("sha256") or ""), "012922 source",
    )
    target_sidecar = target_source.with_name(target_source.name + ".manifest.json")
    try:
        sidecar_bytes = target_sidecar.read_bytes()
        sidecar = json.loads(sidecar_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowP4ReplayError("cannot read 012922 source sidecar") from exc
    if (
        sidecar.get("content_sha256") != hashlib.sha256(target_bytes).hexdigest()
        or sidecar.get("version_id") != target_binding.get("version_id")
    ):
        raise NdxDynamicShadowP4ReplayError("012922 source sidecar does not match the evaluation run")

    bundle_root = final_manifest.parent.parent
    bundle_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=bundle_root))
    try:
        price_entries: list[dict[str, Any]] = []
        price_dir = temporary / "prices"
        price_dir.mkdir()
        for row in inventory.to_dict("records"):
            ticker = _safe_ticker(row["ticker"])
            source = Path(str(row["path"])).resolve()
            expected_source = (root / "data/cache" / f"{ticker}.csv").resolve()
            if source != expected_source or not source.is_file():
                raise NdxDynamicShadowP4ReplayError(f"{ticker} source path is not canonical")
            expected_hash = str(row["sha256"])
            source_bytes = _read_hashed_bytes(source, expected_hash, f"{ticker} source")
            frame = _parse_price_bytes(source_bytes, ticker)
            frozen = price_dir / f"{ticker}.csv"
            frozen.write_bytes(source_bytes)
            price_entries.append({
                "ticker": ticker,
                "source_path": source.as_posix(),
                "source_sha256": expected_hash,
                "frozen_path": (
                    final_manifest.parent / "prices" / f"{ticker}.csv"
                ).as_posix(),
                "frozen_sha256": file_sha256(frozen),
                "rows": int(len(frame)),
            })

        target_dir = temporary / "target_012922"
        target_dir.mkdir()
        frozen_target = target_dir / target_source.name
        frozen_sidecar = target_dir / target_sidecar.name
        frozen_target.write_bytes(target_bytes)
        frozen_sidecar.write_bytes(sidecar_bytes)
        target_rows = len(_parse_target_bytes(target_bytes))
        payload: dict[str, Any] = {
            "schema_version": 1,
            "manifest_type": MANIFEST_TYPE,
            "evaluation_run_id": run_id,
            "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "status": "IMMUTABLE_REPLAY_SOURCES_FROZEN_RESEARCH_ONLY",
            "inputs": {
                "evaluation_run": {"path": run_path.as_posix(), "sha256": file_sha256(run_path)},
                "price_inventory": {
                    "path": inventory_path.as_posix(), "sha256": file_sha256(inventory_path),
                    "rows": int(len(inventory)),
                },
                "spec": dict(run["spec"]),
                "registry_manifest": dict(run["registry_manifest"]),
                "target_012922_version": dict(target_binding),
            },
            "artifacts": {
                "prices": sorted(price_entries, key=lambda item: item["ticker"]),
                "target_012922": {
                    "source_path": target_source.as_posix(),
                    "source_sha256": hashlib.sha256(target_bytes).hexdigest(),
                    "frozen_path": (
                        final_manifest.parent / "target_012922" / target_source.name
                    ).as_posix(),
                    "frozen_sha256": file_sha256(frozen_target),
                    "rows": int(target_rows),
                    "version_id": target_binding.get("version_id"),
                },
                "target_012922_sidecar": {
                    "source_path": target_sidecar.as_posix(),
                    "source_sha256": hashlib.sha256(sidecar_bytes).hexdigest(),
                    "frozen_path": (
                        final_manifest.parent / "target_012922" / target_sidecar.name
                    ).as_posix(),
                    "frozen_sha256": file_sha256(frozen_sidecar),
                },
            },
            "boundaries": dict(BOUNDARIES),
        }
        payload["manifest_sha256"] = _canonical_sha256(payload)
        temporary_manifest = temporary / "manifest.json"
        temporary_manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        try:
            os.replace(temporary, final_manifest.parent)
        except OSError:
            if final_manifest.exists():
                shutil.rmtree(temporary)
                return verify_p4_replay_source_bundle(
                    final_manifest, repository_root=root,
                ).manifest
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return verify_p4_replay_source_bundle(final_manifest, repository_root=root).manifest


def verify_p4_replay_source_bundle(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> VerifiedReplayBundle:
    """Verify a source bundle using only frozen copies for market data."""

    root = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    payload = _load_json(path, "P4 replay source bundle")
    if set(payload) != MANIFEST_FIELDS or payload.get("schema_version") != 1:
        raise NdxDynamicShadowP4ReplayError("replay bundle schema fields changed")
    run_id = str(payload.get("evaluation_run_id") or "")
    expected = canonical_replay_bundle_path(run_id, repository_root=root)
    if path != expected or payload.get("manifest_type") != MANIFEST_TYPE:
        raise NdxDynamicShadowP4ReplayError("replay bundle path or type is not canonical")
    if payload.get("status") != "IMMUTABLE_REPLAY_SOURCES_FROZEN_RESEARCH_ONLY":
        raise NdxDynamicShadowP4ReplayError("replay bundle status changed")
    if payload.get("boundaries") != BOUNDARIES:
        raise NdxDynamicShadowP4ReplayError("replay bundle safety boundary changed")
    if payload.get("manifest_sha256") != _canonical_sha256(payload):
        raise NdxDynamicShadowP4ReplayError("replay bundle canonical hash changed")

    inputs = payload.get("inputs") or {}
    if set(inputs) != {
        "evaluation_run", "price_inventory", "spec", "registry_manifest",
        "target_012922_version",
    }:
        raise NdxDynamicShadowP4ReplayError("replay bundle input fields changed")
    run_path = (
        root / EVALUATION_ROOT_RELATIVE / "evaluation_runs" / run_id / "manifest.json"
    ).resolve()
    if Path(str((inputs.get("evaluation_run") or {}).get("path") or "")).resolve() != run_path:
        raise NdxDynamicShadowP4ReplayError("bundle evaluation run path changed")
    if file_sha256(run_path) != (inputs.get("evaluation_run") or {}).get("sha256"):
        raise NdxDynamicShadowP4ReplayError("bundle evaluation run hash changed")
    run = _validate_evaluation_run(run_path, repository_root=root)
    for key in ("spec", "registry_manifest", "target_012922_version"):
        if inputs.get(key) != run.get(key):
            raise NdxDynamicShadowP4ReplayError(f"bundle {key} no longer matches evaluation run")
    inventory_path, inventory = _price_inventory(run, run_path)
    inventory_binding = inputs.get("price_inventory") or {}
    if (
        set(inventory_binding) != {"path", "sha256", "rows"}
        or Path(str(inventory_binding.get("path") or "")).resolve() != inventory_path
        or inventory_binding.get("sha256") != file_sha256(inventory_path)
        or int(inventory_binding.get("rows", -1)) != len(inventory)
    ):
        raise NdxDynamicShadowP4ReplayError("bundle price inventory binding changed")

    artifacts = payload.get("artifacts") or {}
    if set(artifacts) != {"prices", "target_012922", "target_012922_sidecar"}:
        raise NdxDynamicShadowP4ReplayError("replay bundle artifact fields changed")
    price_items = artifacts.get("prices")
    if not isinstance(price_items, list) or len(price_items) != len(inventory):
        raise NdxDynamicShadowP4ReplayError("frozen price inventory count changed")
    inventory_by_ticker = {str(row["ticker"]): row for row in inventory.to_dict("records")}
    prices: dict[str, pd.DataFrame] = {}
    seen: set[str] = set()
    for item in price_items:
        if not isinstance(item, Mapping) or set(item) != SOURCE_FIELDS:
            raise NdxDynamicShadowP4ReplayError("frozen price artifact fields changed")
        ticker = _safe_ticker(item.get("ticker"))
        if ticker in seen or ticker not in inventory_by_ticker:
            raise NdxDynamicShadowP4ReplayError("frozen price ticker set changed")
        seen.add(ticker)
        source_row = inventory_by_ticker[ticker]
        source_path = (root / "data/cache" / f"{ticker}.csv").resolve()
        frozen_path = (path.parent / "prices" / f"{ticker}.csv").resolve()
        if (
            Path(str(item.get("source_path") or "")).resolve() != source_path
            or item.get("source_sha256") != source_row["sha256"]
            or Path(str(source_row["path"])).resolve() != source_path
            or Path(str(item.get("frozen_path") or "")).resolve() != frozen_path
            or not frozen_path.is_file()
            or item.get("frozen_sha256") != item.get("source_sha256")
        ):
            raise NdxDynamicShadowP4ReplayError(f"frozen {ticker} price binding changed")
        frozen_bytes = _read_hashed_bytes(
            frozen_path, str(item.get("frozen_sha256") or ""), f"frozen {ticker}",
        )
        frame = _parse_price_bytes(frozen_bytes, ticker)
        if len(frame) != int(item.get("rows", -1)):
            raise NdxDynamicShadowP4ReplayError(f"frozen {ticker} price rows changed")
        prices[ticker] = frame
    if seen != set(inventory_by_ticker):
        raise NdxDynamicShadowP4ReplayError("frozen price ticker coverage changed")

    target_item = artifacts.get("target_012922") or {}
    sidecar_item = artifacts.get("target_012922_sidecar") or {}
    expected_target_keys = SOURCE_FIELDS.difference({"ticker"}).union({"version_id"})
    if set(target_item) != expected_target_keys or set(sidecar_item) != {
        "source_path", "source_sha256", "frozen_path", "frozen_sha256",
    }:
        raise NdxDynamicShadowP4ReplayError("frozen 012922 artifact fields changed")
    target_source = (root / TARGET_RELATIVE).resolve()
    frozen_target = (path.parent / "target_012922" / "012922.csv").resolve()
    frozen_sidecar = (path.parent / "target_012922" / "012922.csv.manifest.json").resolve()
    run_target = run["target_012922_version"]
    if (
        Path(str(target_item.get("source_path") or "")).resolve() != target_source
        or target_item.get("source_sha256") != run_target.get("sha256")
        or target_item.get("version_id") != run_target.get("version_id")
        or Path(str(target_item.get("frozen_path") or "")).resolve() != frozen_target
        or not frozen_target.is_file()
        or target_item.get("frozen_sha256") != target_item.get("source_sha256")
        or Path(str(sidecar_item.get("source_path") or "")).resolve()
        != target_source.with_name(target_source.name + ".manifest.json")
        or Path(str(sidecar_item.get("frozen_path") or "")).resolve() != frozen_sidecar
        or not frozen_sidecar.is_file()
        or sidecar_item.get("source_sha256") != sidecar_item.get("frozen_sha256")
    ):
        raise NdxDynamicShadowP4ReplayError("frozen 012922 binding changed")
    target_bytes = _read_hashed_bytes(
        frozen_target, str(target_item.get("frozen_sha256") or ""), "frozen 012922",
    )
    sidecar_bytes = _read_hashed_bytes(
        frozen_sidecar, str(sidecar_item.get("frozen_sha256") or ""),
        "frozen 012922 sidecar",
    )
    try:
        frozen_sidecar_payload = json.loads(sidecar_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowP4ReplayError("frozen 012922 sidecar is invalid") from exc
    if (
        frozen_sidecar_payload.get("content_sha256") != hashlib.sha256(target_bytes).hexdigest()
        or frozen_sidecar_payload.get("version_id") != target_item.get("version_id")
    ):
        raise NdxDynamicShadowP4ReplayError("frozen 012922 sidecar semantics changed")
    target = _parse_target_bytes(target_bytes)
    if len(target) != int(target_item.get("rows", -1)):
        raise NdxDynamicShadowP4ReplayError("frozen 012922 rows changed")
    return VerifiedReplayBundle(payload, path, run, run_path, prices, target)


def _parse_tickers(value: Any) -> list[str]:
    tickers = [_safe_ticker(item) for item in str(value).split(";") if str(item).strip()]
    if not tickers or len(set(tickers)) != len(tickers):
        raise NdxDynamicShadowP4ReplayError("candidate ticker list is empty or duplicated")
    return tickers


def _parse_weights(value: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in str(value).split(";"):
        if not item:
            continue
        try:
            ticker, raw = item.split(":", 1)
            parsed = float(raw)
        except (TypeError, ValueError) as exc:
            raise NdxDynamicShadowP4ReplayError("candidate weight map is malformed") from exc
        ticker = _safe_ticker(ticker)
        if ticker in result or not math.isfinite(parsed) or parsed <= 0:
            raise NdxDynamicShadowP4ReplayError("candidate weight map is invalid")
        result[ticker] = parsed
    if not result or not math.isclose(sum(result.values()), 1.0, abs_tol=1e-8):
        raise NdxDynamicShadowP4ReplayError("candidate weights do not sum to one")
    return result


def _validate_positions(
    positions: pd.DataFrame, candidate: Mapping[str, Any], *, expected_role: str,
    expected_weights: Mapping[str, float], observation_date: str,
    prices: Mapping[str, pd.DataFrame], standardized_cash: float,
    minimum_cash_buffer: float, expected_risk_chains: Mapping[str, str],
) -> None:
    required = {
        "registry_entry_id", "track_role", "ticker", "target_weight",
        "cohort_whole_lot_shares", "risk_chain", "observation_close",
    }
    if not required.issubset(positions.columns) or positions.empty:
        raise NdxDynamicShadowP4ReplayError("cohort positions are incomplete")
    if set(positions["track_role"].astype(str)) != {expected_role}:
        raise NdxDynamicShadowP4ReplayError("cohort position role changed")
    tickers = positions["ticker"].astype(str).map(_safe_ticker)
    if tickers.duplicated().any():
        raise NdxDynamicShadowP4ReplayError("cohort position ticker is duplicated")
    weights = pd.to_numeric(positions["target_weight"], errors="coerce")
    shares = pd.to_numeric(positions["cohort_whole_lot_shares"], errors="coerce")
    if (
        weights.isna().any() or not weights.map(math.isfinite).all()
        or shares.isna().any() or not shares.map(math.isfinite).all()
        or (shares < 0).any() or not (shares % 1 == 0).all()
    ):
        raise NdxDynamicShadowP4ReplayError("cohort positions contain invalid weights or shares")
    declared_tickers = set(_parse_tickers(candidate["candidate_tickers"]))
    declared_weights = _parse_weights(candidate["frozen_target_weights"])
    normalized_expected = {_safe_ticker(key): float(value) for key, value in expected_weights.items()}
    actual = dict(zip(tickers, weights.astype(float)))
    if (
        set(actual) != declared_tickers or set(actual) != set(declared_weights)
        or set(actual) != set(normalized_expected)
    ):
        raise NdxDynamicShadowP4ReplayError("cohort position ticker coverage changed")
    if any(
        not math.isclose(actual[key], declared_weights[key], abs_tol=1e-8)
        or not math.isclose(actual[key], normalized_expected[key], abs_tol=1e-8)
        for key in actual
    ):
        raise NdxDynamicShadowP4ReplayError("cohort position weights changed")
    normalized_chains = {
        _safe_ticker(key): str(value).strip()
        for key, value in expected_risk_chains.items()
    }
    actual_chains = dict(zip(tickers, positions["risk_chain"].astype(str).str.strip()))
    if (
        set(normalized_chains) != set(actual)
        or actual_chains != normalized_chains
        or any(not value for value in actual_chains.values())
    ):
        raise NdxDynamicShadowP4ReplayError("cohort position risk-chain mapping changed")
    observation = pd.Timestamp(observation_date).normalize()
    observation_closes: dict[str, float] = {}
    for ticker in sorted(actual):
        if ticker not in prices or observation not in prices[ticker].index:
            raise NdxDynamicShadowP4ReplayError(
                f"frozen prior-close price is missing: {ticker}/{observation_date}"
            )
        close = float(prices[ticker].loc[observation, "Close"])
        if not math.isfinite(close) or close <= 0:
            raise NdxDynamicShadowP4ReplayError(
                f"frozen prior-close price is invalid: {ticker}/{observation_date}"
            )
        observation_closes[ticker] = close
    declared_closes = dict(zip(
        tickers,
        pd.to_numeric(positions["observation_close"], errors="coerce").astype(float),
    ))
    if any(
        not math.isfinite(declared_closes[ticker])
        or not math.isclose(declared_closes[ticker], observation_closes[ticker], abs_tol=1e-9)
        for ticker in observation_closes
    ):
        raise NdxDynamicShadowP4ReplayError("cohort prior-close evidence changed")
    allocation = evaluate_local_action_execution(
        normalized_expected,
        observation_closes,
        normalized_chains,
        cash=float(standardized_cash),
        minimum_cash_buffer=float(minimum_cash_buffer),
        **_constraints(str(candidate["action_scope"])),
    )
    declared_shares = dict(zip(tickers, shares.astype(int)))
    if declared_shares != allocation["shares"]:
        raise NdxDynamicShadowP4ReplayError(
            "cohort whole-lot shares do not reproduce from prior-close frozen inputs"
        )
    declared_status = str(candidate.get("execution_track_status") or "")
    if declared_status == "COHORT_WHOLE_LOT_COMPLIANT" and not allocation["constraints_passed"]:
        raise NdxDynamicShadowP4ReplayError(
            "cohort claims executable status despite failed prior-close whole-lot allocation"
        )


def _canonical_forward_sessions(
    prices: Mapping[str, pd.DataFrame], *, observation_date: str,
    horizon: int, tickers: Sequence[str],
) -> tuple[pd.DatetimeIndex, dict[str, pd.DataFrame]]:
    """Lock every track to the same first QQQ sessions after observation."""

    observation = pd.Timestamp(observation_date).normalize()
    qqq = prices["QQQ"]
    sessions = pd.DatetimeIndex(qqq.index[qqq.index > observation])[: int(horizon)]
    scoped: dict[str, pd.DataFrame] = {}
    for ticker in sorted(set(tickers)):
        frame = prices[ticker]
        required = sessions.union(pd.DatetimeIndex([observation]))
        missing = required.difference(frame.index)
        if len(missing):
            raise NdxDynamicShadowP4ReplayError(
                f"frozen prices do not cover the canonical QQQ cohort calendar: "
                f"{ticker}/{missing[0].date().isoformat()}"
            )
        scoped[ticker] = frame.loc[required].sort_index().copy()
    return sessions, scoped


def _regime(qqq: pd.DataFrame, observation_date: str) -> str:
    history = qqq.loc[qqq.index <= pd.Timestamp(observation_date), "Close"].tail(200)
    if len(history) < 200:
        return "INSUFFICIENT_HISTORY"
    close = float(history.iloc[-1])
    above50 = close >= float(history.tail(50).mean())
    above200 = close >= float(history.mean())
    return "BULL" if above50 and above200 else (
        "BEAR" if not above50 and not above200 else "TRANSITION"
    )


def replay_cohort_evaluations(
    active_registry: pd.DataFrame,
    cohorts: Sequence[Mapping[str, Any]],
    prices: Mapping[str, pd.DataFrame],
    target_012922: pd.DataFrame,
    forward_contract: Mapping[str, Any],
    original8_weights: Mapping[str, float],
    risk_chains_by_registry: Mapping[str, Mapping[str, str]] | None = None,
) -> pd.DataFrame:
    """Rebuild raw economic rows for both research tracks and original-eight."""

    required_active = set(IDENTITY_COLUMNS)
    if not required_active.issubset(active_registry.columns) or active_registry.empty:
        raise NdxDynamicShadowP4ReplayError("active registry identity is incomplete")
    active = active_registry.copy()
    if active["registry_entry_id"].astype(str).duplicated().any():
        raise NdxDynamicShadowP4ReplayError("active registry id is duplicated")
    if set(active["research_track"].astype(str)) != {
        "portfolio_optimization", "migration_control",
    }:
        raise NdxDynamicShadowP4ReplayError("both independent research tracks are required")
    for key in (
        "primary_horizon_trading_days", "standardized_execution_cash_usd",
        "minimum_cash_buffer_usd", "transaction_cost_bps",
    ):
        value = float(forward_contract[key])
        if not math.isfinite(value) or value <= 0:
            raise NdxDynamicShadowP4ReplayError(f"forward contract {key} is invalid")
    if "QQQ" not in prices:
        raise NdxDynamicShadowP4ReplayError("frozen QQQ is required to rebuild regime")
    normalized_original8 = {
        _safe_ticker(key): float(value) for key, value in original8_weights.items()
    }
    if (
        not normalized_original8
        or any(not math.isfinite(value) or value <= 0 for value in normalized_original8.values())
        or not math.isclose(sum(normalized_original8.values()), 1.0, abs_tol=1e-8)
    ):
        raise NdxDynamicShadowP4ReplayError("frozen original-eight definition is invalid")

    rows: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    active_by_id = {
        str(row["registry_entry_id"]): row for row in active.to_dict("records")
    }
    for cohort in cohorts:
        if set(cohort) != {"observation_date", "fresh_oos_eligible", "candidates", "positions"}:
            raise NdxDynamicShadowP4ReplayError("cohort replay input fields changed")
        observation_date = pd.Timestamp(cohort["observation_date"]).strftime("%Y-%m-%d")
        if observation_date in seen_dates or cohort["fresh_oos_eligible"] is not True:
            raise NdxDynamicShadowP4ReplayError("cohort date is duplicated or not fresh OOS")
        seen_dates.add(observation_date)
        observation_regime = _regime(prices["QQQ"], observation_date)
        if observation_regime == "INSUFFICIENT_HISTORY":
            raise NdxDynamicShadowP4ReplayError(
                "frozen QQQ lacks 200 point-in-time closes for regime replay"
            )
        candidates = cohort["candidates"]
        positions = cohort["positions"]
        if not isinstance(candidates, pd.DataFrame) or not isinstance(positions, pd.DataFrame):
            raise NdxDynamicShadowP4ReplayError("cohort tables must be data frames")
        if "track_role" not in candidates.columns or "registry_entry_id" not in candidates.columns:
            raise NdxDynamicShadowP4ReplayError("cohort candidate identity is incomplete")
        challengers = candidates.loc[candidates["track_role"].astype(str).eq("CHALLENGER")].copy()
        controls = candidates.loc[candidates["track_role"].astype(str).eq("ORIGINAL_8_CONTROL")].copy()
        challenger_ids = challengers["registry_entry_id"].astype(str)
        if (
            len(challengers) != len(active) or challenger_ids.duplicated().any()
            or set(challenger_ids) != set(active_by_id) or len(controls) != 1
            or len(candidates) != len(active) + 1
        ):
            raise NdxDynamicShadowP4ReplayError("cohort does not contain full registry plus one original-eight control")
        control_id = str(controls.iloc[0]["registry_entry_id"])
        control_positions = positions.loc[
            positions["registry_entry_id"].astype(str).eq(control_id)
        ].copy()
        all_cohort_tickers = sorted(set(
            positions["ticker"].astype(str).map(_safe_ticker)
        ))
        missing = set(all_cohort_tickers).difference(prices)
        if missing:
            raise NdxDynamicShadowP4ReplayError(
                f"frozen prices missing candidate/control tickers: {sorted(missing)}"
            )
        _, cohort_prices = _canonical_forward_sessions(
            prices, observation_date=observation_date,
            horizon=int(forward_contract["primary_horizon_trading_days"]),
            tickers=all_cohort_tickers,
        )
        supplied_chains = risk_chains_by_registry or {}
        control_chains = supplied_chains.get(control_id)
        if control_chains is None:
            control_chains = dict(zip(
                control_positions["ticker"].astype(str),
                control_positions["risk_chain"].astype(str),
            ))
        _validate_positions(
            control_positions, controls.iloc[0], expected_role="ORIGINAL_8_CONTROL",
            expected_weights=normalized_original8,
            observation_date=observation_date, prices=cohort_prices,
            standardized_cash=float(forward_contract["standardized_execution_cash_usd"]),
            minimum_cash_buffer=float(forward_contract["minimum_cash_buffer_usd"]),
            expected_risk_chains=control_chains,
        )
        expected_position_ids = set(active_by_id).union({control_id})
        if set(positions["registry_entry_id"].astype(str)) != expected_position_ids:
            raise NdxDynamicShadowP4ReplayError("cohort position registry coverage changed")
        control_row = controls.iloc[0]
        for candidate in challengers.to_dict("records"):
            registry_id = str(candidate["registry_entry_id"])
            active_row = active_by_id[registry_id]
            for column in IDENTITY_COLUMNS:
                if str(candidate.get(column, "")) != str(active_row.get(column, "")):
                    raise NdxDynamicShadowP4ReplayError(
                        f"cohort candidate identity changed: {registry_id}/{column}"
                    )
            candidate_positions = positions.loc[
                positions["registry_entry_id"].astype(str).eq(registry_id)
            ].copy()
            candidate_chains = supplied_chains.get(registry_id)
            if candidate_chains is None:
                candidate_chains = dict(zip(
                    candidate_positions["ticker"].astype(str),
                    candidate_positions["risk_chain"].astype(str),
                ))
            _validate_positions(
                candidate_positions, candidate, expected_role="CHALLENGER",
                expected_weights=_parse_weights(candidate["frozen_target_weights"]),
                observation_date=observation_date, prices=cohort_prices,
                standardized_cash=float(forward_contract["standardized_execution_cash_usd"]),
                minimum_cash_buffer=float(forward_contract["minimum_cash_buffer_usd"]),
                expected_risk_chains=candidate_chains,
            )
            tickers = sorted(
                set(candidate_positions["ticker"].astype(str).map(_safe_ticker)).union(
                    control_positions["ticker"].astype(str).map(_safe_ticker)
                )
            )
            result = evaluate_candidate_pair(
                candidate_positions,
                control_positions,
                {ticker: cohort_prices[ticker] for ticker in tickers},
                observation_date=observation_date,
                horizon=int(forward_contract["primary_horizon_trading_days"]),
                standardized_cash=float(forward_contract["standardized_execution_cash_usd"]),
                minimum_cash_buffer=float(forward_contract["minimum_cash_buffer_usd"]),
                transaction_cost_bps=float(forward_contract["transaction_cost_bps"]),
                target_nav=target_012922,
            )
            identity = {
                "registry_entry_id": registry_id,
                "candidate_id": candidate["candidate_id"],
                "selection_role": candidate["selection_role"],
                "action_scope": candidate["action_scope"],
                "research_track": candidate["research_track"],
                "holding_count_interpretation": candidate["holding_count_interpretation"],
                "holding_count": candidate["holding_count"],
                "candidate_tickers": candidate["candidate_tickers"],
                "frozen_target_weights": candidate["frozen_target_weights"],
                "selection_rationale": candidate["selection_rationale"],
                "cohort_execution_track_status": candidate["execution_track_status"],
                "cohort_execution_constraint_failures": candidate["execution_constraint_failures"],
                "original_8_cohort_execution_track_status": control_row["execution_track_status"],
                "original_8_cohort_execution_constraint_failures": control_row["execution_constraint_failures"],
                "fresh_oos_eligible": True,
                "observation_regime": observation_regime,
            }
            row = {**identity, **result}
            rows.append({**row, **annotate_paired_execution_evidence(row)})
    return pd.DataFrame(rows)


def assert_replayed_evaluations_match(
    replayed: pd.DataFrame, archived: pd.DataFrame,
) -> None:
    """Reject any raw metric, identity, regime or 012922 value mismatch."""

    if set(replayed.columns) != set(archived.columns) or len(replayed) != len(archived):
        raise NdxDynamicShadowP4ReplayError("replayed evaluation schema or row count changed")
    keys = ["observation_date", "registry_entry_id"]
    if not set(keys).issubset(replayed.columns):
        raise NdxDynamicShadowP4ReplayError("replayed evaluation coordinate is missing")
    if replayed[keys].astype(str).duplicated().any() or archived[keys].astype(str).duplicated().any():
        raise NdxDynamicShadowP4ReplayError("replayed evaluation coordinate is duplicated")
    # Match the evaluator's CSV round trip before comparing mixed bool/nullable columns.
    buffer = io.StringIO()
    replayed.to_csv(buffer, index=False)
    buffer.seek(0)
    normalized = pd.read_csv(buffer, low_memory=False, keep_default_na=False)
    normalized = normalized[archived.columns]
    normalized = normalized.sort_values(keys).reset_index(drop=True)
    archived_sorted = archived.sort_values(keys).reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(
            normalized, archived_sorted, check_dtype=False, check_exact=False,
            rtol=1e-12, atol=1e-12,
        )
    except AssertionError as exc:
        raise NdxDynamicShadowP4ReplayError(
            "archived evaluation rows do not match immutable-source economic replay"
        ) from exc


def _load_production_cohorts(
    run: Mapping[str, Any], *, repository_root: Path, spec_path: Path,
    registry_path: Path, registry_content_sha256: str, active_count: int,
    first_fresh_observation: str,
) -> list[dict[str, Any]]:
    item = run.get("cohort_index")
    if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
        raise NdxDynamicShadowP4ReplayError("evaluation run cohort index is missing")
    expected = repository_root / EVALUATION_ROOT_RELATIVE / "cohort_index.jsonl"
    index_path = Path(str(item.get("path") or "")).resolve()
    if index_path != expected.resolve() or file_sha256(index_path) != item.get("sha256"):
        raise NdxDynamicShadowP4ReplayError("evaluation run cohort index changed")
    records = read_cohort_index(index_path)
    if len(records) != int(run.get("registered_cohorts", -1)):
        raise NdxDynamicShadowP4ReplayError("evaluation run cohort count changed")
    cohorts: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for record in records:
        date = str(record.get("observation_date") or "")
        if (
            date in seen_dates
            or pd.Timestamp(date).normalize() < pd.Timestamp(first_fresh_observation).normalize()
            or record.get("fresh_oos_eligible") is not True
            or int(record.get("active_candidate_count", -1)) != active_count
        ):
            raise NdxDynamicShadowP4ReplayError(
                "cohort date, freshness, or active candidate identity changed"
            )
        seen_dates.add(date)
        manifest_path = (
            repository_root / EVALUATION_ROOT_RELATIVE / "observations" / date / "manifest.json"
        ).resolve()
        if (
            Path(str(record.get("cohort_manifest_path") or "")).resolve() != manifest_path
            or not manifest_path.is_file()
            or file_sha256(manifest_path) != record.get("cohort_manifest_sha256")
        ):
            raise NdxDynamicShadowP4ReplayError("cohort manifest binding changed")
        manifest = _load_json(manifest_path, "cohort manifest")
        if (
            manifest.get("schema_version") != 1
            or manifest.get("manifest_type") != "ndx_challenger_forward_cohort"
            or manifest.get("observation_date") != date
            or manifest.get("fresh_oos_eligible") is not True
            or int(manifest.get("active_candidate_count", -1)) != active_count
            or int(manifest.get("same_date_original_8_control_count", -1)) != 1
            or manifest.get("promotion_allowed") is not False
            or manifest.get("live_config_changed") is not False
            or manifest.get("state_changed") is not False
            or manifest.get("today_advice_changed") is not False
        ):
            raise NdxDynamicShadowP4ReplayError("cohort manifest identity changed")
        inputs = manifest.get("inputs") or {}
        for key, expected_path in (
            ("spec", spec_path), ("registry_manifest", registry_path),
        ):
            item = inputs.get(key) or {}
            if (
                Path(str(item.get("path") or "")).resolve() != expected_path.resolve()
                or item.get("sha256") != file_sha256(expected_path)
            ):
                raise NdxDynamicShadowP4ReplayError(f"cohort {key} identity changed")
        if inputs.get("registry_content_sha256") != registry_content_sha256:
            raise NdxDynamicShadowP4ReplayError("cohort registry content identity changed")
        artifacts = manifest.get("artifacts") or {}
        tables: dict[str, pd.DataFrame] = {}
        for key, filename, record_key in (
            ("cohort_candidates", "cohort_candidates.csv", "cohort_candidates_sha256"),
            ("cohort_positions", "cohort_positions.csv", "cohort_positions_sha256"),
        ):
            artifact = artifacts.get(key) or {}
            artifact_path = (manifest_path.parent / filename).resolve()
            if (
                Path(str(artifact.get("path") or "")).resolve() != artifact_path
                or not artifact_path.is_file()
                or file_sha256(artifact_path) != artifact.get("sha256")
                or artifact.get("sha256") != record.get(record_key)
            ):
                raise NdxDynamicShadowP4ReplayError(f"cohort {key} binding changed")
            tables[key] = _read_csv(
                artifact_path, rows=int(artifact.get("rows", -1)), label=key,
            )
        cohorts.append({
            "observation_date": date,
            "fresh_oos_eligible": record.get("fresh_oos_eligible"),
            "candidates": tables["cohort_candidates"],
            "positions": tables["cohort_positions"],
        })
    return cohorts


def verify_p4_economic_replay(
    bundle_manifest: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Rebuild the canonical immutable v5 raw rows from frozen source bytes."""

    root = Path(repository_root).resolve()
    bundle = verify_p4_replay_source_bundle(bundle_manifest, repository_root=root)
    run = bundle.evaluation_run
    latest_path = (root / LATEST_RELATIVE).resolve()
    latest = _load_json(latest_path, "canonical latest v5 evaluation")
    immutable = latest.get("immutable_evaluation_run") or {}
    if (
        latest.get("schema_version") != 1
        or latest.get("manifest_type") != "ndx_challenger_forward_evaluation"
        or latest.get("promotion_allowed") is not False
        or latest.get("live_config_changed") is not False
        or latest.get("state_changed") is not False
        or latest.get("today_advice_changed") is not False
        or Path(str(immutable.get("path") or "")).resolve() != bundle.evaluation_run_path
        or immutable.get("sha256") != file_sha256(bundle.evaluation_run_path)
        or immutable.get("evaluation_run_id") != run.get("evaluation_run_id")
    ):
        raise NdxDynamicShadowP4ReplayError(
            "canonical latest evaluation does not bind the replayed immutable run"
        )
    spec_path = root / SPEC_RELATIVE
    registry_path = root / REGISTRY_RELATIVE
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    registry = _load_json(registry_path, "v5 registry manifest")
    validate_forward_spec(spec)
    validate_registry_spec_binding(registry, spec, spec_sha256=file_sha256(spec_path))
    active_item = (registry.get("artifacts") or {}).get("active_registry") or {}
    active_path = root / ACTIVE_REGISTRY_RELATIVE
    if (
        Path(str(active_item.get("path") or "")).resolve() != active_path.resolve()
        or not active_path.is_file() or active_item.get("sha256") != file_sha256(active_path)
    ):
        raise NdxDynamicShadowP4ReplayError("active registry binding changed")
    active = _read_csv(
        active_path, rows=int(active_item.get("rows", -1)), label="active registry",
    )
    if (
        len(active) != int(registry.get("active_candidate_count", -1))
        or len(active) != int(run.get("portfolio_optimization_active_candidates", 0))
        + int(run.get("migration_control_active_candidates", 0))
    ):
        raise NdxDynamicShadowP4ReplayError("active registry/run candidate count changed")
    baseline_item = (registry.get("artifacts") or {}).get("baseline") or {}
    baseline_path = registry_path.parent / "original_8_forward_baseline.csv"
    if (
        set(baseline_item) != {"path", "rows", "sha256"}
        or Path(str(baseline_item.get("path") or "")).resolve() != baseline_path.resolve()
        or not baseline_path.is_file()
        or file_sha256(baseline_path) != baseline_item.get("sha256")
    ):
        raise NdxDynamicShadowP4ReplayError("frozen original-eight baseline binding changed")
    baseline = _read_csv(
        baseline_path, rows=int(baseline_item.get("rows", -1)),
        label="original-eight baseline",
    )
    if (
        not {"ticker", "frozen_weight"}.issubset(baseline.columns)
        or len(baseline) != 8 or baseline["ticker"].astype(str).duplicated().any()
    ):
        raise NdxDynamicShadowP4ReplayError("frozen original-eight baseline is incomplete")
    original8_weights = dict(zip(
        baseline["ticker"].astype(str),
        pd.to_numeric(baseline["frozen_weight"], errors="raise").astype(float),
    ))
    risk_item = (registry.get("artifacts") or {}).get("risk_chain_map") or {}
    risk_path = registry_path.parent / "frozen_candidate_risk_chain_map.csv"
    if (
        set(risk_item) != {"path", "rows", "sha256"}
        or Path(str(risk_item.get("path") or "")).resolve() != risk_path.resolve()
        or not risk_path.is_file()
        or risk_item.get("sha256") != file_sha256(risk_path)
    ):
        raise NdxDynamicShadowP4ReplayError("frozen candidate risk-chain binding changed")
    risk_frame = _read_csv(
        risk_path, rows=int(risk_item.get("rows", -1)), label="candidate risk-chain map",
    )
    required_risk_columns = {"registry_entry_id", "ticker", "risk_chain"}
    if (
        not required_risk_columns.issubset(risk_frame.columns)
        or risk_frame[["registry_entry_id", "ticker"]].astype(str).duplicated().any()
        or risk_frame["risk_chain"].astype(str).str.strip().eq("").any()
    ):
        raise NdxDynamicShadowP4ReplayError("frozen candidate risk-chain map is invalid")
    risk_chains_by_registry: dict[str, dict[str, str]] = {
        registry_id: dict(zip(
            group["ticker"].astype(str).map(_safe_ticker),
            group["risk_chain"].astype(str),
        ))
        for registry_id, group in risk_frame.groupby(
            risk_frame["registry_entry_id"].astype(str), sort=False,
        )
    }
    if not {str(value) for value in active["registry_entry_id"]}.issubset(risk_chains_by_registry):
        raise NdxDynamicShadowP4ReplayError("frozen candidate risk-chain coverage is incomplete")
    if not {"ticker", "risk_chain"}.issubset(baseline.columns):
        raise NdxDynamicShadowP4ReplayError("frozen original-eight risk-chain map is missing")
    risk_chains_by_registry["ORIGINAL_8_CONTROL"] = dict(zip(
        baseline["ticker"].astype(str).map(_safe_ticker),
        baseline["risk_chain"].astype(str),
    ))
    cohorts = _load_production_cohorts(
        run, repository_root=root, spec_path=spec_path,
        registry_path=registry_path,
        registry_content_sha256=str(active_item.get("sha256") or ""),
        active_count=len(active),
        first_fresh_observation=str(
            spec["forward_contract"]["first_fresh_observation_on_or_after"]
        ),
    )
    required_tickers = {"QQQ"}
    for cohort in cohorts:
        required_tickers.update(cohort["positions"]["ticker"].astype(str).map(_safe_ticker))
    if set(bundle.prices) != required_tickers:
        raise NdxDynamicShadowP4ReplayError("frozen price bundle is not the exact cohort/control Cartesian coverage")
    replayed = replay_cohort_evaluations(
        active, cohorts, bundle.prices, bundle.target_012922, spec["forward_contract"],
        original8_weights, risk_chains_by_registry,
    )
    evaluations_item = (run.get("artifacts") or {}).get("evaluations") or {}
    evaluations_path = bundle.evaluation_run_path.parent / "cohort_evaluations.csv"
    if (
        Path(str(evaluations_item.get("path") or "")).resolve() != evaluations_path.resolve()
        or file_sha256(evaluations_path) != evaluations_item.get("sha256")
    ):
        raise NdxDynamicShadowP4ReplayError("immutable raw evaluation artifact changed")
    archived = _read_csv(
        evaluations_path, rows=int(evaluations_item.get("rows", -1)),
        label="immutable raw evaluations",
    )
    assert_replayed_evaluations_match(replayed, archived)
    summary = summarize_forward_readiness(
        active, replayed, spec["forward_contract"], spec["promotion_contract"],
    )
    tracks = summarize_research_tracks(summary)
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_p4_economic_replay_verification",
        "status": "RAW_ECONOMIC_PATH_REPLAY_VERIFIED_RESEARCH_ONLY",
        "source_bundle": {
            "path": bundle.manifest_path.as_posix(),
            "sha256": file_sha256(bundle.manifest_path),
            "manifest_sha256": bundle.manifest["manifest_sha256"],
        },
        "immutable_evaluation_run": {
            "path": bundle.evaluation_run_path.as_posix(),
            "sha256": file_sha256(bundle.evaluation_run_path),
        },
        "registered_cohorts": len(cohorts),
        "replayed_evaluation_rows": len(replayed),
        "portfolio_optimization_rows": int(
            replayed["research_track"].astype(str).eq("portfolio_optimization").sum()
        ),
        "migration_control_rows": int(
            replayed["research_track"].astype(str).eq("migration_control").sum()
        ),
        "original_8_same_date_control_replayed": True,
        "target_012922_replayed": True,
        "qqq_regime_replayed": True,
        "summary": summary,
        "research_track_summary": tracks,
        "raw_economic_path_replay_implemented": True,
        "raw_economic_path_replay_verified": True,
        "promotion_allowed": False,
        "live_mutation": False,
    }


__all__ = [
    "NdxDynamicShadowP4ReplayError",
    "VerifiedReplayBundle",
    "assert_replayed_evaluations_match",
    "canonical_replay_bundle_path",
    "freeze_p4_replay_source_bundle",
    "replay_cohort_evaluations",
    "verify_p4_economic_replay",
    "verify_p4_replay_source_bundle",
]
