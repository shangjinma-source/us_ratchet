"""Pure recovery plan from explicit failed-parent metadata, never byte authentication.

The publisher must authenticate the complete inventory, each supplied document,
and full machine/task EOF before executing this plan. Missing successful parent
publication is intentional; no successful-parent overlay interface is used.
"""
import copy
import re
from pathlib import PureWindowsPath

FLAGS = ('formal_comparison_passed', 'point_in_time_verified', 'promotion_allowed',
         'future_independent_oos', 'economics_recomputed', 'risk_recomputed',
         'fit_performed', 'account_executed', 'independent_export_readback_passed',
         'visual_acceptance_passed', 'workbook_delivered')
MAX_PACKAGE_BYTES = 50 * 1024 * 1024


def require(value, message):
    if not value:
        raise ValueError(message)


def false_flags(value):
    require(all(value.get(k) is False for k in FLAGS), 'Exact False authority flags')


def sha(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'SHA256')
    return value


def relative(value):
    require(type(value) is str and value and '\\' not in value and ':' not in value, 'Relative slash path')
    p = PureWindowsPath(value)
    require(not p.is_absolute() and not p.drive and not p.root and all(x not in ('', '.', '..') and x == x.rstrip(' .') for x in value.split('/')), 'Bounded relative path')
    return value


