"""Verify explicit report hashes against the sealed date denominator."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_dynamic_training_date import INDEX, INDEX_SHA
from scripts.ndx_equal_weight_base_report import load_report


def inspect_coverage(descriptors):
    """Descriptors are externally supplied path/SHA pairs, never inferred hashes."""
    raw = INDEX.read_bytes()
    if hashlib.sha256(raw).hexdigest() != INDEX_SHA:
        raise ValueError('Training index changed')
    expected = {(row['source_batch'], row['universe_track'], row['selection_date'])
                for row in json.loads(raw)['coordinates']}
    found = {}
    for descriptor in descriptors:
        if set(descriptor) != {'path', 'sha256'}:
            raise ValueError('Explicit path and expected SHA required')
        report = load_report(descriptor['path'], expected_sha256=descriptor['sha256'])
        coordinate = report['coordinate']
        key = tuple(coordinate[name] for name in ('source_batch', 'universe_track', 'selection_date'))
        if key not in expected or key in found:
            raise ValueError('Duplicate or unexpected date')
        found[key] = dict(**coordinate, **descriptor, count=report['evaluation']['count'],
                          cardinalities=report['input_summary']['cardinalities'])
    return dict(schema='ndx_equal_base_coverage_v1', expected_dates=len(expected),
                completed_dates=len(found), equal_weight_records=sum(row['count'] for row in found.values()),
                dates=[found[key] for key in sorted(found)],
                missing_dates=[dict(zip(('source_batch', 'universe_track', 'selection_date'), key))
                               for key in sorted(expected - set(found))],
                all_equal_dates_verified=set(found) == expected,
                non_equal_coverage_verified=False, whole_lot_status='NOT_EVALUATED',
                full_portfolio_optimization_complete=False, promotion_allowed=False)
