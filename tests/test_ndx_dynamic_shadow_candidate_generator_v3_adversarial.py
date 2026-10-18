from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from backtest.ndx_dynamic_shadow_candidate_generator_v3 import (
    NdxDynamicShadowCandidateGeneratorV3Error,
    verify_candidate_generator_v3_provenance,
)
from data.versioning import file_sha256
import test_ndx_dynamic_shadow_candidate_generator_v3 as owner


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.write_text(
        frame.to_csv(index=False, lineterminator="\n"),
        encoding="utf-8",
        newline="\n",
    )


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _replace_source_hash(manifest: dict, key: str, path: Path) -> str:
    digest = file_sha256(path)
    manifest["source_versions"][key] = digest
    manifest["membership_evidence"]["candidate_v3_source_capture"][
        "source_versions"
    ][key] = digest
    return digest


class DynamicShadowCandidateGeneratorV3AdversarialTests(unittest.TestCase):
    def _resign_archive_after_binding_rejection(
        self, manifest_path: Path, manifest: dict, root: Path,
    ) -> None:
        # First prove the unchanged archive detects source-registry tampering.
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateGeneratorV3Error,
            "source archive entry binding changed",
        ):
            verify_candidate_generator_v3_provenance(
                manifest_path, manifest, repository_root=root
            )
        # Then give the attacker a self-consistent replacement archive too.
        # The caller must still reach and fail the deeper semantic check.
        owner._attach_source_archive(manifest_path, manifest)

    def test_resigned_non_nasdaq_official_source_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = owner._fixture(root)
            archive = Path(manifest["source_paths"]["official_snapshot_sha256"])
            sidecar_path = Path(
                manifest["source_paths"]["official_snapshot_manifest_sha256"]
            )
            frame = pd.read_csv(archive, low_memory=False)
            frame["source_locator"] = "https://evil.example/fabricated"
            _write_csv(archive, frame)
            archive_hash = file_sha256(archive)
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar.update({
                "content_sha256": archive_hash,
                "content_bytes": len(archive.read_bytes()),
                "dataset_key": f"nasdaq_100:2026-10-01:{archive_hash[:12]}",
                "source_locator": "https://evil.example/fabricated",
                "version_id": (
                    "security_pool_snapshot:nasdaq_100:2026-10-01:"
                    f"{archive_hash[:12]}:{archive_hash[:16]}"
                ),
            })
            _write_json(sidecar_path, sidecar)
            manifest["source_versions"]["official_snapshot_sha256"] = archive_hash
            manifest["membership_evidence"]["candidate_v3_source_capture"][
                "source_versions"
            ]["official_snapshot_sha256"] = archive_hash
            _replace_source_hash(
                manifest, "official_snapshot_manifest_sha256", sidecar_path
            )
            self._resign_archive_after_binding_rejection(manifest_path, manifest, root)

            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "Nasdaq source contract|authority",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root
                )

    def test_resigned_false_liquidity_exclusion_is_recomputed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = owner._fixture(root)
            eligible_item = manifest["artifacts"]["eligible_securities"]
            eligible_path = manifest_path.parent / eligible_item["filename"]
            eligible = pd.read_csv(eligible_path, low_memory=False)
            empty = eligible.iloc[0:0].copy()
            _write_csv(eligible_path, empty)
            eligible_item.update({
                "rows": 0,
                "sha256": file_sha256(eligible_path),
            })

            exclusion_item = manifest["artifacts"]["liquidity_exclusions"]
            exclusion_path = manifest_path.parent / exclusion_item["filename"]
            exclusions = pd.DataFrame([{
                "ticker": "NEW",
                "median_dollar_volume_usd": 1.0,
                "liquidity_lookback_rows": 63,
                "nominal_consumed_max_date": "2026-10-01",
                "exclusion_reason": (
                    "MEDIAN_DOLLAR_VOLUME_BELOW_PREREGISTERED_MINIMUM"
                ),
                "minimum_median_dollar_volume_usd": 50_000_000.0,
            }])
            _write_csv(exclusion_path, exclusions)
            exclusion_item.update({
                "rows": 1,
                "sha256": file_sha256(exclusion_path),
            })
            liquidity = deepcopy(
                manifest["membership_evidence"][
                    "candidate_v3_nominal_liquidity_capture"
                ]
            )
            liquidity["computed_excluded_tickers"] = ["NEW"]
            for track in (
                "strict_technology",
                "technology_plus_adjacent",
            ):
                liquidity["track_post_liquidity_cardinality"][track] = {
                    "eligible_security_count": 0,
                    "eligible_unique_issuer_count": 0,
                    "dynamic_k_minimum": 1,
                    "dynamic_k_maximum": 0,
                }
            manifest["membership_evidence"][
                "candidate_v3_nominal_liquidity_capture"
            ] = liquidity

            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "nominal liquidity capture cannot be rebuilt|"
                "liquidity exclusions cannot be recomputed",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root
                )

    def test_resigned_fabricated_identity_issue_is_rebuilt(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = owner._fixture(root)
            issues_path = Path(
                manifest["source_paths"]["taxonomy_identity_issues_sha256"]
            )
            issues = pd.DataFrame([{
                "issue_type": "identity",
                "security_id": "security:0000000001:123456789",
                "issuer_id": "issuer:0000000001",
                "ticker": "NEW",
                "cik": "0000000001",
                "cusip": "123456789",
                "report_date": "2026-06-30",
                "detail": "fabricated_identity_issue",
            }])
            _write_csv(issues_path, issues)
            issue_hash = _replace_source_hash(
                manifest, "taxonomy_identity_issues_sha256", issues_path
            )
            taxonomy_manifest_path = Path(
                manifest["source_paths"]["taxonomy_manifest_sha256"]
            )
            taxonomy_manifest = json.loads(
                taxonomy_manifest_path.read_text(encoding="utf-8")
            )
            taxonomy_manifest["artifacts"]["identity_issues"].update({
                "rows": 1,
                "sha256": issue_hash,
            })
            taxonomy_manifest["summary"]["identity_issue_count"] = 1
            _write_json(taxonomy_manifest_path, taxonomy_manifest)
            _replace_source_hash(
                manifest, "taxonomy_manifest_sha256", taxonomy_manifest_path
            )
            self._resign_archive_after_binding_rejection(manifest_path, manifest, root)

            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "identity issues cannot be rebuilt",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root
                )

    def test_adjusted_nominal_source_cannot_be_resigned_as_execution_input(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = owner._fixture(root)
            sidecar_path = Path(
                manifest["source_paths"]["nominal_price_NEW_manifest_sha256"]
            )
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar["source_mode"] = "provider_adjusted_close"
            _write_json(sidecar_path, sidecar)
            sidecar_hash = file_sha256(sidecar_path)
            manifest["source_versions"][
                "nominal_price_NEW_manifest_sha256"
            ] = sidecar_hash
            manifest["membership_evidence"][
                "candidate_v3_nominal_liquidity_capture"
            ]["source_versions"][
                "nominal_price_NEW_manifest_sha256"
            ] = sidecar_hash
            self._resign_archive_after_binding_rejection(manifest_path, manifest, root)

            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "nominal sidecar semantics changed",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root
                )


if __name__ == "__main__":
    unittest.main()
