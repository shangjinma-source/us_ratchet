import unittest
from unittest.mock import patch
from data import roa_current_signal as provider

class CurrentSignalTests(unittest.TestCase):
    def test_real_frozen_sources_and_identity(self):
        signal=provider.load_current_signal(as_of_date='2026-11-06')
        self.assertEqual(signal['training_dependency_count'],1144)
        self.assertEqual(len(signal['securities']),10)
        self.assertFalse(signal['executable'])
        self.assertEqual(signal['execution_not_before_session'],'2026-11-06')
        self.assertTrue(all(r['security_id'] in signal['weights'] for r in signal['securities']))

    def test_signal_bytes_must_match_server_pin(self):
        with self.assertRaisesRegex(ValueError,'CURRENT_SIGNAL_CHANGED'):
            provider.load_current_signal(as_of_date='2026-11-06',expected_signal_sha256='0'*64)

    def test_cannot_reuse_stale_market_state_next_session(self):
        with self.assertRaisesRegex(ValueError,'SESSION_NOT_SUPPORTED'):
            provider.load_current_signal(as_of_date='2026-11-09')

    def test_changed_dependency_rejected(self):
        original=provider._read
        def changed(root,name):
            result=original(root,name)
            if 'raw_companyfacts' in name:return result+b' '
            return result
        with patch.object(provider,'_read',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'DEPENDENCY_CHANGED'):
                provider.load_current_signal(as_of_date='2026-11-06')

    def test_server_contract_pin_is_enforced(self):
        with self.assertRaisesRegex(ValueError,'CONTRACT_CHANGED'):
            provider.load_current_signal(as_of_date='2026-11-06',expected_contract_hashes={})

if __name__=='__main__':unittest.main()
