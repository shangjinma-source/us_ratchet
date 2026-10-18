"""Same-source four-security fixture; real original8 dependency manifests are read-only."""
from argparse import Namespace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

import test_ndx_dynamic_shadow_candidate_generator_v3 as raw_fixture
import test_ndx_dynamic_shadow_candidate_v3_public_verify as public_fixture
import test_ndx_observed_session_calendar_v2 as calendar_fixture
from backtest import ndx_dynamic_shadow_candidate_calendar_v2 as calendar
from backtest import ndx_dynamic_shadow_candidate_generator_v3 as provenance
from backtest import ndx_dynamic_shadow_fresh_search as search
from backtest import ndx_dynamic_shadow_fresh_search_v2 as controller_core
from backtest.ndx_dynamic_shadow_candidate_membership_v3 import build_runtime_official_eligible_membership_v3
from backtest.ndx_dynamic_shadow_candidate_snapshot import build_fresh_candidate_input_snapshot, write_snapshot_bundle
from backtest.ndx_observed_session_calendar_v2 import write_canonical_reviewed_calendar_v2
from data.ndx_history import constituents_asof
from data.ndx_security_identity import load_security_lifecycle
from scripts import ndx_dynamic_shadow_candidate_generator as generator
from scripts import ndx_dynamic_shadow_fresh_search as leaf
from scripts import ndx_dynamic_shadow_fresh_search_v2 as controller
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance

REAL_ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = Path("data/cache/research/ndx_original_8_control_v1/manifest.json")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def write_frame(path, frame):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frame.to_csv(index=False, lineterminator="\n"), encoding="utf-8")


