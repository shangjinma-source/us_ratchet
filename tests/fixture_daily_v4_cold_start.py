"""Raw source material for cold-start tests; never imports sealed run artifacts.

The donor fixture is used only as a synthetic raw-market source factory. Its
candidate outputs, calendar evidence, seal ledgers and nominal snapshot outputs
are not copied into the cold runtime. Taxonomy is rebuilt by the real CLI.
"""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
import yaml

import fixture_fresh_search_v4_e2e as source_fixture
from scripts import ndx_taxonomy_v2 as taxonomy


def prepare_raw_sources(root):
    root = Path(root).resolve()
    # Only raw upstream namespaces cross the donor boundary.
    with TemporaryDirectory() as directory:
        donor = Path(directory).resolve()
        snapshot, watched = source_fixture.prepare(donor)
        payload = json.loads(snapshot.read_bytes())
        raw_keys = ("membership_history_sha256", "membership_manifest_sha256",
                    "cik_crosswalk_sha256", "cik_crosswalk_manifest_sha256",
                    "official_snapshot_sha256", "official_snapshot_manifest_sha256",
                    "security_lifecycle_sha256", "search_plan_sha256")
        paths = {}
        for key in raw_keys:
            source = Path(payload["source_paths"][key])
            destination = root / source.relative_to(donor)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            paths[key] = destination
        contract = root / source_fixture.provenance.CONTRACT_RELATIVE
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_bytes((donor / source_fixture.provenance.CONTRACT_RELATIVE).read_bytes())
        original = root / source_fixture.ORIGINAL
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes((donor / source_fixture.ORIGINAL).read_bytes())
    official_metadata = json.loads(paths["official_snapshot_manifest_sha256"].read_bytes())
    official_metadata["cache_path"] = paths["official_snapshot_sha256"].as_posix()
    official_metadata["manifest_path"] = paths["official_snapshot_manifest_sha256"].as_posix()
    paths["official_snapshot_manifest_sha256"].write_text(json.dumps(official_metadata), encoding="utf-8")
    # Unlike the old hand-built taxonomy fixture, the raw source identity must
    # agree with the reviewed OLD->NEW lifecycle before real taxonomy rebuild.
    for data_key, manifest_key, column in (
            ("membership_history_sha256", "membership_manifest_sha256", "cusip"),
            ("cik_crosswalk_sha256", "cik_crosswalk_manifest_sha256", "cusips")):
        frame = pd.read_csv(paths[data_key], dtype=str, keep_default_na=False)
        frame.loc[frame.ticker.eq("NEW"), column] = "123456789"
        paths[data_key].write_text(frame.to_csv(index=False, lineterminator="\n"), encoding="utf-8")
        metadata = json.loads(paths[manifest_key].read_bytes())
        metadata["content_sha256"] = source_fixture.acceptance.digest(paths[data_key])
        paths[manifest_key].write_text(json.dumps(metadata), encoding="utf-8")
    identity_contract = yaml.safe_load(contract.read_text(encoding="utf-8"))
    identity_contract["identity_contract"]["frozen_sec_cik_crosswalk_sha256"] = source_fixture.acceptance.digest(paths["cik_crosswalk_sha256"])
    contract.write_text(yaml.safe_dump(identity_contract), encoding="utf-8")
    copies = set(source_fixture.acceptance.CODE_FILES) | {
        str(path) for key, path in source_fixture.provenance.STATIC_SOURCE_PATHS.items()
        if key != "candidate_generator_v3_contract_sha256"
    } | {"config/ndx_dynamic_shadow_candidate_generator_v1.yaml",
         "config/ndx_dynamic_shadow_search_budget_v1.yaml", "config/candidate_taxonomy_v2.yaml",
         "scripts/ndx_taxonomy_v2.py", "backtest/ndx_dynamic_shadow_candidate_snapshot.py"}
    for relative in copies:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((source_fixture.REAL_ROOT / relative).read_bytes())
    cfg = yaml.safe_load((source_fixture.REAL_ROOT / "config/config.yaml").read_text(encoding="utf-8"))
    cfg["data"]["cache_dir"] = (root / "data/cache").as_posix()
    (root / "config/config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    evidence_path = root / "data/cache/candidate_pools/cold_test_reviewed_evidence.csv"
    rows = []
    plan_path = paths["search_plan_sha256"]
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    plan["universe_tracks"]["strict_technology"]["accepted_risk_chains"] = ["ai_accelerator", "eda_ip"]
    plan["universe_tracks"]["technology_plus_adjacent"]["accepted_risk_chains"] = ["ai_accelerator", "eda_ip"]
    plan_path.write_text(yaml.safe_dump(plan), encoding="utf-8")
    for ticker, chain in (("NEW", "ai_accelerator"), ("O000", "eda_ip"),
                          ("O001", "eda_ip"), ("O002", "ai_accelerator")):
        rows.append(dict(ticker=ticker, risk_chain=chain, effective_from="2026-01-01",
            evidence_source_type="sec_filing_business_description", evidence_source="SYNTHETIC TEST SOURCE",
            evidence_locator="https://www.sec.gov/Archives/edgar/data/test", evidence_available_date="2026-01-01",
            evidence_excerpt="Synthetic reviewed fixture business classification, not market research.",
            confidence="high", status="accepted"))
    evidence_path.write_text(pd.DataFrame(rows).to_csv(index=False), encoding="utf-8")
    assert not (root / source_fixture.acceptance.INPUT).exists()
    assert not (root / source_fixture.acceptance.SEARCH).exists()
    assert not (root / source_fixture.acceptance.ACCEPTANCE).exists()
    return paths, evidence_path, watched


def run_taxonomy(root, evidence_path):
    output = StringIO()
    command = [str(root / "scripts/ndx_taxonomy_v2.py"), "--plan-only", "--evidence-csv", str(evidence_path)]
    with patch.object(taxonomy, "ROOT", root), patch("sys.argv", command), redirect_stdout(output), redirect_stderr(output):
        code = taxonomy.main()
    if code:
        raise AssertionError(output.getvalue())
    manifest_path = root / "data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json"
    return json.loads(manifest_path.read_bytes())
