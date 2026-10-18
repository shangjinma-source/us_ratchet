"""Draft comparison with an immutable NAV snapshot; never replay stock paths.

The old NAV report remains historical evidence with its original source hashes.
Current mutable cache paths are observation metadata, never replay dependencies.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_dynamic_nav_research_v2 as nav_module
from scripts import ndx_dynamic_frozen_comparison as historical

SELF = Path(__file__).resolve()
LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
          for path in (SELF, Path(nav_module.__file__).resolve(), Path(historical.__file__).resolve())}
LOADED.update(nav_module._SOURCES)
STOCK_ROLES = ('RETURN', 'USER_PREFERENCE', 'INCUMBENT')
MUTABLE_NAV_SOURCES = {(ROOT / 'data/cache/funds' / name).resolve()
                       for name in ('012922.csv', '012922.csv.manifest.json')}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify(sources):
    for name, expected in sources.items():
        if digest(Path(name).read_bytes()) != expected:
            raise ValueError('Comparison source drift: ' + name)


def merge_sources(*mappings):
    result = {}
    for mapping in mappings:
        for name, expected in mapping.items():
            if name in result and result[name] != expected:
                raise ValueError('Conflicting comparison source: ' + name)
            result[name] = expected
    return result


def read_bound(path, expected):
    raw = Path(path).read_bytes()
    if digest(raw) != expected:
        raise ValueError('Bound comparison input differs: ' + str(path))
    return raw


def write_once(path, raw):
    """Resume an identical immutable snapshot without rewriting its bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Existing snapshot differs: ' + str(path))
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    if path.read_bytes() != raw:
        raise ValueError('Snapshot readback differs')


def snapshot_nav(*, csv_path, manifest_path, expected_csv_sha256,
                 expected_manifest_sha256, output_directory):
    verify(LOADED)
    csv_path, manifest_path = Path(csv_path).resolve(), Path(manifest_path).resolve()
    raw = read_bound(csv_path, expected_csv_sha256)
    sidecar = read_bound(manifest_path, expected_manifest_sha256)
    manifest = json.loads(sidecar)
    if manifest['content_sha256'] != expected_csv_sha256 or manifest['content_bytes'] != len(raw):
        raise ValueError('Snapshot NAV sidecar binding differs')
    fingerprint = digest((expected_csv_sha256 + ':' + expected_manifest_sha256).encode())
    directory = Path(output_directory).resolve() / fingerprint
    copy_csv, copy_manifest = directory / '012922.csv', directory / '012922.csv.manifest.json'
    if csv_path == copy_csv or manifest_path == copy_manifest:
        raise ValueError('Snapshot must be separate from mutable source')
    write_once(copy_csv, raw)
    write_once(copy_manifest, sidecar)
    # Detect a cache refresh during capture; never silently mix versions.
    read_bound(csv_path, expected_csv_sha256)
    read_bound(manifest_path, expected_manifest_sha256)
    capture = dict(schema='ndx_nav_immutable_snapshot_v1', csv_path=str(copy_csv),
        manifest_path=str(copy_manifest), csv_sha256=expected_csv_sha256,
        manifest_sha256=expected_manifest_sha256, fingerprint=fingerprint,
        original_source_observation=dict(csv_path=str(csv_path), manifest_path=str(manifest_path),
            fetched_at=manifest.get('fetched_at'), data_end=manifest.get('data_end')),
        original_paths_are_replay_dependencies=False, original_sidecar_bytes_preserved=True,
        source_authenticity_verified=False, publication_time_verified=False,
        point_in_time_verified=False, promotion_allowed=False)
    capture_path = directory / 'snapshot.json'
    encoded = (json.dumps(capture, sort_keys=True, indent=2) + '\n').encode()
    write_once(capture_path, encoded)
    verify(LOADED)
    return capture_path, digest(encoded)


