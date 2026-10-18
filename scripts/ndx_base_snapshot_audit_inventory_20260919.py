"""Seal the fifteen already-completed independent readbacks, without evaluation."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ndx_base_snapshot_inventory_20260919 import BASE, digest
SOURCE = Path(__file__).resolve()
LOADED = digest(SOURCE)
HELPER = SOURCE.with_name('ndx_base_snapshot_inventory_20260919.py')
HELPER_LOADED = digest(HELPER)


def build():
    inventory_path = BASE / 'present_source_inventory_20260919.json'
    expected = '7dfb85f95de5d88ae5588834b822366f00d3a1532a78852483df9c00e7155820'
    if digest(inventory_path) != expected:
        raise ValueError('Initial inventory binding differs')
    inventory = json.loads(inventory_path.read_bytes())
    sources = {str(inventory_path): expected, str(SOURCE): LOADED, str(HELPER): HELPER_LOADED}
    dates = []
    for ordinal, row in enumerate(inventory['dates']):
        path = Path(row['index_path']).parent / ('completed_date_independent_audit_20260912.json' if ordinal < 3 else 'completed_date_independent_audit_20260919.json')
        report = json.loads(path.read_bytes())
        if (report['schema'] != 'ndx_snapshot_completed_date_independent_audit_v1'
                or report['date'].replace('-', '') != row['date']
                or report['complete_task_count'] != row['planned']
                or report['complete_task_lineage_verified'] is not True
                or report['all_sampled_windows_independently_recomputed'] is not True
                or report['no_fitter_or_evaluator_called'] is not True
                or report['all_tasks_old_metrics_independently_recomputed'] is not False
                or report['point_in_time_verified'] is not False or report['promotion_allowed'] is not False
                or report['source_hashes'].get(row['index_path']) != row['index_sha256']):
            raise ValueError('Independent date report binding differs: ' + row['date'])
        # Each sealed date audit already performed its full numerical closure
        # checks. This inventory binds reports and indices, without re-reading
        # their 59.7 GiB combined transitive checkpoint payloads a second time.
        sources[row['index_path']] = row['index_sha256']
        sources[str(path)] = digest(path)
        dates.append(dict(date=row['date'], index_path=row['index_path'], index_sha256=row['index_sha256'],
                          audit_path=str(path), audit_sha256=sources[str(path)], completed=report['complete_task_count'],
                          sampled_tasks=report['sampled_task_count']))
    for name, sha in sources.items():
        if digest(Path(name)) != sha:
            raise ValueError('Source drift after readbacks: ' + name)
    return dict(schema='ndx_base_snapshot_all15_readback_inventory_20260919_v1', dates=dates,
                completed=sum(r['completed'] for r in dates), date_count=len(dates), source_hashes=sources,
                complete_task_lineage_verified=True, scalar_verification='PRESPECIFIED_FIRST_LAST_PER_K_AND_WEIGHT_SPEC',
                validation_scope='DIRECT_SAVED_AUDIT_AND_INDEX_BYTES_WITH_NESTED_DATE_AUDIT_REFERENCES',
                transitive_numerical_sources_rehashed_by_inventory=False,
                all_tasks_economics_independently_recomputed=False, no_fitter_or_evaluator_called=True,
                point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    result = build()
    output = BASE / 'all15_independent_readback_inventory_20260919.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    for name, sha in result['source_hashes'].items():
        if digest(Path(name)) != sha:
            raise ValueError('Source drift after publication: ' + name)
    print(json.dumps(dict(path=str(output), sha256=digest(output), completed=result['completed'], dates=result['date_count'])))
