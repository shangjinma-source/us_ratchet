"""Read-only economic replay of all shadow lanes and their frozen price evidence.

No fetch, append, repair, or persistent artifact publication occurs here.
Dependency verification can create and delete temporary lifecycle parse files.
Realization is reconstructed at its recorded timestamp, not today's clock.
"""
from io import BytesIO
import hashlib
import json
from pathlib import Path

import pandas as pd

from backtest import ndx_dynamic_shadow_daily as core
from backtest import ndx_dynamic_shadow_daily_v2 as calendar
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance
from data.ndx_price_basis import RECOGNIZED_SOURCE_MODES


DAILY_ROOT = Path("data/cache/research/ndx_dynamic_shadow_daily_v1")
ORIGINAL = Path("data/cache/research/ndx_original_8_control_v1/manifest.json")
SELECTORS = {f"{track}__{role.lower()}__v1" for track in core.TRACKS for role in core.ROLES}
CONTROL = "ndx_original_8_incumbent_v0"
NOMINAL_FIELDS = {
    "schema_version", "manifest_type", "status", "valuation_end_date", "tickers",
    "price_basis", "execution_field", "valuation_field", "sources", "artifact",
    "module_sha256", "script_sha256", "promotion_allowed", "live_mutation", "manifest_sha256",
}


class DailyEconomicReplayError(core.NdxDynamicShadowDailyError):
    pass


def _require(condition, message):
    if not condition:
        raise DailyEconomicReplayError("daily economic replay: " + message)


def _same(left, right):
    return core.canonical_sha256(left) == core.canonical_sha256(right)


class _ReadSet:
    def __init__(self):
        self.files = {}
        self.directories = {}

    def read(self, path):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        _require(path not in self.files or self.files[path] == digest, "source changed while reading")
        self.files[path] = digest
        return raw

    def json(self, path):
        return json.loads(self.read(path))

    def children(self, path):
        path = Path(path).resolve()
        names = tuple(sorted(item.name for item in path.iterdir())) if path.is_dir() else ()
        _require(path not in self.directories or self.directories[path] == names, "directory changed")
        self.directories[path] = names
        return [path / name for name in names]

    def check(self):
        for path, digest in self.files.items():
            _require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, "bound bytes changed")
        for path, names in self.directories.items():
            current = tuple(sorted(item.name for item in path.iterdir())) if path.is_dir() else ()
            _require(current == names, "bound directory changed")


def _verified_original(root, reads):
    path = root / ORIGINAL
    payload = reads.json(path)
    core.load_frozen_original_8_definition(path)
    return payload["definition"]["securities"], reads.files[path.resolve()]


