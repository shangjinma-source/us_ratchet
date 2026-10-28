"""Exact ETP177 scope only; unknown listings and target identities remain blocked."""
import os,importlib.util,unittest
from datetime import datetime,timezone
from scripts.current_research_official_alert_capture import parse_official_feed
path=os.environ.get('FRONTIER_SCOPE_TEST_CANDIDATE_PATH')
if path:
 spec=importlib.util.spec_from_file_location('etp177_candidate',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
else:
 from data import saved_frontier_first_window_v1 as module
class Etp177Tests(unittest.TestCase):
 def raw(self):
  return b'<rss><channel><pubDate>Wed, 28 Oct 2026 19:16:00 GMT</pubDate><item><title>ETP2026-177 -  Nasdaq to Begin Listing Two Franklin Templeton ETFs on Thursday, October 29, 2026</title><NewsCategory>Trader Alerts - New ETP Listings</NewsCategory><description>News Category Alert Markets What You Need To Know Trader Alerts - New ETP Listings #2026-177 The Nasdaq Stock Market</description><link>http://www.nasdaqtrader.com/TraderNews.aspx?id=ETP2026-177</link><pubDate>Wed, 28 Oct 2026 22:45:00 GMT</pubDate></item></channel></rss>'
 def check(self,raw=None,ticker='MRNA',names=None,truncated=False):
  raw=self.raw() if raw is None else raw;feed=parse_official_feed(raw,observed_at=datetime(2026,10,28,19,21,tzinfo=timezone.utc))
  if truncated:feed['items'][0]['description_truncated']=True
  return module.review_future_notice_scope(raw,feed=feed,ticker=ticker,issuer_names=['Moderna, Inc.'] if names is None else names)
 def test_exact_current_targets_keep_original_times(self):
  for ticker,names in [('MRNA',['Moderna, Inc.']),('SNDK',['Sandisk Corporation'])]:
   result=self.check(ticker=ticker,names=names);row=result['ignored_future_items'][0]
   self.assertEqual(row['scope_classification']['listed_tickers'],['FBEQ','FIBT']);self.assertEqual(row['published_at_utc'],'2026-10-28T22:45:00+00:00');self.assertFalse(result['original_times_modified'])
 def test_related_or_unknown_target_identity_rejected(self):
  for ticker,names in [('FBEQ',['Franklin Templeton']),('FIBT',['Franklin']),('MRNA',['Franklin Templeton']),('SNDK',[]),('SNDK',['']),('OTHER',['Other Inc.'])]:
   with self.subTest(ticker=ticker,names=names),self.assertRaises(ValueError):self.check(ticker=ticker,names=names)
 def test_changed_signature_truncation_channel_and_target_mentions_rejected(self):
  for old,new in [(b'ETP2026-177',b'ETP2026-178'),(b'Two Franklin',b'Three Franklin'),(b'Franklin Templeton',b'Moderna'),(b'The Nasdaq Stock Market',b'The Nasdaq Stock Market SNDK'),(b'19:16:00',b'23:16:00'),(b'id=ETP2026-177',b'id=ETP2026-176')]:
   with self.subTest(old=old),self.assertRaises(ValueError):self.check(self.raw().replace(old,new))
  with self.assertRaises(ValueError):self.check(truncated=True)
if __name__=='__main__':unittest.main()
