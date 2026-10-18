"""Recover an accidentally empty SEC checkpoint from verified review artifacts.

This is a one-purpose provenance repair utility.  It only reconstructs rows
for raw files whose review-pack document index and adjacent raw-file Manifest
are present and hash-consistent; it never downloads or classifies anything.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.ndx_taxonomy import read_versioned_csv
from data.versioning import file_sha256, manifest_path, write_dataset_manifest


CHECKPOINT_COLUMNS = [
    "job_id", "issuer_id", "cik", "accession_number", "status", "index_url",
    "document_url", "raw_path", "content_bytes", "content_sha256", "attempted_at", "error",
]


def _resolve(path: str | Path) -> Path:
    target = Path(path)
    return target if target.is_absolute() else ROOT / target


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="从已校验 SEC 复核包恢复空的 fetch_attempts 检查点")
    parser.add_argument("--review-dir", default="data/cache/candidate_pools/ndx_taxonomy_v2/review_pack")
    parser.add_argument("--plan", default="data/cache/candidate_pools/ndx_taxonomy_v2/evidence_plan.csv")
    parser.add_argument("--output", default="data/cache/candidate_pools/ndx_taxonomy_v2/fetch_attempts.csv")
    parser.add_argument("--allow-nonempty", action="store_true")
    args = parser.parse_args()
    review_dir = _resolve(args.review_dir)
    output = _resolve(args.output)
    if output.exists() and output.stat().st_size > 256 and not args.allow_nonempty:
        print(f"拒绝覆盖非空检查点: {output}", file=sys.stderr)
        return 1
    try:
        documents, _ = read_versioned_csv(
            review_dir / "sec_review_documents.csv",
            name="ndx_taxonomy_v2_review_documents",
            used_for="恢复 SEC 检查点",
        )
        plan, _ = read_versioned_csv(
            _resolve(args.plan),
            name="ndx_taxonomy_v2_evidence_plan",
            used_for="恢复 SEC 目录地址",
        )
        plan_index = plan.drop_duplicates("job_id", keep="first").set_index("job_id", drop=False)
        rows = []
        for row in documents.itertuples(index=False):
            raw_path = Path(str(row.raw_path))
            raw_manifest = Path(str(row.raw_manifest_path))
            if not raw_path.exists() or not raw_manifest.exists():
                raise ValueError(f"raw file or Manifest missing: {raw_path}")
            actual_sha = file_sha256(raw_path)
            if actual_sha != str(row.raw_sha256):
                raise ValueError(f"raw file hash mismatch: {raw_path}")
            if str(row.job_id) not in plan_index.index:
                raise ValueError(f"review document missing from plan: {row.job_id}")
            plan_row = plan_index.loc[str(row.job_id)]
            rows.append({
                "job_id": str(row.job_id),
                "issuer_id": str(row.issuer_id),
                "cik": str(row.cik),
                "accession_number": str(row.accession_number),
                "status": "fetched",
                "index_url": str(plan_row.get("sec_index_url") or ""),
                "document_url": str(row.document_url),
                "raw_path": raw_path.as_posix(),
                "content_bytes": raw_path.stat().st_size,
                "content_sha256": actual_sha,
                "attempted_at": "",
                "error": "",
            })
        frame = pd.DataFrame(rows, columns=CHECKPOINT_COLUMNS).drop_duplicates("job_id")
        _atomic_csv(frame, output)
        manifest = write_dataset_manifest(
            output,
            dataset_type="ndx_taxonomy_v2_sec_fetch_checkpoint",
            dataset_key="qqq_nport_public_filings_recovered",
            source="reconstructed_from_manifest_verified_review_documents",
            fetched_at_evidence="raw_file_and_review_manifest_hash_verified",
            row_count=len(frame),
            extra={
                "research_only": True,
                "reconstructed": True,
                "classification_automatic": False,
                "raw_file_hashes_verified": True,
            },
        )
        print(f"SEC检查点恢复完成 | fetched={len(frame)} | sha256={manifest['content_sha256']}")
        print(f"输出: {output}")
        return 0
    except Exception as exc:
        print(f"SEC检查点恢复 fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
