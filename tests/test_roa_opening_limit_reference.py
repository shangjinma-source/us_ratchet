import unittest
from test_roa_quote_provider_20261106 import QuoteTests

class OpeningLimitReferenceTests(QuoteTests):
    def test_explicit_single_session_uses_open_not_last(self):
        self.provider.opening_limit_session='2026-11-06'
        result=self.run_quote()
        self.assertEqual(result['limits']['sid']['buy'],'99')
        self.assertEqual(result['limits']['sid']['sell'],'99')
        self.assertEqual(result['marks']['sid']['price'],'101')
        self.assertEqual(result['limit_reference'],'SESSION_OPEN')
        self.assertEqual(result['limits']['sid']['reference_at'],self.open.isoformat())
        self.assertEqual(result['limits']['sid']['observed_at'],result['marks']['sid']['observed_at'])

    def test_other_session_and_close_keep_latest_quote(self):
        self.provider.opening_limit_session='2026-11-05'
        self.assertEqual(self.run_quote()['limits']['sid']['buy'],'101')
        self.provider.opening_limit_session='2026-11-06'
        result=self.provider({},['sid'],'2026-11-06','CLOSE',self.now)
        self.assertEqual(result['limits']['sid']['sell'],'101')
        self.assertEqual(result['limit_reference'],'LATEST_QUOTE')

    def test_opening_limit_does_not_bypass_freshness(self):
        self.provider.opening_limit_session='2026-11-06'
        self.test_stale_last_rejected()

if __name__=='__main__':unittest.main()
