import copy
from hashlib import sha256
import unittest

from backtest import ndx_h_saved_machine_recovery_research as module


def fixture():
    lines = [(f'{{"original_task":{i},"literal":"unchanged"}}\n').encode()
             for i in range(1632)]
    rows, offset = [], 0
    for ordinal, line in enumerate(lines):
        rows.append(dict(task_ordinal=ordinal, numerical_task_id=sha256(str(ordinal).encode()).hexdigest(),
                         jsonl_record=dict(record_index=ordinal, byte_start=offset,
                                           byte_stop=offset + len(line), row_sha256=sha256(line).hexdigest())))
        offset += len(line)
    reference = dict(path='D:/saved/tasks.jsonl', sha256=sha256(b''.join(lines)).hexdigest())
    index = dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1', planned_task_count=1632,
                 task_index=rows, task_jsonl_reference=dict(**reference, record_count=1632, byte_count=offset))
    blobs = [b''.join(lines[i:i+17]) for i in range(0, 1632, 17)]
    return index, reference, blobs


def streams(blobs):
    for ordinal, blob in enumerate(blobs):
        yield dict(filename=f'machine/tasks-{ordinal:05d}.jsonl',
                   chunks=(blob[i:i+37] for i in range(0, len(blob), 37)))


class Tests(unittest.TestCase):
    def test_one_pass_chunk_boundaries_and_original_local_coordinates(self):
        index, reference, blobs = fixture()
        before = copy.deepcopy(index)
        result = module.inspect_machine_stream(index=index, expected_tasks_reference=reference,
                                               shards=streams(blobs))
        self.assertEqual(index, before)
        self.assertEqual(result['record_count'], 1632)
        self.assertEqual(result['sha256'], reference['sha256'])
        self.assertEqual(result['shards'][1]['sha256'], sha256(blobs[1]).hexdigest())
        self.assertEqual(result['task_locations'][17]['byte_start'], 0)
        self.assertEqual(result['task_locations'][17]['shard_index'], 1)
        self.assertTrue(result['supplied_stream_eof_verified'])
        for flag in ('full_tasks_copy_verified', 'physical_inventory_verified',
                     'recovery_dispatch_authorized', 'numerical_replay_performed'):
            self.assertIs(result[flag], False)

    def test_changed_truncated_missing_extra_and_wrong_shard_reject(self):
        index, reference, blobs = fixture()
        variants = [
            [blobs[0].replace(b'unchanged', b'UNCHANGED', 1), *blobs[1:]],
            [*blobs[:-1], blobs[-1][:-1]],
            blobs[:-1],
            [*blobs, b'{}\n'],
            [b'', *blobs],
        ]
        for variant in variants:
            with self.subTest(length=len(variant)), self.assertRaises(ValueError):
                module.inspect_machine_stream(index=index, expected_tasks_reference=reference,
                                              shards=streams(variant))
        bad = list(streams(blobs))
        bad[0]['filename'] = '../machine/tasks-00000.jsonl'
        with self.assertRaises(ValueError):
            module.inspect_machine_stream(index=index, expected_tasks_reference=reference, shards=bad)

    def test_index_and_external_anchor_are_separate_gates(self):
        for field in ('byte_start', 'record_index', 'row_sha256'):
            index, reference, blobs = fixture()
            index['task_index'][17]['jsonl_record'][field] = '0' * 64 if field == 'row_sha256' else False
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.inspect_machine_stream(index=index, expected_tasks_reference=reference,
                                              shards=streams(blobs))
        index, reference, blobs = fixture()
        index['task_jsonl_reference']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            module.inspect_machine_stream(index=index, expected_tasks_reference=reference, shards=streams(blobs))

    def test_transport_failure_propagates_without_partial_success(self):
        index, reference, blobs = fixture()
        def failed():
            yield blobs[0][:37]
            raise OSError('saved source read failed')
        with self.assertRaisesRegex(OSError, 'saved source read failed'):
            module.inspect_machine_stream(index=index, expected_tasks_reference=reference,
                shards=[dict(filename='machine/tasks-00000.jsonl', chunks=failed())])


if __name__ == '__main__':
    unittest.main()