def prepare(root, *, leading_zero_cusips=False):
    helper = calendar_fixture.NdxObservedSessionCalendarV2Tests()
    calendar_sources = helper._canonical_repository(root, ["2026-09-30", "2026-10-01"])
    snapshot_path, partial = raw_fixture._fixture(root)
    # Keep the fixture identity contract and tabular source documents, but execute
    # and hash actual source bytes. The search contract is the unmodified formal one.
    copies = set(acceptance.CODE_FILES) | {
        str(path) for key, path in provenance.STATIC_SOURCE_PATHS.items()
        if key != "candidate_generator_v3_contract_sha256"
    } | {"config/ndx_dynamic_shadow_candidate_generator_v1.yaml", "config/ndx_dynamic_shadow_search_budget_v1.yaml",
         "backtest/ndx_dynamic_shadow_candidate_snapshot.py",
         str(calendar.ENGINE_RELATIVE), str(calendar.CALENDAR_SCRIPT_RELATIVE), str(calendar.ADAPTER_RELATIVE)}
    for relative in copies:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REAL_ROOT / relative).read_bytes())
    observed = helper._snapshot(calendar_sources, start_date="2026-09-30", observed_at="2026-10-02T01:00:00+00:00")
    write_canonical_reviewed_calendar_v2(repository_root=root, snapshot=observed,
        calendar_start_date="2026-09-30", prospective_start_date=calendar_fixture.PROSPECTIVE_START,
        initialize_reviewed_v1=True)
    _, calendar_versions, calendar_paths = calendar.capture_candidate_calendar_evidence_v2(
        root / calendar.CALENDAR_RELATIVE, decision_date="2026-10-01", repository_root=root)
    paths = partial["source_paths"]
    taxonomy_path = Path(paths["taxonomy_records_sha256"])
    taxonomy = pd.read_csv(taxonomy_path)
    for index, ticker in enumerate(("O000", "O001", "O002")):
        cusip = f"{index + 2:09d}" if leading_zero_cusips else str(100000002 + index)
        taxonomy.loc[len(taxonomy)] = dict(ticker=ticker, cik=f"{index + 101:010d}",
            cusip=cusip, security_id=f"security:{index + 101:010d}:{cusip}",
            issuer_id=f"issuer:{index + 101:010d}", risk_chain="eda_ip" if index < 2 else "semiconductor",
            status="accepted", evidence_available_date="2026-01-01", selection_date_end="2026-05-29")
    write_frame(taxonomy_path, taxonomy)
    taxonomy_manifest_path = Path(paths["taxonomy_manifest_sha256"])
    taxonomy_manifest = json.loads(taxonomy_manifest_path.read_bytes())
    membership_path = Path(paths["membership_history_sha256"])
    crosswalk_path = Path(paths["cik_crosswalk_sha256"])
    membership = pd.read_csv(membership_path, dtype=str)
    crosswalk = pd.read_csv(crosswalk_path, dtype=str)
    for index, ticker in enumerate(("O000", "O001", "O002")):
        cusip = f"{index + 2:09d}" if leading_zero_cusips else str(100000002 + index)
        membership.loc[membership.ticker == ticker, "cusip"] = cusip
        crosswalk.loc[crosswalk.ticker == ticker, "cusips"] = cusip
    for frame, source_key, manifest_key, source_name in (
        (membership, "membership_history_sha256", "membership_manifest_sha256", "ndx_point_in_time_constituents"),
        (crosswalk, "cik_crosswalk_sha256", "cik_crosswalk_manifest_sha256", "ndx_sec_cik_crosswalk"),
    ):
        source_path = Path(paths[source_key])
        metadata_path = Path(paths[manifest_key])
        write_frame(source_path, frame)
        metadata = json.loads(metadata_path.read_bytes())
        metadata["content_sha256"] = acceptance.digest(source_path)
        write_json(metadata_path, metadata)
        item = next(item for item in taxonomy_manifest["input_versions"] if item["source_name"] == source_name)
        item.update(content_sha256=acceptance.digest(source_path), manifest_sha256=acceptance.digest(metadata_path))
    identity_contract_path = root / provenance.CONTRACT_RELATIVE
    identity_contract = yaml.safe_load(identity_contract_path.read_text(encoding="utf-8"))
    identity_contract["identity_contract"]["frozen_sec_cik_crosswalk_sha256"] = acceptance.digest(crosswalk_path)
    identity_contract_path.write_text(yaml.safe_dump(identity_contract), encoding="utf-8")
    taxonomy_manifest["artifacts"]["records"].update(rows=4, sha256=acceptance.digest(taxonomy_path))
    write_json(taxonomy_manifest_path, taxonomy_manifest)
    plan_path = Path(paths["search_plan_sha256"])
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    plan["universe_tracks"]["strict_technology"]["accepted_risk_chains"] = ["semiconductor", "eda_ip"]
    plan_path.write_text(yaml.safe_dump(plan), encoding="utf-8")
    membership = pd.read_csv(paths["membership_history_sha256"], dtype=str)
    nport, nport_evidence = constituents_asof(membership, "2026-10-01")
    eligible, identity = build_runtime_official_eligible_membership_v3(
        pd.read_csv(paths["official_snapshot_sha256"]), nport, taxonomy, plan,
        load_security_lifecycle(paths["security_lifecycle_sha256"]),
        decision_date="2026-10-01", observed_at_utc="2026-10-01T20:05:00+00:00",
        decision_close_timestamp_utc=partial["decision_close_timestamp_utc"],
        seal_timestamp_utc=partial["seal_timestamp_utc"],
        conservative_seal_deadline_utc=partial["conservative_seal_deadline_utc"],
        allow_degraded_reviewed_taxonomy_subset=True)
    assert set(eligible.ticker) == {"NEW", "O000", "O001", "O002"}
    partial["membership_evidence"].update(official_runtime=identity, nport=nport_evidence)
    versions = {key: acceptance.digest(path) for key, path in paths.items()}
    versions.update(calendar_versions)
    paths.update(calendar_paths)
    # This is intentionally not a self-contained original8 fixture. Bind/check
    # the three real immutable dependencies; never copy the historical data tree.
    original_path = root / ORIGINAL
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes((REAL_ROOT / ORIGINAL).read_bytes())
    original = json.loads(original_path.read_bytes())
    dependency_paths = [Path(original["inputs"][name]["path"]) for name in ("dynamic_walkforward_manifest", "identity_manifest")]
    identity_manifest = json.loads(dependency_paths[1].read_bytes())
    projection = Path(identity_manifest["artifacts"]["projection"]["path"])
    if not projection.is_absolute():
        destination = root / projection
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REAL_ROOT / projection).read_bytes())
        projection = REAL_ROOT / projection
    dependency_paths.append(projection)
    watched = {path: acceptance.digest(path) for path in dependency_paths}
    for relative in ("config/config.yaml", "data/state.json", "data/broker_positions.json"):
        watched[REAL_ROOT / relative] = acceptance.digest(REAL_ROOT / relative)
    controls, _, original_hash = search.load_frozen_original_8_definition(original_path)
    versions["frozen_original8_manifest_sha256"] = original_hash
    paths["frozen_original8_manifest_sha256"] = original_path.as_posix()
    versions["frozen_original8_verifier_sha256"] = acceptance.digest(root / "backtest/ndx_dynamic_shadow_fresh_search.py")
    paths["frozen_original8_verifier_sha256"] = (root / "backtest/ndx_dynamic_shadow_fresh_search.py").as_posix()
    dates = pd.bdate_range(end="2026-10-01", periods=300)
    nominal_frames = {}
    for number, ticker in enumerate(sorted(set(eligible.ticker) | set(controls))):
        # Similar stable price scales leave a real diversified k=4 feasible under
        # the unchanged .45/.80/.55 constraints, without injecting search results.
        close = 95 + np.arange(300) * .015 + .1 * np.sin(np.arange(300) / (8 + number))
        frame = pd.DataFrame(dict(Date=dates.strftime("%Y-%m-%d"), Open=close,
            High=close + 1, Low=close - 1, Close=close, Volume=2_000_000.0))
        nominal_frames[ticker] = frame
        if ticker in set(eligible.ticker):
            price_path = snapshot_path.parent / "nominal_sources" / f"{ticker}.csv"
            write_frame(price_path, frame)
            sidecar = dict(schema_version=1, manifest_type="ndx_dynamic_shadow_frozen_nominal_input",
                ticker=ticker, decision_date="2026-10-01", price_basis="UNADJUSTED_NOMINAL_TRADE_PRICE",
                corporate_action_adjustment="none", source_mode="eastmoney_fqt_0", source_errors_before_success={},
                data_start=dates[0].date().isoformat(), data_end="2026-10-01", rows=300,
                content_sha256=acceptance.digest(price_path), rows_after_decision_date_included=False,
                historical_backfill_allowed=False, promotion_allowed=False, live_mutation=False)
            sidecar_path = price_path.with_suffix(".csv.manifest.json")
            write_json(sidecar_path, sidecar)
            for key, source_path in ((f"nominal_price_{ticker}_sha256", price_path),
                    (f"nominal_price_{ticker}_manifest_sha256", sidecar_path)):
                versions[key] = acceptance.digest(source_path)
                paths[key] = source_path.as_posix()
    partial["source_versions"] = versions
    partial["membership_evidence"]["candidate_v3_source_capture"].update(
        source_versions={key: versions[key] for key in sorted(provenance.CAPTURE_SOURCE_KEYS)},
        source_paths={key: paths[key] for key in sorted(provenance.CAPTURE_SOURCE_KEYS)})
    _, _, liquidity = provenance.capture_nominal_liquidity_inputs_v3(eligible, versions, paths,
        decision_date="2026-10-01", snapshot_directory=snapshot_path.parent)
    partial["membership_evidence"]["candidate_v3_nominal_liquidity_capture"] = liquidity
    raw_fixture._attach_source_archive(snapshot_path, partial)
    snapshot = build_fresh_candidate_input_snapshot(eligible,
        {ticker: frame[["Date", "Close"]] for ticker, frame in nominal_frames.items()}, nominal_frames,
        pd.DataFrame(dict(Date=dates, Close=1 + np.arange(300) * .0001)),
        decision_date="2026-10-01", decision_close_timestamp_utc=partial["decision_close_timestamp_utc"],
        seal_timestamp_utc=partial["seal_timestamp_utc"], conservative_seal_deadline_utc=partial["conservative_seal_deadline_utc"],
        source_versions=versions, source_paths=paths, frozen_original8_tickers=controls)
    snapshot["membership_evidence"] = partial["membership_evidence"]
    for name in ("manifest.json", "eligible_securities.csv", "liquidity_exclusions.csv"):
        (snapshot_path.parent / name).unlink()
    snapshot = write_snapshot_bundle(snapshot_path.parent, snapshot)
    generator._append_decision_seal(root / acceptance.INPUT / "decision_seals.jsonl", snapshot_path, snapshot,
                                  expected_root=root / acceptance.INPUT)
    return snapshot_path, watched


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, 1, 20, 15, tzinfo=timezone.utc)
        return value if tz is None else value.astimezone(tz)