def plan_failed_export_recovery(*, parent_root, parent_inventory, failure, failure_reference,
                                started, started_reference, index, index_reference, attempts):
    root = PureWindowsPath(parent_root)
    require(root.is_absolute(), 'Absolute failed parent root')
    require(type(parent_inventory) is list and parent_inventory, 'Complete supplied parent inventory')
    inventory = {}
    for item in parent_inventory:
        require(type(item) is dict and set(item) == {'path', 'sha256', 'byte_count'}, 'Exact inventory record')
        name = relative(item['path'])
        require(name.casefold() not in {x.casefold() for x in inventory}, 'Unique inventory paths')
        sha(item['sha256'])
        require(type(item['byte_count']) is int and item['byte_count'] >= 0, 'Exact inventory byte count')
        inventory[name] = item
    require(not {'export_manifest.json', 'publication.json', 'machine_index.json', 'navigation_links.json'} & {x.casefold() for x in inventory}, 'This recovery requires the known pre-publication failure phase')

    def bound(ref, expected=None):
        require(type(ref) is dict and {'path', 'sha256'} <= set(ref), 'Artifact reference')
        sha(ref['sha256'])
        path = PureWindowsPath(ref['path'])
        try:
            name = path.relative_to(root).as_posix()
        except (ValueError, TypeError):
            raise ValueError('Artifact outside failed namespace')
        relative(name)
        require(name in inventory and inventory[name]['sha256'] == ref['sha256'], 'Artifact inventory binding')
        require(expected is None or name == expected, 'Fixed artifact role path')
        if 'byte_count' in ref:
            require(type(ref['byte_count']) is int and ref['byte_count'] == inventory[name]['byte_count'], 'Reference byte count')
        return inventory[name]

    bound(failure_reference, 'failure.json'); bound(started_reference, 'started.json')
    bound(index_reference, 'sources/index.json')
    require(failure.get('schema') == 'DATED_H_WORKBOOK_EXTENSION_FAILURE_V1' and failure.get('status') == 'FAILED_DO_NOT_CONSUME', 'Failed parent only')
    require(failure.get('retry_allowed') is False and failure.get('stream_completed') is True and failure.get('all_attempts_retained') is True, 'Preserved terminal failure metadata')
    require('Full ordered task link cells' in failure.get('error', ''), 'Known native navigation failure')
    false_flags(failure); false_flags(started)
    require(started.get('schema') == 'DATED_H_WORKBOOK_EXTENSION_STARTED_V1', 'Started schema')
    rows = index['task_index']
    require(type(rows) is list and len(rows) == 1632, 'Full 1632 source index')
    ids = []
    for i, row in enumerate(rows):
        require(type(row['task_ordinal']) is int and row['task_ordinal'] == i, 'Original ordinal sequence')
        ids.append(sha(row['numerical_task_id']))
    require(len(set(ids)) == 1632 and started['default_task_id'] == ids[0], 'Unique tasks and original first task')
    require(type(attempts) is list and attempts, 'Full attempt metadata')
    packages = []; preserved = []; cursor = 0
    for i, entry in enumerate(attempts):
        require(set(entry) == {'pending', 'pending_reference', 'started', 'started_reference'}, 'Attempt envelope')
        pending = entry['pending']; begin = entry['started']
        directory = f'attempts/attempt-{i:05d}'
        bound(entry['pending_reference'], directory + '/pending.json')
        bound(entry['started_reference'], directory + '/started.json')
        false_flags(pending); false_flags(begin)
        require(pending['schema'] == 'DATED_H_EXPORT_ATTEMPT_V1' and begin['status'] == 'PENDING_EXPORT_ATTEMPT', 'Attempt schemas')
        for field in ('attempt_index', 'start_task_ordinal', 'stop_task_ordinal'):
            require(type(pending[field]) is int and type(begin[field]) is int and pending[field] == begin[field], 'Exact attempt integer coordinates')
        require(pending['attempt_index'] == i, 'Full attempt order')
        start, stop = pending['start_task_ordinal'], pending['stop_task_ordinal']
        require(0 <= start < stop <= 1632 and pending['task_ids'] == ids[start:stop] == begin['task_ids'], 'Attempt original task slice')
        artifact = bound(pending['reference'], directory + '/artifact.xlsx')
        require(type(pending['bytes']) is int and pending['bytes'] == artifact['byte_count'] and pending['sha256'] == artifact['sha256'], 'Original attempt bytes')
        bound(pending['expected_cells_reference'], directory + '/expected_cells.jsonl')
        bound(pending['chart_source_index_reference'], directory + '/chart_source_index.json')
        for preview in pending['previews']:
            bound(preview)
        costs = pending['costs']
        require(type(costs['missing']) is bool and type(costs['taskCount']) is int and costs['taskCount'] == stop - start and costs['taskIds'] == ids[start:stop], 'Exact saved package costs and tasks')
        expected_views = [('任务索引', 'A1:C20')] if costs['missing'] else [('路径查看', 'A1:G46'), ('风险查看', 'A1:N43')]
        require(type(pending['previews']) is list and len(pending['previews']) == len(expected_views), 'Complete original preview roles')
        for pi, (preview, (worksheet, area)) in enumerate(zip(pending['previews'], expected_views)):
            bound(preview, directory + f'/preview-{pi}.png')
            require(preview['worksheet'] == worksheet and preview['range'] == area, 'Original preview role and range')
        require(type(costs['dataRows']) is int and 0 < costs['dataRows'] <= 250000, 'Saved data row limit')
        if pending['status'] == 'OVERSIZE_ATTEMPT_NOT_ACCEPTED':
            require(pending['bytes'] > MAX_PACKAGE_BYTES, 'True oversize attempt')
            preserved.append(copy.deepcopy(entry)); continue
        require(pending['status'] == 'PENDING_COMPLETE_STREAM_AND_SOURCE_PUBLICATION' and 0 < pending['bytes'] <= MAX_PACKAGE_BYTES, 'Accepted-size pending attempt')
        require(start == cursor, 'Full accepted task partition without gaps or overlaps')
        filename = f'package-{len(packages)+1:04d}.xlsx'
        require(filename in inventory and inventory[filename]['sha256'] == artifact['sha256'] and inventory[filename]['byte_count'] == artifact['byte_count'], 'Saved package equals attempt bytes')
        packages.append({'package_index': len(packages), 'filename': filename,
                         'start_task_ordinal': start, 'stop_task_ordinal': stop,
                         'task_ids': ids[start:stop], 'attempt_index': i,
                         'original_workbook_reference': {'path': str(root / filename), 'sha256': artifact['sha256']},
                         'byte_count': artifact['byte_count'], 'pending_reference': copy.deepcopy(entry['pending_reference']),
                         'action': 'REBUILD_SINGLETON_WITH_REGISTERED_B5_ONLY_DELTA' if stop-start == 1 and not costs['missing'] else 'COPY_ORIGINAL_BYTES_NO_SDK_EXPORT'})
        cursor = stop
    require(cursor == 1632, 'All 1632 tasks retained')
    require({x for x in inventory if re.fullmatch('package-\\d{4}\\.xlsx', x)} == {p['filename'] for p in packages}, 'Exact package inventory')
    require({x for x in inventory if re.fullmatch('attempts/attempt-\\d{5}/pending.json', x)} == {f'attempts/attempt-{i:05d}/pending.json' for i in range(len(attempts))}, 'Exact pending inventory')
    for required in ('tasks.jsonl', 'shared_display.json', 'classification.json', 'navigation_expected_cells.jsonl', 'attempts/navigation-artifact.xlsx', 'sources/publication.json', 'sources/audit.json', 'sources/shared.json', 'sources/classification.json'):
        require(required in inventory, 'Required saved recovery source: ' + required)
    shards = sorted(x for x in inventory if re.fullmatch('machine/tasks-\\d{5}\\.jsonl', x))
    require(shards and shards == [f'machine/tasks-{i:05d}.jsonl' for i in range(len(shards))], 'Contiguous machine shard inventory')
    require(sum(inventory[x]['byte_count'] for x in shards) == inventory['tasks.jsonl']['byte_count'], 'Machine sizes equal full task copy; EOF remains unverified')
    return {'schema': 'DATED_H_FAILED_EXPORT_RECOVERY_PLAN_V1',
            'status': 'STRUCTURAL_PLAN_PENDING_INDEPENDENT_BYTES_AND_FULL_EOF_VALIDATION',
            'parent_status': failure['status'], 'old_publication_existed': False,
            'recovery_is_new_attempt': True, 'planned_task_count': 1632,
            'package_count': len(packages), 'packages': packages,
            'preserved_oversize_attempts': preserved,
            'singleton_rebuild_count': sum(p['action'].startswith('REBUILD') for p in packages),
            'navigation_links': [{'worksheet': '全部任务', 'cell': f'H{i+2}', 'target': p['filename'], 'location': f"'任务索引'!A{i-p['start_task_ordinal']+2}"} for p in packages for i in range(p['start_task_ordinal'], p['stop_task_ordinal'])],
            'parent_inventory_preserved': copy.deepcopy(parent_inventory),
            'parent_references': copy.deepcopy({'failure': failure_reference, 'started': started_reference, 'index_copy': index_reference}),
            'machine_shards': shards, 'machine_eof_verified': False,
            'source_bytes_authenticated': False, 'recovery_dispatch_authorized': False,
            'path_containment_physical_verified': False,
            'chart_and_cell_data_verified': False, **{k: False for k in FLAGS}}