def compare_snapshot(*, snapshot_path, snapshot_sha256):
    verify(LOADED)
    snapshot_path = Path(snapshot_path).resolve()
    capture = json.loads(read_bound(snapshot_path, snapshot_sha256))
    if (capture['schema'] != 'ndx_nav_immutable_snapshot_v1'
            or capture['original_paths_are_replay_dependencies'] is not False
            or any(capture[key] is not False for key in ('source_authenticity_verified',
                'publication_time_verified', 'point_in_time_verified', 'promotion_allowed'))):
        raise ValueError('Research NAV snapshot required')
    expected_fingerprint = digest((capture['csv_sha256'] + ':' + capture['manifest_sha256']).encode())
    csv_path, manifest_path = Path(capture['csv_path']), Path(capture['manifest_path'])
    if (capture['fingerprint'] != expected_fingerprint or snapshot_path.parent.name != expected_fingerprint
            or csv_path != snapshot_path.parent / '012922.csv'
            or manifest_path != snapshot_path.parent / '012922.csv.manifest.json'):
        raise ValueError('Immutable snapshot namespace differs')
    sources = merge_sources(LOADED, {str(snapshot_path): snapshot_sha256})
    loaded = {}
    for role in (*STOCK_ROLES, '012922'):
        name, expected = historical.REPORTS[role]
        path = historical.DIRECTORY / name
        report = json.loads(read_bound(path, expected))
        if report['promotion_allowed'] is not False:
            raise ValueError('Historical research-only report required')
        sources = merge_sources(sources, {str(path): expected})
        if role in STOCK_ROLES:
            sources = merge_sources(sources, report['source_hashes'])
        else:
            # Only the two known mutable NAV cache paths become observations.
            # Historical numerical code and any other evidence remain bound.
            sources = merge_sources(sources, {name: value for name, value in report['source_hashes'].items()
                if Path(name).resolve() not in MUTABLE_NAV_SOURCES})
        loaded[role] = report
    verify(sources)
    control = loaded['INCUMBENT']['execution']
    dates = [row['session'] for row in control['daily']]
    clock = [(row['decision_date'], row['execution_date']) for row in control['decisions']]
    rows = []
    for role in STOCK_ROLES:
        execution = loaded[role]['execution']
        if ([row['session'] for row in execution['daily']] != dates
                or [(row['decision_date'], row['execution_date']) for row in execution['decisions']] != clock
                or execution['execution_policy'] != control['execution_policy']
                or execution['daily'][0]['total_value_usd'] != control['daily'][0]['total_value_usd']):
            raise ValueError('Historical stock comparison coordinates differ')
        if role == 'USER_PREFERENCE' and any(
                {target['ticker'] for target in row['targets'].values()} != {'AMAT', 'AVGO', 'CDNS', 'GOOG'}
                for row in execution['decisions']):
            raise ValueError('Historical preference identity differs')
        summary = execution['summary']
        rows.append(dict(role=role, path_return=summary['path_return_net'],
            annualized_return_252_session=(1 + summary['path_return_net']) ** (252 / (len(dates) - 1)) - 1,
            path_max_drawdown=summary['path_max_drawdown'],
            fees_usd=sum(row['transaction_cost_usd'] for row in execution['trades']),
            invested_risk_failure_days=sum(any(row['shares'].values()) and not row['risk']['all_passed']
                for row in execution['daily']), target_cardinalities=sorted(set(summary['k_path']))))
    nav = nav_module.load_nav_v2(csv_path=csv_path, manifest_path=manifest_path,
        expected_csv_sha256=capture['csv_sha256'], expected_manifest_sha256=capture['manifest_sha256'],
        calendar=pd.DatetimeIndex(dates))
    sources = merge_sources(sources, nav['source_hashes'])
    old_nav = loaded['012922']
    old_sources = []
    for name, expected in old_nav['source_hashes'].items():
        path = Path(name)
        observed = digest(path.read_bytes()) if path.exists() else None
        old_sources.append(dict(path=name, historical_expected_sha256=expected,
            observed_sha256=observed, matches_historical_source=observed == expected))
    rows.append({key: nav[key] for key in ('role', 'path_return', 'annualized_return_252_session',
                                          'path_max_drawdown')})
    verify(sources)
    return dict(schema='ndx_dynamic_frozen_comparison_v2', review_status='DRAFT_PENDING_ROOT_REVIEW',
        rows=rows, nav_report=nav, source_hashes=sources, date_start=dates[0], date_end=dates[-1],
        session_count=len(dates), historical_nav_rows_exact_match=old_nav['rows'] == nav['rows'],
        historical_nav_source_observations=old_sources,
        historical_nav_source_closure_restored=False, historical_nav_report_modified=False,
        historical_source_observations_are_replay_dependencies=False,
        stock_execution_rerun=False, historical_stock_reports_reused=list(STOCK_ROLES),
        training_rerun=False, current_pool_reselected=False, historical_diagnostic_only=True,
        native_currency_nav=True, nav_currency_and_publication_equivalence_verified=False,
        publication_time_verified=False, point_in_time_verified=False,
        candidate_search_exhaustive=False, independent_oos=False,
        winner_selected=False, promotion_allowed=False)


def save_draft(report, path):
    verify(report['source_hashes'])
    encoded = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded)
    if path.read_bytes() != encoded:
        raise ValueError('Draft comparison readback differs')
    verify(report['source_hashes'])
    return digest(encoded)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--csv-sha256', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output-directory', required=True)
    arguments = parser.parse_args()
    directory = Path(arguments.output_directory).resolve()
    if (ROOT / 'data/cache/research').resolve() not in directory.parents:
        raise ValueError('Separate research output directory required')
    snapshot_path, snapshot_sha256 = snapshot_nav(csv_path=arguments.csv, manifest_path=arguments.manifest,
        expected_csv_sha256=arguments.csv_sha256, expected_manifest_sha256=arguments.manifest_sha256,
        output_directory=directory)
    report = compare_snapshot(snapshot_path=snapshot_path, snapshot_sha256=snapshot_sha256)
    path = snapshot_path.parent / 'comparison_draft.json'
    print(json.dumps(dict(path=str(path), sha256=save_draft(report, path),
        historical_nav_rows_exact_match=report['historical_nav_rows_exact_match'],
        session_count=report['session_count'], rows=report['rows']), indent=2))