def _realized_lanes(root, sessions, reads, original_hash):
    directory = root / DAILY_ROOT / "realized_decisions"
    batches = core.verify_realized_decision_chain(directory)
    directories = [p for p in reads.children(directory) if p.is_dir() and not p.name.startswith(".")]
    _require({p.name for p in directories} == {b["decision_date"] for b in batches}, "batch inventory changed")
    lanes = {name: [] for name in SELECTORS}
    receipts = {}
    for batch in batches:
        decision = acceptance.decision_date(batch["decision_date"])
        batch_dir = directory / decision
        _require(_same(reads.json(batch_dir / "batch_manifest.json"), batch), "batch changed")
        reads.children(batch_dir)
        receipt_path = root / acceptance.ACCEPTANCE / decision / "receipt.json"
        receipt = acceptance.verify_acceptance(receipt_path)
        _require(_same(reads.json(receipt_path), receipt), "receipt changed")
        receipts[decision] = receipt
        final_path = root / acceptance.SEARCH / "final" / decision / "manifest.json"
        final = core.verify_final_candidate_snapshot(final_path)
        _require(_same(reads.json(final_path), final), "final changed")
        _require(final["original_8_sha256"] == original_hash, "original-8 final binding changed")
        _require(Path(receipt["final_binding"]["path"]).resolve() == final_path.resolve()
                 and receipt["final_binding"]["sha256"] == reads.files[final_path.resolve()], "receipt final changed")

        def frame(name):
            item = final["artifacts"][name]
            path = (final_path.parent / item["filename"]).resolve()
            _require(path.parent == final_path.parent.resolve(), "final artifact path escaped")
            raw = reads.read(path)
            _require(hashlib.sha256(raw).hexdigest() == item["sha256"], "final artifact changed")
            # Match the frozen realization builder's parser for target weights.
            return pd.read_csv(BytesIO(raw), low_memory=False)

        candidates, roles, jobs = frame("candidates"), frame("role_lock"), frame("job_plan")
        _require(set(jobs["decision_date"].astype(str)) == {decision}, "job coordinate changed")
        timing = core.resolve_first_observed_execution_session(sessions, decision)
        _require(timing is not None, "realization has no completed next session")
        sealed = core._aware_utc(final["roles_sealed_at_utc"], "role seal")
        _require(sealed < core._aware_utc(timing["execution_open_timestamp_utc"], "execution open"), "late role seal")
        actual = {}
        for filename in batch["artifacts"]:
            lane = reads.json(batch_dir / filename)
            _require(lane["selector_id"] not in actual, "duplicate realized selector")
            actual[lane["selector_id"]] = lane
        _require(set(actual) == SELECTORS and set(roles["selector_id"].astype(str)) == SELECTORS, "incomplete lane matrix")
        for role in roles.itertuples(index=False):
            selector = str(role.selector_id)
            lane = actual[selector]
            realized_at = core._aware_utc(lane["timing"]["execution_realized_at_utc"], "realized at")
            _require(realized_at >= core._aware_utc(timing["execution_close_timestamp_utc"], "execution close"), "premature realization")
            portfolio = "" if pd.isna(role.portfolio_id) else str(role.portfolio_id)
            selected = None
            if role.status != "REFERENCE_UNAVAILABLE_NOT_REPLACED":
                matches = candidates.loc[candidates["universe_track"].astype(str).eq(str(role.universe_track))
                                         & candidates["portfolio_id"].astype(str).eq(portfolio)]
                _require(len(matches) == 1, "role candidate is not unique")
                chosen = matches.iloc[0]
                selected = {"portfolio_id": portfolio, "holding_count": int(chosen["holding_count"]),
                            "targets": core._target_payload(chosen)}
            else:
                _require(role.policy_role == "USER_PREFERENCE", "competitive role unavailable")
            prior = lanes[selector][-1] if lanes[selector] else None
            expected = {
                "schema_version": 1, "artifact_type": "ndx_dynamic_shadow_realized_monthly_lane_decision",
                "selector_id": selector, "universe_track": str(role.universe_track),
                "policy_role": str(role.policy_role), "decision_sequence": len(lanes[selector]) + 1,
                "previous_decision_sha256": prior["payload_sha256"] if prior else None,
                "timing": {**timing, "candidate_sealed_at_utc": sealed.isoformat(),
                           "execution_realized_at_utc": realized_at.isoformat()},
                "status": str(role.status), "selected_candidate": selected,
                "provenance": {"candidate_manifest_path": final_path.resolve().as_posix(),
                               "candidate_manifest_sha256": reads.files[final_path.resolve()],
                               "snapshot_manifest_sha256": final["snapshot_manifest_sha256"],
                               "snapshot_fingerprint": final["snapshot_fingerprint"]},
                "selection_training_only": True, "fresh_oos_outcome_consumed_at_selection": False,
                "historical_candidate_replay_used": False, "independent_lane_only": True,
                "promotion_allowed": False, "live_mutation": False,
            }
            expected["payload_sha256"] = core.canonical_sha256(expected)
            _require(_same(lane, expected), f"realized final/targets/timing differ: {selector}")
            lanes[selector].append(lane)
    return lanes, receipts


def _tickers(lanes, securities):
    names = {str(value["ticker"]).upper() for value in securities}
    for decisions in lanes.values():
        for decision in decisions:
            for target in ((decision.get("selected_candidate") or {}).get("targets") or {}).values():
                names.add(str(target["ticker"]).upper())
    return sorted(names)


