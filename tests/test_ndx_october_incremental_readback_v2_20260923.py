from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import ndx_october_incremental_readback_v2_20260923 as module


class OctoberLineageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.base = {str(self.folder / 'source.py'): 'a' * 64}
        self.queue = dict(candidate_count=425, candidates=[{'task': {'job_id': str(index)}} for index in range(425)])
        self.entries = [dict(job_id=str(index), started=dict(path=str(self.folder / (str(index)+'.started.json')), sha256='b'*64),
                             result=dict(path=str(self.folder / (str(index)+'.json')), sha256='c'*64)) for index in range(425)]
        self.references = {}
        self.values = {}
        parent = None
        for count in reversed(module.COUNTS):
            sources = dict(self.base)
            for row in self.entries[:count]:
                for key in ('started', 'result'):
                    sources[row[key]['path']] = row[key]['sha256']
            if parent:
                sources[parent['path']] = parent['sha256']
            status = 'COMPLETE' if count == 425 else 'PARTIAL'
            final = dict(schema='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1', planned=425, completed=count,
                         status=status, historical_expected_source_hashes=sources, archive_resolution={},
                         **dict.fromkeys(module.original.FLAGS, False))
            value = dict(schema='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1',
                         queue=dict(path=str(module.original.QUEUE), sha256=module.original.QUEUE_SHA),
                         seed=None, planned=425, completed=deepcopy(self.entries[:count]), status=status,
                         finalization=final, **dict.fromkeys(module.original.FLAGS, False))
            parent = self.write(value)
            self.references[count] = parent
            self.values[count] = value

    def write(self, value):
        path = self.folder / ('index_' + module.original.pure.digest(value) + '.json')
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())

    def read(self, reference):
        raw = Path(reference['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference['sha256']:
            raise ValueError('Fixture edge SHA differs')
        return json.loads(raw)

    def check(self, value=None, reference=None, read=None):
        return module.validate_lineage(reference or self.references[425], value or self.values[425],
            self.references[201], self.base, self.queue, read or self.read)

    def test_exact_transitive_chain_passes_without_direct_101_edge(self):
        self.assertNotIn(self.references[101]['path'], self.values[425]['finalization']['historical_expected_source_hashes'])
        lineage, sources = self.check()
        self.assertEqual([row['completed'] for row in lineage], list(module.COUNTS))
        self.assertIn(self.references[101]['path'], sources)

    def test_parent_edge_hash_change_rejected(self):
        value = deepcopy(self.values[425])
        value['finalization']['historical_expected_source_hashes'][self.references[401]['path']] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA'):
            self.check(value, self.write(value))

    def test_missing_parent_and_non_index_input_rejected(self):
        for path in (self.references[401]['path'], next(iter(self.base)), self.entries[0]['started']['path']):
            value = deepcopy(self.values[425])
            del value['finalization']['historical_expected_source_hashes'][path]
            with self.assertRaises(ValueError):
                self.check(value, self.write(value))

    def test_changed_completed_prefix_rejected(self):
        value = deepcopy(self.values[425])
        value['completed'][0]['result']['sha256'] = 'e' * 64
        value['finalization']['historical_expected_source_hashes'][value['completed'][0]['result']['path']] = 'e' * 64
        with self.assertRaisesRegex(ValueError, 'prefix'):
            self.check(value, self.write(value))

    def test_skipped_seed_and_foreign_ancestry_rejected(self):
        for replacement in (self.references[101], {'path':str(self.folder.parent/'index_foreign.json'),'sha256':'f'*64}):
            value = deepcopy(self.values[425])
            del value['finalization']['historical_expected_source_hashes'][self.references[401]['path']]
            value['finalization']['historical_expected_source_hashes'][replacement['path']] = replacement['sha256']
            with self.assertRaises(ValueError):
                self.check(value, self.write(value))

    def test_nonfinalized_and_false_content_address_rejected(self):
        for kind in ('finalization', 'address'):
            def changed_read(reference):
                value = self.read(reference)
                if kind == 'finalization':
                    value['finalization'] = None
                else:
                    value['status'] = 'counterfeit'
                return value
            with self.assertRaises(ValueError):
                self.check(read=changed_read)


if __name__ == '__main__':
    unittest.main()
