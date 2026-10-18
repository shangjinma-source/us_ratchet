"""Identifier-preserving research cache reader; old activated reader is frozen."""
import pandas as pd
from data import ndx_history as legacy


def read_history_cache(cfg):
    path = legacy._history_path(cfg)
    manifest = legacy._strict_manifest(path)
    frame = legacy._normalize_history(pd.read_csv(
        path, keep_default_na=False, dtype={"cusip": str},
    ))
    if len(frame) != int(manifest.get("row_count") or -1):
        raise legacy.NdxHistoryError("NDX history row count does not match manifest")
    report_count = frame["report_date"].nunique()
    if report_count != int(manifest.get("report_count") or -1):
        raise legacy.NdxHistoryError("NDX history report count does not match manifest")
    return frame, legacy.NdxHistoryMeta(source="ndx_history_cache", rows=len(frame),
        report_count=report_count, cached=True, manifest=manifest)
