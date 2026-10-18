import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_latest_all_k_completed_independent_audit_v2_20260919 as m


class PrefixAuditReview(unittest.TestCase):
    def value(self):
        return dict(schema='LATEST_ALL_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1', historical_expected_source_hashes=dict(m.LOADED), archive_resolution={}, **dict.fromkeys(m.FALSE, False))

    def test_publication_cannot_upgrade_scope_or_accept_foreign_schema(self):
        attacks = [('schema', 'UNRELATED'), ('schema', None), ('schema', 0)]
        attacks += [(key, bad) for key in m.FALSE for bad in (True, 0, None, 'False')]
        attacks += [(key, 'MISSING') for key in ('schema', *m.FALSE)]
        for key, bad in attacks:
            with self.subTest(key=key, bad=bad), tempfile.TemporaryDirectory() as directory:
                value = self.value()
                if bad == 'MISSING':
                    del value[key]
                else:
                    value[key] = bad
                target = Path(directory) / 'audit.json'
                with patch.object(m.archive, 'load_contract', side_effect=AssertionError('Invalid authority reached source IO')), self.assertRaises(ValueError):
                    m.publish_verified(target, value)
                self.assertFalse(target.exists())

    def test_valid_false_preserves_source_guards_and_exclusive_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'audit.json'
            value = self.value()
            with patch.object(m.archive, 'load_contract', return_value={}) as load, patch.object(m.archive, 'verify_expected_sources', return_value={}) as verify:
                result = m.publish_verified(target, value)
                self.assertEqual(json.loads(target.read_bytes()), value)
                self.assertEqual(result['path'], str(target.resolve()))
                self.assertEqual(load.call_count, 2)
                self.assertEqual(verify.call_count, 2)
                for call in verify.call_args_list:
                    self.assertEqual(call.args, (value['historical_expected_source_hashes'], {}))
                with self.assertRaises(FileExistsError):
                    m.publish_verified(target, value)

    def test_valid_scope_does_not_bypass_omitted_or_drifted_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'audit.json'
            value = self.value()
            value['historical_expected_source_hashes'].pop(next(iter(m.LOADED)))
            with patch.object(m.archive, 'load_contract', side_effect=AssertionError('Omitted source reached IO')), self.assertRaisesRegex(ValueError, 'Audit source omitted'):
                m.publish_verified(target, value)
            self.assertFalse(target.exists())
            with patch.object(m.archive, 'load_contract', return_value={}), patch.object(m.archive, 'verify_expected_sources', return_value={'drift': True}), self.assertRaisesRegex(ValueError, 'Source drift'):
                m.publish_verified(target, self.value())
            self.assertFalse(target.exists())
            with patch.object(m.archive, 'load_contract', return_value={}), patch.object(m.archive, 'verify_expected_sources', side_effect=[{}, {'drift': True}]), self.assertRaisesRegex(ValueError, 'Source drift after publication'):
                m.publish_verified(target, self.value())
            self.assertTrue(target.exists())


if __name__ == '__main__':
    unittest.main()