def bindings(stack, root, calls):
    public_fixture._temporary_public_paths(stack, root)
    for module in (leaf, controller, controller_core, acceptance):
        stack.enter_context(patch.object(module, "ROOT", root))
    for module, values in (
        (leaf, dict(CANONICAL_SNAPSHOT_ROOT=root / acceptance.INPUT, CANONICAL_OUTPUT_ROOT=root / acceptance.SEARCH,
                    CANONICAL_CONTRACT=root / "config/ndx_dynamic_shadow_fresh_search_v1.yaml",
                    CANONICAL_ORIGINAL8=root / ORIGINAL, ROLE_SEAL_LEDGER=root / acceptance.SEARCH / "role_seals.jsonl",
                    __file__=str(root / "scripts/ndx_dynamic_shadow_fresh_search.py"),
                    PROTECTED=tuple(root / relative for relative in ("config/config.yaml", "data/state.json", "data/broker_positions.json")))),
        (controller, dict(OUTPUT_ROOT=root / acceptance.SEARCH,
                         CONTROL_ROOT=root / "data/cache/research/ndx_dynamic_shadow_fresh_search_v2_controller", ORIGINAL8=root / ORIGINAL)),
        (controller_core, dict(SNAPSHOT_ROOT=root / acceptance.INPUT, OUTPUT_ROOT=root / acceptance.SEARCH,
                              CONTROLLER_ROOT=root / "data/cache/research/ndx_dynamic_shadow_fresh_search_v2_controller", ORIGINAL8=root / ORIGINAL)),
    ):
        for name, value in values.items():
            stack.enter_context(patch.object(module, name, value))
    for module in (leaf, controller, search):
        stack.enter_context(patch.object(module, "datetime", FixedClock))

    def bridge(command, *, timeout_seconds):
        expected = [str(root / "scripts/ndx_dynamic_shadow_fresh_search.py"),
                    "--execute", "--resume", "--max-jobs", "1", "--snapshot-manifest"]
        assert len(command) == 9 and command[:2] == [sys.executable, "-B"]
        assert command[2:8] == expected and timeout_seconds > 0
        assert Path(command[8]).resolve() == (root / acceptance.INPUT / "2026-10-01/manifest.json").resolve()
        calls.append(command)
        leaf.execute(Namespace(snapshot_manifest=command[8], contract=str(leaf.CANONICAL_CONTRACT),
            output_root=str(leaf.CANONICAL_OUTPUT_ROOT), original_8_manifest=str(leaf.CANONICAL_ORIGINAL8),
            resume=True, max_jobs=1))
        return 0
    stack.enter_context(patch.object(controller, "run_process_tree", side_effect=bridge))