def _nominal(path, root, sessions, tickers, reads):
    path = Path(path).resolve()
    payload = reads.json(path)
    end = acceptance.decision_date(payload["valuation_end_date"])
    expected = (root / DAILY_ROOT / "nominal_price_evidence" / end / "manifest.json").resolve()
    _require(path == expected, "nominal manifest is not canonical")
    unsigned = dict(payload)
    declared = unsigned.pop("manifest_sha256", None)
    _require(set(payload) == NOMINAL_FIELDS and declared == core.canonical_sha256(unsigned), "nominal schema/hash changed")
    _require(type(payload["schema_version"]) is int and payload["schema_version"] == 1
             and payload["manifest_type"] == "ndx_dynamic_shadow_nominal_open_close_evidence"
             and payload["status"] == "IMMUTABLE_EXACT_TICKER_SESSION_GRID"
             and payload["price_basis"] == "UNADJUSTED_NOMINAL_TRADE_PRICE"
             and payload["execution_field"] == "Open" and payload["valuation_field"] == "Close"
             and payload["promotion_allowed"] is False and payload["live_mutation"] is False,
             "nominal basis/boundary changed")
    for key, relative in (("module_sha256", "backtest/ndx_dynamic_shadow_daily.py"),
                          ("script_sha256", "scripts/ndx_dynamic_shadow_daily.py")):
        _require(hashlib.sha256(reads.read(root / relative)).hexdigest() == payload[key], "nominal code changed")
    _require(payload["tickers"] == tickers and set(payload["sources"]) == set(tickers), "nominal ticker inventory changed")
    frames = []
    for ticker in tickers:
        descriptor = payload["sources"][ticker]
        _require(set(descriptor) == {"filename", "rows", "sha256", "source_mode", "fallback_errors", "data_start", "data_end"}
                 and descriptor["filename"] == f"sources/{ticker}.csv", "nominal source schema/path changed")
        _require(isinstance(descriptor["source_mode"], str)
                 and descriptor["source_mode"] in RECOGNIZED_SOURCE_MODES,
                 "nominal source mode is not recognized as unadjusted")
        _require(type(descriptor["rows"]) is int and descriptor["rows"] > 0,
                 "nominal source rows must be a positive integer")
        source = (path.parent / descriptor["filename"]).resolve()
        _require(source.parent == (path.parent / "sources").resolve(), "nominal ticker path escaped")
        raw = reads.read(source)
        _require(hashlib.sha256(raw).hexdigest() == descriptor["sha256"], "nominal source hash changed")
        frame = pd.read_csv(BytesIO(raw), float_precision="round_trip", keep_default_na=False)
        _require(list(frame.columns) == ["Date", "ticker", "Open", "Close"]
                 and len(frame) == descriptor["rows"] and set(frame["ticker"]) == {ticker}, "nominal source grid changed")
        normalized = core.validate_nominal_price_evidence(frame, sessions, tickers=[ticker], valuation_end_date=end)
        _require(descriptor["data_start"] == normalized["Date"].iloc[0].date().isoformat()
                 and descriptor["data_end"] == normalized["Date"].iloc[-1].date().isoformat(), "nominal source date metadata changed")
        frames.append(normalized)
    combined = core.validate_nominal_price_evidence(pd.concat(frames, ignore_index=True), sessions,
                                                   tickers=tickers, valuation_end_date=end)
    artifact = payload["artifact"]
    _require(set(artifact) == {"filename", "rows", "sha256"} and artifact["filename"] == "prices.csv"
             and type(artifact["rows"]) is int and artifact["rows"] == len(combined), "combined nominal descriptor changed")
    raw = reads.read(path.parent / "prices.csv")
    _require(hashlib.sha256(raw).hexdigest() == artifact["sha256"], "combined nominal hash changed")
    rebuilt = combined.assign(Date=combined["Date"].dt.date.astype(str)).to_csv(index=False, lineterminator="\n").encode()
    _require(raw == rebuilt, "nominal combined bytes do not rebuild from sources")
    opens = combined.pivot(index="Date", columns="ticker", values="Open")
    closes = combined.pivot(index="Date", columns="ticker", values="Close")
    return opens, closes, end


def _economic_rows(path, rebalances, trades):
    rows = {}
    for row in path.itertuples(index=False):
        date = str(row.date)
        rows[date] = {
            "path_state": {"cash_usd": float(row.cash_usd), "holdings_value_usd": float(row.holdings_value_usd),
                           "total_value_usd": float(row.total_value_usd), "holding_count": int(row.holding_count),
                           "active_security_ids": str(row.active_security_ids), "active_tickers": str(row.active_tickers),
                           "holdings": str(row.holdings)},
            "rebalance_events": core._jsonable(rebalances.loc[rebalances["execution_date"].astype(str).eq(date)].to_dict("records")) if not rebalances.empty else [],
            "trade_events": core._jsonable(trades.loc[trades["execution_date"].astype(str).eq(date)].to_dict("records")) if not trades.empty else [],
        }
    return rows


def _replay(lanes, securities, sessions, opens, closes, end):
    rebuilt = {}
    for selector, decisions in sorted(lanes.items()):
        _require(bool(decisions), "price evidence predates all realized decisions")
        _, rebalances, trades, path = core.replay_lane_path(decisions, sessions=sessions,
            valuation_closes=closes, execution_opens=opens, valuation_end_date=end)
        rebuilt[selector] = _economic_rows(path, rebalances, trades)
    _, rebalances, trades, path = core.replay_original8_control_path(
        lanes["strict_technology__return__v1"], frozen_securities=securities, sessions=sessions,
        valuation_closes=closes, execution_opens=opens, valuation_end_date=end)
    rebuilt[CONTROL] = _economic_rows(path, rebalances, trades)
    return rebuilt


