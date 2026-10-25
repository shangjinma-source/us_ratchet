"""Formal per-operation market/action provider through real capital blob publication."""
import unittest
from hashlib import sha256
from data.strategy_capital_capture_provider_v2 import capital_capture_provider
import test_strategy_capital_arrival_actual_v2 as actual

class MarketV2CapitalIntegration(unittest.TestCase):
 def test_market_v2_through_selection_blob_recovery_publication(self):
  def capture(runtime):
   actions=runtime.execution_provider.__self__.actions
   original_rss=actions.rss_fetch
   def complete_rss():
    response=dict(original_rss())
    response['body']=response['body'].replace(b'<channel>',b'<channel><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate>',1)
    return response
   actions.rss_fetch=complete_rss
   selected=capital_capture_provider(runtime)
   def collect(state):
    evidence=selected(state)
    for name,raw in [('large-one',b'a'*(28*1024*1024)),('large-two',b'b'*(28*1024*1024))]:
     evidence['source_package']['files'][name]=raw
     evidence['source_package']['source_hashes'][name]=sha256(raw).hexdigest()
    return evidence
   return collect
  fixture=actual.ArrivalActualProviderTests();fixture.capture_builder=capture
  fixture.test_actual_continuous32_prepared_publication_only_recovery()
if __name__=='__main__':unittest.main()
