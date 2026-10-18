"""Inspect supplied saved machine streams without filesystem IO or JSON replay.

Hashes include every original byte, including line terminators. The caller must
authenticate the index, external anchor, physical files and final inventory.
This function neither reads the full tasks copy nor certifies its existence.
"""
from hashlib import sha256
import re

TASK_COUNT = 1632
MAX_SHARD_BYTES = 32 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    require(type(value) is int and value >= 0, 'Exact nonnegative integer')
    return value


def digest(value):
    require(type(value) is str and re.fullmatch('[a-f0-9]{64}', value), 'SHA256')
    return value


def inspect_machine_stream(*, index, shards, expected_tasks_reference):
    """Consume ordered {filename, chunks} streams once; keep only line metadata.

    Each chunks iterable yields bytes of at most 32 MiB. A shard must end on a
    complete original line. No parsing, numerical computation or reserialization
    of the large task records occurs here.
    """
    require(type(index) is dict and index.get('schema') ==
            'SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1', 'Original B6 index')
    require(integer(index['planned_task_count']) == TASK_COUNT, 'Full task denominator')
    require(type(expected_tasks_reference) is dict and set(expected_tasks_reference) ==
            {'path', 'sha256'}, 'External original tasks reference')
    require(type(expected_tasks_reference['path']) is str and
            bool(expected_tasks_reference['path']), 'Original path identity')
    digest(expected_tasks_reference['sha256'])
    source = index['task_jsonl_reference']
    require(all(source[k] == expected_tasks_reference[k] for k in ('path', 'sha256')),
            'Index must bind the external tasks anchor')
    require(integer(source['record_count']) == TASK_COUNT, 'Original record count')
    expected_bytes = integer(source['byte_count'])
    rows = index['task_index']
    require(type(rows) is list and len(rows) == TASK_COUNT, 'Complete index rows')
    offset = 0
    identifiers = set()
    for ordinal, row in enumerate(rows):
        require(integer(row['task_ordinal']) == ordinal, 'Original index order')
        task_id = digest(row['numerical_task_id'])
        require(task_id not in identifiers, 'Unique original task IDs')
        identifiers.add(task_id)
        record = row['jsonl_record']
        require(integer(record['record_index']) == ordinal and
                integer(record['byte_start']) == offset, 'Original contiguous line coordinates')
        stop = integer(record['byte_stop'])
        require(offset < stop <= offset + MAX_SHARD_BYTES, 'Bounded positive original line')
        digest(record['row_sha256'])
        offset = stop
    require(offset == expected_bytes, 'Index complete byte extent')

    whole_hash = sha256()
    descriptors, locations = [], []
    global_bytes = 0
    for shard_index, shard in enumerate(shards):
        require(shard_index < TASK_COUNT, 'At least one record per bounded shard')
        require(type(shard) is dict and set(shard) == {'filename', 'chunks'}, 'Shard stream fields')
        filename = f'machine/tasks-{shard_index:05d}.jsonl'
        require(shard['filename'] == filename, 'Original contiguous shard order')
        shard_hash = sha256()
        start_ordinal = len(locations)
        shard_bytes, local_offset = 0, 0
        pending = bytearray()
        for chunk in shard['chunks']:
            require(type(chunk) is bytes and 0 < len(chunk) <= MAX_SHARD_BYTES,
                    'Bounded nonempty original byte chunks')
            shard_bytes += len(chunk)
            require(shard_bytes <= MAX_SHARD_BYTES, 'Original shard size limit')
            shard_hash.update(chunk)
            whole_hash.update(chunk)
            pending.extend(chunk)
            while True:
                end = pending.find(b'\n')
                if end < 0:
                    break
                raw = bytes(pending[:end + 1])
                del pending[:end + 1]
                ordinal = len(locations)
                require(ordinal < TASK_COUNT, 'No additional task records')
                expected = rows[ordinal]['jsonl_record']
                line_hash = sha256(raw).hexdigest()
                require(expected['byte_start'] == global_bytes and
                        expected['byte_stop'] == global_bytes + len(raw) and
                        expected['row_sha256'] == line_hash, 'Original line bytes and global position')
                locations.append(dict(task_ordinal=ordinal, shard_index=shard_index,
                                      byte_start=local_offset, byte_stop=local_offset + len(raw),
                                      row_sha256=line_hash))
                global_bytes += len(raw)
                local_offset += len(raw)
        require(not pending, 'No partial line at shard EOF')
        require(len(locations) > start_ordinal and local_offset == shard_bytes,
                'Nonempty complete shard')
        descriptors.append(dict(shard_index=shard_index, filename=filename,
                                start_task_ordinal=start_ordinal, stop_task_ordinal=len(locations),
                                record_count=len(locations) - start_ordinal, byte_count=shard_bytes,
                                sha256=shard_hash.hexdigest()))
    require(len(locations) == TASK_COUNT and global_bytes == expected_bytes,
            'Complete original record and byte denominator')
    final_hash = whole_hash.hexdigest()
    require(final_hash == expected_tasks_reference['sha256'], 'Original complete stream hash')
    return dict(schema='DATED_H_SAVED_MACHINE_STREAM_INSPECTION_V1',
                record_count=len(locations), byte_count=global_bytes, sha256=final_hash,
                shards=descriptors, task_locations=locations, supplied_stream_eof_verified=True,
                full_tasks_copy_verified=False, physical_inventory_verified=False,
                source_origin_authenticated=False, numerical_replay_performed=False,
                index_external_authentication_performed=False, recovery_dispatch_authorized=False,
                point_in_time_verified=False, promotion_allowed=False, workbook_delivered=False)