def verify_daily_economic_replay(run_manifest, *, repository_root):
    """Rebuild final-to-realized decisions and every current/historical lane row."""
    root = Path(repository_root).resolve()
    reads = _ReadSet()
    for source in (Path(__file__), Path(core.__file__), Path(calendar.__file__)):
        reads.read(source)
    calendar_path = root / calendar.CALENDAR_RELATIVE
    reads.read(calendar_path)
    calendar_manifest, calendar_proof, sessions = calendar.load_reviewed_calendar_projection(calendar_path, repository_root=root)
    calendar_events = core.canonical_sha256(list(calendar_proof.events))
    reads.read(Path(calendar_manifest["artifacts"]["event_ledger"]["path"]))
    end = acceptance.decision_date(run_manifest["latest_observed_session"])
    sessions = sessions.loc[pd.to_datetime(sessions["session_date"]).le(pd.Timestamp(end))].copy()
    _require(not sessions.empty and sessions.iloc[-1]["session_date"].date().isoformat() == end, "run end is not sealed session")
    securities, original_hash = _verified_original(root, reads)
    lanes, receipts = _realized_lanes(root, sessions, reads, original_hash)
    if not receipts:
        _require(run_manifest["independent_lane_count"] == 0, "paths exist without realized decisions")
        reads.check()
        return {"economic_replay_verified": True, "economic_lane_count": 0, "verified_rows": 0, "price_evidence_count": 0}
    _require(run_manifest["independent_lane_count"] == 10, "run does not declare ten lanes")
    records = {}
    for selector in sorted(SELECTORS | {CONTROL}):
        path = root / DAILY_ROOT / ("benchmark_controls/original_8_incumbent_v0.jsonl" if selector == CONTROL else f"lane_paths/{selector}.jsonl")
        reads.read(path)
        records[selector] = core.load_lane_path_ledger(path, selector)
        _require(bool(records[selector]), "empty economic ledger")
    current_path = root / DAILY_ROOT / "nominal_price_evidence" / end / "manifest.json"
    descriptor = run_manifest["research_artifacts"]["nominal_price_evidence_manifest"]
    _require(Path(descriptor["path"]).resolve() == current_path.resolve(), "current nominal descriptor path changed")
    opens, closes, _ = _nominal(current_path, root, sessions, _tickers(lanes, securities), reads)
    _require(descriptor["sha256"] == reads.files[current_path.resolve()], "current nominal descriptor hash changed")
    rebuilt = _replay(lanes, securities, sessions, opens, closes, end)
    for selector, values in records.items():
        _require([r["date"] for r in values] == list(rebuilt[selector]), f"economic dates differ: {selector}")
        for record in values:
            actual = {key: record[key] for key in ("path_state", "rebalance_events", "trade_events")}
            _require(_same(actual, rebuilt[selector][record["date"]]), f"economic path differs: {selector}/{record['date']}")

    required_hashes = {record["price_evidence_sha256"] for values in records.values() for record in values}
    evidence_paths = {}
    for directory in reads.children(root / DAILY_ROOT / "nominal_price_evidence"):
        if directory.is_dir() and not directory.name.startswith("."):
            path = directory / "manifest.json"
            if path.is_file():
                raw = reads.read(path)
                digest = hashlib.sha256(raw).hexdigest()
                _require(digest not in evidence_paths, "duplicate evidence hash coordinate")
                evidence_paths[digest] = path
    _require(required_hashes <= set(evidence_paths), "historical price evidence hash is unbound")
    for digest in sorted(required_hashes):
        path = evidence_paths[digest]
        historical_end = acceptance.decision_date(path.parent.name)
        _require(historical_end <= end, "future price evidence")
        historical_lanes = {selector: [d for d in values if d["timing"]["execution_date"] <= historical_end]
                            for selector, values in lanes.items()}
        historical_opens, historical_closes, _ = _nominal(path, root, sessions,
            _tickers(historical_lanes, securities), reads)
        historical = _replay(historical_lanes, securities, sessions, historical_opens, historical_closes, historical_end)
        for selector, values in records.items():
            for record in values:
                if record["price_evidence_sha256"] != digest:
                    continue
                date = record["date"]
                _require(date in historical[selector], "record is outside bound historical price grid")
                actual = {key: record[key] for key in ("path_state", "rebalance_events", "trade_events")}
                _require(_same(actual, historical[selector][date]), f"historical evidence economics differ: {selector}/{date}")
    for decision, receipt in receipts.items():
        repeated = acceptance.verify_acceptance(root / acceptance.ACCEPTANCE / decision / "receipt.json")
        _require(_same(receipt, repeated), "acceptance changed during replay")
    repeated_calendar, repeated_proof, _ = calendar.load_reviewed_calendar_projection(calendar_path, repository_root=root)
    _require(_same(repeated_calendar, calendar_manifest)
             and core.canonical_sha256(list(repeated_proof.events)) == calendar_events,
             "calendar evidence changed during replay")
    _require(_verified_original(root, reads)[1] == original_hash, "original-8 changed during replay")
    reads.check()
    return {"economic_replay_verified": True, "economic_lane_count": 11,
            "verified_rows": sum(len(values) for values in records.values()),
            "price_evidence_count": len(required_hashes)}
