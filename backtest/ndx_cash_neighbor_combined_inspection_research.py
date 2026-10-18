"""Independent saved journal parsing and arithmetic; no production evaluator.

Source authentication belongs to the caller. Arithmetic callbacks must be the
frozen independent helper/oracle, never the production evaluation function.
"""
import hashlib
import json


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def exact(left, right, message):
    require(encode(left) == encode(right), message)


def integer(value):
    require(type(value) is int and value >= 0, 'Exact nonnegative integer')
    return value


def hash_string(value):
    require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'Exact SHA256')

def records(raw, *, recovery, context):
    hash_string(context)
    require(type(raw) is bytes and raw and raw.endswith(b'\n'), 'Complete nonempty journal')
    previous = '0' * 64
    offset = 0
    result = []
    for sequence, line in enumerate(raw.splitlines(keepends=True)):
        def pairs(items):
            value = {}
            for key, item in items:
                require(key not in value, 'Duplicate JSON key')
                value[key] = item
            return value
        row = json.loads(line, object_pairs_hook=pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        shared = {'schema', 'previous_record_sha256', 'task_id', 'stage', 'payload', 'record_sha256'}
        extra = ({'record_sequence', 'registration_sha256', 'original_shard_task_position',
                  'original_global_task_position', 'scenario_candidate_ordinal'} if recovery else
                 {'sequence', 'context_sha256', 'task_position'})
        require(type(row) is dict and set(row) == shared | extra, 'Exact journal fields')
        for key in ('task_id','previous_record_sha256','record_sha256'):hash_string(row[key])
        exact(row['schema'], 'CASH_NEIGHBOR_RECOVERY_RECORD_V1' if recovery else 'CASH_NEIGHBOR_JOURNAL_RECORD_V1', 'Journal schema')
        exact(row['record_sequence' if recovery else 'sequence'], sequence, 'Record sequence')
        exact(row['registration_sha256' if recovery else 'context_sha256'], context, 'Original context')
        require(row['previous_record_sha256'] == previous, 'Hash chain')
        require(row['record_sha256'] == digest({k: v for k, v in row.items() if k != 'record_sha256'}), 'Record digest')
        require(encode(row) + b'\n' == line, 'Canonical original bytes')
        locator = dict(sequence=sequence, byte_start=offset, byte_stop=offset + len(line),
                       record_sha256=row['record_sha256'], task_id=row['task_id'], stage=row['stage'])
        result.append((row, locator))
        previous = row['record_sha256']
        offset += len(line)
    return result


def inspect_span(*, raw, tasks, prepared, descriptor, start, stop, context,
                 recovery, arguments, independent_result, expected_detail, sidecar=None):
    """Inspect a full recovery segment or original prefix ending in one saved RAW.

The sidecar RAW is independently recomputed here and counted as such; its old
postcheck is compared, not synthesized into the original journal.
"""
    require(type(recovery) is bool, 'Explicit journal role')
    integer(start); integer(stop)
    require(0 <= start < stop <= len(tasks), 'Original task range')
    require(len({t['task_id'] for t in tasks}) == len(tasks), 'Unique full shard tasks')
    require(integer(descriptor['global_task_stop']) - integer(descriptor['global_task_start']) == len(tasks), 'Full global descriptor')
    require(integer(descriptor['shard']['stop']) - integer(descriptor['shard']['start']) == len(tasks), 'Full source descriptor')
    require((recovery and sidecar is None) or (not recovery and start == 0 and sidecar is not None), 'Explicit supported source role')
    saved = records(raw, recovery=recovery, context=context)
    cursor = 0
    details = []
    journal_hash = hashlib.sha256(raw).hexdigest()
    for position in range(start, stop):
        task = tasks[position]
        ordinal = descriptor['shard']['start'] + position
        args = arguments(prepared, task, ordinal)
        use_sidecar = sidecar is not None and position == stop - 1
        length = 2 if use_sidecar else 3
        group = saved[cursor:cursor + length]
        require(len(group) == length, 'All original task records')
        exact([r['stage'] for r, _ in group], ['TASK_STARTED', 'RAW_RETURNED'] + ([] if use_sidecar else ['POSTCHECK']), 'No technical or missing records')
        for row, _ in group:
            require(row['task_id'] == task['task_id'], 'Task identity')
            exact(row['original_shard_task_position' if recovery else 'task_position'], position, 'Original task position')
            if recovery:
                exact(row['original_global_task_position'], descriptor['global_task_start'] + position, 'Original global position')
                exact(row['scenario_candidate_ordinal'], ordinal, 'Original scenario ordinal')
        reference = dict(path=descriptor['shard']['path'], sha256=descriptor['shard']['sha256'], jsonl_line_index=position)
        expected_start = dict(task_reference=reference, evaluation_argument_sha256=digest(args))
        if not recovery:
            reference['scenario_candidate_ordinal'] = ordinal
            expected_start['global_task_position'] = descriptor['global_task_start'] + position
        exact(group[0][0]['payload'], expected_start, 'Independent arguments and source pointer')
        payload = group[1][0]['payload']
        require(type(payload) is dict and set(payload) == {'result', 'error', 'explicit_evaluator_call_attempt_count', 'returned_evaluation_count'}, 'Full raw envelope')
        require(payload['error'] is None, 'No failed evaluation')
        exact(payload['explicit_evaluator_call_attempt_count'], 1, 'Single explicit call')
        exact(payload['returned_evaluation_count'], 1, 'Single saved return')
        result = independent_result(args)
        exact(payload['result'], result, 'Independent full financial and five-risk arithmetic')
        detail = expected_detail(prepared, result)
        require(detail['outcome'] in ('FEASIBLE', 'INFEASIBLE'), 'Economic terminal outcome')
        if use_sidecar:
            require(sidecar['schema'] == 'CASH_NEIGHBOR_SAVED_RAW_INDEPENDENT_POSTCHECK_V1' and sidecar['status'] == 'PASS_SAVED_RAW_ARITHMETIC_ONLY', 'Independent sidecar role')
            for key in ('evaluator_called', 'dispatch_authorized', 'original_journal_modified', 'original_postcheck_existed', 'promotion_allowed'):
                require(sidecar[key] is False, 'Sidecar authority')
            require(sidecar['saved_arithmetic_independently_verified'] is True, 'Sidecar checked arithmetic')
            exact(sidecar['journal_sha256'], journal_hash, 'Original sidecar journal')
            exact(sidecar['context_sha256'], context, 'Sidecar context')
            exact(sidecar['task_id'], task['task_id'], 'Sidecar task')
            exact(sidecar['task_position'], position, 'Sidecar local position')
            exact(sidecar['global_task_position'], descriptor['global_task_start'] + position, 'Sidecar global position')
            exact(sidecar['dispatch_record_reference'], group[0][1], 'Sidecar dispatch locator')
            exact(sidecar['raw_record_reference'], group[1][1], 'Sidecar RAW locator')
            exact(sidecar['independent_postcheck'], detail, 'Saved sidecar independent postcheck')
        else:
            exact(group[2][0]['payload'], detail, 'Original postcheck exact')
        details.append(dict(task_id=task['task_id'], original_global_task_position=descriptor['global_task_start'] + position,
                            outcome=detail['outcome'], original_target_stock_weight_l1=detail['original_target_stock_weight_l1'],
                            new_arithmetic_checked=True, source_kind='SIDECAR_RAW_RECHECKED' if use_sidecar else ('RECOVERY_JOURNAL' if recovery else 'OLD_PARTIAL_JOURNAL'),
                            raw_record_locator=group[1][1]))
        cursor += length
    require(cursor == len(saved), 'No surplus journal records')
    return dict(schema='CASH_COMBINED_SPAN_INSPECTION_V1', status='PASS', task_results=details,
                task_count=len(details), arithmetic_checked_count=len(details),
                sidecar_arithmetic_rechecked_count=int(sidecar is not None), journal_sha256=journal_hash,
                evaluator_called=False, source_bytes_authenticated=False, promotion_allowed=False)


def merge_original_order(*, ordered_task_ids, blocks):
    """Prove an exact full ordered partition; no set-only or prefix acceptance."""
    require(type(ordered_task_ids) is list and len(set(ordered_task_ids)) == len(ordered_task_ids), 'Unique expected domain')
    cursor = 0
    counts = dict(FEASIBLE=0, INFEASIBLE=0, EXTERNALLY_REFERENCED=0)
    for block in blocks:
        require(type(block) is list and block, 'Nonempty saved block')
        for row in block:
            require(cursor < len(ordered_task_ids) and row['task_id'] == ordered_task_ids[cursor], 'Exact original task order without gap/duplicate')
            require(row['outcome'] in counts, 'Only economic results or original external evidence')
            if row['outcome'] == 'EXTERNALLY_REFERENCED':
                require(cursor == 0 and row['new_arithmetic_checked'] is False, 'Unique original first evidence')
            else:
                require(row['new_arithmetic_checked'] is True, 'Independent arithmetic coverage')
            counts[row['outcome']] += 1
            cursor += 1
    require(cursor == len(ordered_task_ids) and counts['EXTERNALLY_REFERENCED'] == 1, 'Full domain and exactly one external first')
    return dict(task_count=cursor, outcome_counts=counts, evaluator_called=False, promotion_allowed=False)
