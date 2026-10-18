"""Independent synthetic byte-stream tests; no actual machine file or recovery."""
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
import unittest
from backtest import ndx_h_saved_machine_recovery_research as m


def fixture():
    # Deliberately opaque bytes: the reader must not reinterpret or reserialize JSON.
    lines = [(('原始零00:' + str(i) + ':' + 'x' * (i % 11)).encode() +
              (b'\r\n' if i % 2 else b'\n')) for i in range(1632)]
    rows = []; offset = 0
    for i, raw in enumerate(lines):
        rows.append(dict(task_ordinal=i, numerical_task_id=sha256(b'id:' + str(i).encode()).hexdigest(),
                         jsonl_record=dict(record_index=i, byte_start=offset,
                                           byte_stop=offset + len(raw), row_sha256=sha256(raw).hexdigest())))
        offset += len(raw)
    raw = b''.join(lines)
    ref = dict(path='D:/synthetic/tasks.jsonl', sha256=sha256(raw).hexdigest())
    index = dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1', planned_task_count=1632,
                 task_index=rows, task_jsonl_reference=dict(ref, byte_count=len(raw), record_count=1632))
    return index, ref, lines


def streams(blobs):
    for i, raw in enumerate(blobs):
        yield dict(filename=f'machine/tasks-{i:05d}.jsonl', chunks=(raw[j:j+1] for j in range(len(raw))))


class Review(unittest.TestCase):
    def test_opaque_utf8_crlf_local_global_offsets_and_full_digest(self):
        index, ref, lines = fixture(); original = deepcopy(index)
        stops = [1, 3, 38, 901, 1632]; start = 0; blobs = []
        for stop in stops:
            blobs.append(b''.join(lines[start:stop])); start = stop
        out = m.inspect_machine_stream(index=index, expected_tasks_reference=ref, shards=streams(blobs))
        self.assertEqual(index, original)
        self.assertEqual(out['sha256'], sha256(b''.join(blobs)).hexdigest())
        for shard, end in enumerate(stops):
            begin = 0 if shard == 0 else stops[shard-1]
            descriptor = out['shards'][shard]
            self.assertEqual((descriptor['start_task_ordinal'], descriptor['stop_task_ordinal']), (begin, end))
            self.assertEqual(descriptor['byte_count'], sum(map(len, lines[begin:end])))
            offset = 0
            for ordinal in range(begin, end):
                location = out['task_locations'][ordinal]
                self.assertEqual((location['byte_start'], location['byte_stop']), (offset, offset + len(lines[ordinal])))
                self.assertEqual(location['row_sha256'], sha256(lines[ordinal]).hexdigest())
                self.assertEqual(location['shard_index'], shard)
                offset += len(lines[ordinal])
        self.assertIs(out['numerical_replay_performed'], False)
        self.assertIs(out['physical_inventory_verified'], False)

    def test_late_iterator_failure_and_partial_shard_cannot_be_success(self):
        index, ref, lines = fixture(); full = b''.join(lines)
        def late_failure():
            yield dict(filename='machine/tasks-00000.jsonl', chunks=[full])
            raise OSError('EOF transport authentication failure')
        with self.assertRaisesRegex(OSError, 'EOF transport'):
            m.inspect_machine_stream(index=index, expected_tasks_reference=ref, shards=late_failure())
        # Concatenation is original, but a line may not straddle physical shards.
        with self.assertRaisesRegex(ValueError, 'partial line'):
            m.inspect_machine_stream(index=index, expected_tasks_reference=ref,
                                     shards=streams([full[:1], full[1:]]))
        changed = deepcopy(index); raw = full.replace(b'00:', b'01:', 1)
        first = lines[0].replace(b'00:', b'01:', 1)
        changed['task_index'][0]['jsonl_record']['row_sha256'] = sha256(first).hexdigest()
        # Even a rewritten per-row hash cannot bypass the independently anchored full hash.
        with self.assertRaisesRegex(ValueError, 'complete stream hash'):
            m.inspect_machine_stream(index=changed, expected_tasks_reference=ref, shards=streams([raw]))

    def test_size_gates_strict_types_and_duplicate_identity(self):
        index, ref, lines = fixture()
        oversized = b'x' * (32 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, 'byte chunks'):
            m.inspect_machine_stream(index=index, expected_tasks_reference=ref,
                                     shards=[dict(filename='machine/tasks-00000.jsonl', chunks=[oversized])])
        del oversized
        # Prove cumulative shard gate independently of per-chunk/line gates.
        with patch.object(m, 'MAX_SHARD_BYTES', 128), self.assertRaisesRegex(ValueError, 'shard size'):
            m.inspect_machine_stream(index=index, expected_tasks_reference=ref,
                                     shards=[dict(filename='machine/tasks-00000.jsonl', chunks=lines)])
        for attack in ('bool', 'float', 'duplicate', 'bytearray'):
            x = deepcopy(index); supplied = streams([b''.join(lines)])
            if attack == 'bool': x['task_index'][0]['jsonl_record']['byte_start'] = False
            elif attack == 'float': x['task_jsonl_reference']['byte_count'] = float(x['task_jsonl_reference']['byte_count'])
            elif attack == 'duplicate': x['task_index'][1]['numerical_task_id'] = x['task_index'][0]['numerical_task_id']
            else: supplied = [dict(filename='machine/tasks-00000.jsonl', chunks=[bytearray(lines[0])])]
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                m.inspect_machine_stream(index=x, expected_tasks_reference=ref, shards=supplied)


if __name__ == '__main__':
    unittest.main()
