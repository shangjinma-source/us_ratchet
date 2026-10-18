"""Canonical session/header validation without changing frozen v1 evidence."""
import csv
import hashlib
import io
from pathlib import Path

import pandas as pd
from backtest import ndx_dynamic_nav_research as legacy

_SOURCES = {str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in (__file__, legacy.__file__)}


def load_nav_v2(*, csv_path, manifest_path, expected_csv_sha256,
                expected_manifest_sha256, calendar):
    if (not isinstance(calendar, pd.DatetimeIndex) or calendar.hasnans
            or calendar.tz is not None or not calendar.equals(calendar.normalize())):
        raise ValueError('Canonical timezone-naive midnight sessions required')
    raw = csv_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_csv_sha256:
        raise ValueError('NAV CSV identity differs')
    rows = csv.reader(io.StringIO(raw.decode('utf-8-sig')))
    header = next(rows, [])
    if not header or len(header) != len(set(header)) or not all(header):
        raise ValueError('Unique nonempty NAV columns required')
    if any(len(row) != len(header) for row in rows):
        raise ValueError('NAV row width differs')
    result = legacy.load_nav(csv_path=csv_path, manifest_path=manifest_path,
        expected_csv_sha256=expected_csv_sha256,
        expected_manifest_sha256=expected_manifest_sha256, calendar=calendar)
    for path, digest in _SOURCES.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('NAV source drift')
    result['source_hashes'].update(_SOURCES)
    result['schema'] = 'ndx_dynamic_nav_research_v2'
    result['maximum_nav_age_calendar_days'] = max(
        (pd.Timestamp(row['session'])-pd.Timestamp(row['nav_date'])).days for row in result['rows'])
    return result
