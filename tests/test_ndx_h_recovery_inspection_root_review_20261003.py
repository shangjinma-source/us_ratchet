from copy import deepcopy
from hashlib import sha256
import unittest
from unittest.mock import patch

from backtest import ndx_h_failed_export_recovery_inspection_research as inspection
from backtest import ndx_h_saved_machine_recovery_research as producer
from test_ndx_h_saved_machine_recovery_research import fixture, streams


def reference(name):
    return dict(path='D:/synthetic/' + name, sha256=sha256(name.encode()).hexdigest())


class Tests(unittest.TestCase):
    def test_independent_stream_reader_does_not_call_producer(self):
        index, source, blobs = fixture()
        saved = producer.inspect_machine_stream(index=index, shards=streams(blobs), expected_tasks_reference=source)
        def arguments():
            return dict(index=index, expected_tasks_reference=source,
                        shards=(dict(filename=f'machine/tasks-{i:05d}.jsonl', raw_bytes=b) for i, b in enumerate(blobs)),
                        saved_descriptors=saved['shards'], saved_task_locations=saved['task_locations'])
        with patch.object(producer, 'inspect_machine_stream', side_effect=AssertionError('Producer must not run')):
            report = inspection.inspect_machine_stream(**arguments())
            self.assertEqual(report['verified_records'], 1632)
            self.assertIs(report['physical_inventory_verified'], False)
            corrupted = arguments()
            corrupted['saved_descriptors'] = deepcopy(saved['shards'])
            corrupted['saved_descriptors'][1]['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                inspection.inspect_machine_stream(**corrupted)

    def test_repair_decision_cannot_be_rewritten_in_both_manifests(self):
        index, _, _ = fixture()
        for row in index['task_index']:
            row['status'] = 'DISPLAY_PROJECTED'
        parent, output = [], []
        for i, (start, stop, action) in enumerate(((0, 1, inspection.REPAIR), (1, 1632, inspection.COPY))):
            old = dict(package_index=i, filename=f'package-{i+1:04d}.xlsx',
                       start_task_ordinal=start, stop_task_ordinal=stop,
                       task_ids=[r['numerical_task_id'] for r in index['task_index'][start:stop]],
                       action=action, original_workbook_reference=reference(f'old{i}.xlsx'),
                       pending_reference=reference(f'pending{i}.json'), byte_count=8)
            new = deepcopy(old)
            new.update(workbook_reference=dict(path='D:/new/' + old['filename'],
                                               sha256=old['original_workbook_reference']['sha256']),
                       sha256=old['original_workbook_reference']['sha256'],
                       repair_evidence_reference=reference(f'repair{i}.json'))
            parent.append(old)
            output.append(new)
        result = inspection.inspect_package_partition(index=index, parent_packages=parent, packages=output)
        self.assertEqual(result['repaired_package_count'], 1)
        parent[0]['action'] = output[0]['action'] = inspection.COPY
        with self.assertRaises(ValueError):
            inspection.inspect_package_partition(index=index, parent_packages=parent, packages=output)


if __name__ == '__main__':
    unittest.main()
