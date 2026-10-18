import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_corrected_base_overlay_limited_drift_research as reader
from test_ndx_corrected_base_overlay_research import fixture


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LimitedDriftTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.exceptions = {}
        for i in range(26):
            path = self.root / (str(i) + '.csv')
            path.write_bytes(b'new')
            self.exceptions[str(path)] = dict(expected_historical_sha256=hashlib.sha256(b'old').hexdigest(),
                                             observed_current_sha256=sha(path))
        self.contract = dict(authority_source_hashes={}, exceptions=self.exceptions)
        self.mock = patch.object(reader.drift, 'load_contract', return_value=self.contract)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding='utf8')
        return dict(path=str(path), sha256=sha(path))

    def bundle(self):
        parent, replacements = fixture()
        parent['coordinate'] = dict(selection_date='2023-04-03')
        parent['source_hashes'] = {p: r['expected_historical_sha256'] for p, r in self.exceptions.items()}
        old = self.write('old.json', {'original': True})
        parent['records'][0]['lineage'] = dict(original_checkpoint_path=old['path'], original_checkpoint_sha256=old['sha256'])
        parent['records_sha256'] = reader.merger.digest(parent['records'])
        task = replacements[0]['task']
        row = dict(new_job_id='new', task=task, checkpoint_path=old['path'], checkpoint_sha256=old['sha256'])
        sources = {old['path']: old['sha256']}
        manifest = self.write('manifest.json', dict(date='2023-04-03', tasks=[row], source_hashes=sources))
        saved = dict(new_job_id='new', manifest_path=manifest['path'], manifest_sha256=manifest['sha256'], promotion_allowed=False,
                     result=dict(cache_checkpoint_sha256=old['sha256'], source_hashes=sources,
                                 evaluation=dict(result=replacements[0]['result'])))
        checkpoint = self.write('saved.json', saved)
        index = self.write('index.json', dict(schema='ndx_base_window_snapshot_completion_index_v1', status='COMPLETE', planned=1,
                           manifest=manifest, completed=[checkpoint], finalization=dict(status='COMPLETE', planned=1, completed=1,
                           source_closure_verified=True, source_hashes=sources)))
        audit = self.write('audit.json', dict(schema='ndx_snapshot_completed_date_independent_audit_v1',
            source_hashes={**sources, index['path']: index['sha256']}, date='2023-04-03', complete_task_count=1,
            complete_task_lineage_verified=True, all_sampled_windows_independently_recomputed=True,
            no_fitter_or_evaluator_called=True, promotion_allowed=False, point_in_time_verified=False))
        p = self.write('parent.json', parent)
        dates = [dict(date='20230403', index_path=index['path'], index_sha256=index['sha256'],
                      audit_path=audit['path'], audit_sha256=audit['sha256'])]
        dates += [dict(date='other-' + str(i)) for i in range(14)]
        authority = self.write('audit_inventory.json', dict(schema='ndx_base_snapshot_all15_readback_inventory_20260919_v1',
                                date_count=15, completed=15578, dates=dates))
        for name, value in [('AUDIT_INVENTORY', Path(authority['path'])), ('AUDIT_INVENTORY_SHA', authority['sha256'])]:
            mock = patch.object(reader, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        return dict(parent_path=p['path'], parent_sha256=p['sha256'], index_path=index['path'], index_sha256=index['sha256'],
                    audit_path=audit['path'], audit_sha256=audit['sha256']), parent, old

    def test_real_small_merge_keeps_gaps_separate_and_unrelated_records_exact(self):
        arguments, parent, _ = self.bundle()
        output = reader.build(**arguments)
        self.assertEqual(output['schema'], 'ndx_corrected_base_overlay_limited_drift_v3')
        self.assertEqual(output['records'][1:], parent['records'][1:])
        self.assertEqual(len(output['historical_price_cache_gap_observations']), 26)
        self.assertNotIn('source_hashes', output)
        self.assertTrue(output['base_numerical_source_closure_verified'])
        self.assertFalse(output['historical_full_source_closure_verified'])
        self.assertFalse(set(self.exceptions) & set(output['verified_source_hashes']))
        self.assertEqual(output['historical_expected_source_hashes'], parent['source_hashes'])

    def test_exception_cannot_hide_strict_base_dependency_drift(self):
        path = next(iter(self.exceptions))
        old = self.exceptions[path]['expected_historical_sha256']
        with self.assertRaisesRegex(ValueError, 'Strict BASE'):
            reader.verify_partitions(verified={path: old}, historical={path: old}, contract=self.contract)

    def test_unlisted_source_or_different_old_hash_rejected(self):
        path = next(iter(self.exceptions))
        with self.assertRaisesRegex(ValueError, 'Different historical SHA'):
            reader.verify_partitions(verified={}, historical={path: '0' * 64}, contract=self.contract)
        other = self.root / 'unexpected.csv'
        other.write_bytes(b'new')
        with self.assertRaisesRegex(ValueError, 'Non-exempt'):
            reader.verify_partitions(verified={}, historical={str(other): '0' * 64}, contract=self.contract)

    def test_gap_changed_during_actual_atomic_publication_is_rejected(self):
        arguments, _, _ = self.bundle()
        output = reader.build(**arguments)
        original = reader.publish
        def publish_then_change(path, value):
            saved = original(path, value)
            Path(next(iter(self.exceptions))).write_bytes(b'changed again')
            return saved
        with patch.object(reader, 'publish', side_effect=publish_then_change):
            with self.assertRaisesRegex(ValueError, 'changed again'):
                reader.publish_verified(self.root / 'published.json', output)

    def test_changed_original_checkpoint_is_not_a_price_cache_exception(self):
        arguments, _, old = self.bundle()
        Path(old['path']).write_bytes(b'changed original numerical source')
        with self.assertRaisesRegex(ValueError, 'Strict BASE'):
                reader.build(**arguments)

    def test_rehashed_caller_audit_cannot_replace_hard_inventory_entry(self):
        arguments, _, _ = self.bundle()
        path = Path(arguments['audit_path'])
        changed = json.loads(path.read_bytes())
        changed['extra_forged_claim'] = True
        path.write_text(json.dumps(changed))
        arguments['audit_sha256'] = sha(path)
        with self.assertRaisesRegex(ValueError, 'differs from hard fifteen-date'):
            reader.build(**arguments)

    def test_publication_rejects_omitted_loaded_source(self):
        arguments, _, _ = self.bundle()
        value = reader.build(**arguments)
        del value['verified_source_hashes'][str(Path(reader.__file__).resolve())]
        with self.assertRaisesRegex(ValueError, 'partition omitted'):
            reader.publish_verified(self.root / 'bad.json', value)


if __name__ == '__main__':
    unittest.main()
