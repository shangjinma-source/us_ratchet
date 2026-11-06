import unittest
from datetime import timedelta
from test_roa_quote_provider_20261106 import QuoteTests
class WaitTests(QuoteTests):
 def test_wait_until_real_clock_reaches_quote(self):
  self.payload['chart']['result'][0]['meta']['regularMarketTime']=int(self.now.timestamp())+2
  waits=[]
  def wait(seconds):waits.append(seconds);self.now+=timedelta(seconds=seconds)
  self.provider.wait=wait
  result=self.run_quote();self.assertEqual(len(waits),1);self.assertGreaterEqual(self.now.timestamp(),int(self.payload['chart']['result'][0]['meta']['regularMarketTime']));self.assertEqual(result['marks']['sid']['price'],'101')
 def test_large_future_does_not_wait(self):
  self.payload['chart']['result'][0]['meta']['regularMarketTime']=int(self.now.timestamp())+4
  self.provider.wait=lambda _:self.fail('must not wait')
  with self.assertRaisesRegex(ValueError,'WAIT_FRESH_QUOTE'):self.run_quote()
 def test_no_clock_advance_remains_rejected(self):
  self.payload['chart']['result'][0]['meta']['regularMarketTime']=int(self.now.timestamp())+2
  self.provider.wait=lambda _:None
  with self.assertRaisesRegex(ValueError,'WAIT_FRESH_QUOTE'):self.run_quote()
if __name__=='__main__':unittest.main()
