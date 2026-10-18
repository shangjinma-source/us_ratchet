import unittest
from unittest.mock import patch
from scripts import ndx_current92_sec_identity_readback_20260919 as module


class Tests(unittest.TestCase):
    def test_real_complete_sources_and_all_101_current_observations(self):
        report=module.build()
        self.assertEqual((report['ticker_count'],report['issuer_count']),(101,100))
        self.assertEqual((report['refreshed_ticker_count'],report['reused_prior_current_ticker_count']),(92,9))
        self.assertTrue(report['all_current_ciks_match_july_candidate_ciks'])
        for row in report['rows']:
            self.assertFalse(row['historical_cusip_verified']);self.assertFalse(row['provider_price_identity_bound'])

    def test_manifest_and_raw_hash_cannot_be_resigned_locally(self):
        with patch.object(module,'MANIFEST_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'Bound bytes'):module.build()
        original=module.nine.read
        def injected(path,sha,sources):
            result=original(path,sha,sources)
            if str(path)==str(module.MANIFEST):result['captures'][0]['raw_sha256']='0'*64
            return result
        with patch.object(module.nine,'read',side_effect=injected):
            with self.assertRaisesRegex(ValueError,'raw binding'):module.build()


if __name__=='__main__':unittest.main()
