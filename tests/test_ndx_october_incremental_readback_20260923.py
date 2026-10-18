import copy
import json
import unittest
from unittest.mock import patch

from scripts import ndx_october_incremental_readback_20260923 as module


class IncrementalOctoberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = json.loads(module.SEED.read_bytes())
        cls.previous = json.loads(module.Path(cls.seed['index']['path']).read_bytes())

    def extension(self):
        value = copy.deepcopy(self.previous)
        value['completed'].append(dict(job_id='new', started={}, result={}))
        return value

    def test_exact_seed_prefix_accepted_without_old_numerical_calls(self):
        self.assertEqual(module.original.archive.drift.file_sha(module.SEED), module.SEED_SHA)
        module.check_prefix(self.seed, self.previous, self.extension())

    def test_changed_old_result_and_reordered_prefix_rejected(self):
        value = self.extension()
        value['completed'][0]['result']['sha256'] = '0'*64
        with self.assertRaises(ValueError):
            module.check_prefix(self.seed, self.previous, value)
        value = self.extension()
        value['completed'][:2] = reversed(value['completed'][:2])
        with self.assertRaises(ValueError):
            module.check_prefix(self.seed, self.previous, value)

    def test_no_new_rows_and_mismatched_detail_ref_rejected(self):
        with self.assertRaises(ValueError):
            module.check_prefix(self.seed, self.previous, self.previous)
        seed = copy.deepcopy(self.seed)
        seed['details'][0]['result_reference']['sha256'] = '0'*64
        with self.assertRaises(ValueError):
            module.check_prefix(seed, self.previous, self.extension())

    def test_closed_publication_builds_once_and_refuses_source_drift(self):
        value = dict(historical_expected_source_hashes={'source': 'hash'}, archive_resolution={'ok': 1})
        with patch.object(module, 'build', return_value=value) as build, \
                patch.object(module.original.archive, 'load_contract', return_value={}), \
                patch.object(module.original.archive, 'verify_expected_sources', side_effect=[{'ok': 1}, {'ok': 0}]), \
                patch.object(module.original, 'publish', return_value={'path': 'artifact', 'sha256': 'hash'}), \
                patch.object(module.original.archive.drift, 'file_sha', return_value='hash'):
            with self.assertRaisesRegex(ValueError, 'Published bytes or sources changed'):
                module.build_and_publish('artifact', 'index', 'sha')
            build.assert_called_once_with('index', 'sha')


if __name__ == '__main__':
    unittest.main()
