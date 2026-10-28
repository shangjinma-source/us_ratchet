"""Single body-reviewed merger notice; target identity and source boundaries."""
import importlib.util,os,unittest
from datetime import datetime,timezone
from scripts.current_research_official_alert_capture import parse_official_feed
candidate=os.environ.get('FRONTIER_SCOPE_TEST_CANDIDATE_PATH')
if candidate:
 spec=importlib.util.spec_from_file_location('eca776_candidate',candidate);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
else:
 from data import saved_frontier_first_window_v1 as module

class ReviewedMergerTests(unittest.TestCase):
 def raw(self):
  return b'<rss><channel><pubDate>Wed, 28 Oct 2026 17:50:04 GMT</pubDate><item><title>ECA2026-776 - Information Regarding the Business Combination of Adial Pharmaceuticals, Inc. (ADIL) and Azora Therapeutics, Inc.</title><NewsCategory>Equity Corporate Actions Alert</NewsCategory><description>News Category Alert Markets What You Need To Know Equity Corporate Actions Alert #2026-776 The Nasdaq Stock Market</description><link>http://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-776</link><pubDate>Wed, 28 Oct 2026 21:01:30 GMT</pubDate></item></channel></rss>'
 def check(self,raw=None,ticker='MRNA',names=None,truncated=False):
  raw=raw or self.raw();feed=parse_official_feed(raw,observed_at=datetime(2026,10,28,18,tzinfo=timezone.utc))
  if truncated:feed['items'][0]['description_truncated']=True
  return module.review_future_notice_scope(raw,feed=feed,ticker=ticker,issuer_names=['Moderna, Inc.'] if names is None else names)
 def test_exact_two_targets_body_identity_and_original_time(self):
  for ticker,names in [('MRNA',['Moderna, Inc.']),('SNDK',['Sandisk Corporation'])]:
   result=self.check(ticker=ticker,names=names);item=result['ignored_future_items'][0];scope=item['scope_classification']
   self.assertEqual(scope['old_cusip'],'00688A304');self.assertEqual(scope['new_cusip'],'054800107');self.assertEqual(scope['reviewed_body_sha256'],'ff54d7bf01f508daf178f24e1b81b539711f4039cab697faaf2ae3aa0bb485ec');self.assertEqual(item['published_at_utc'],'2026-10-28T21:01:30+00:00');self.assertFalse(result['original_times_modified'])
 def test_parties_unknown_identity_and_other_targets_rejected(self):
  for ticker,names in [('ADIL',['Adial Pharmaceuticals, Inc.']),('AZR',['Azora Therapeutics, Inc.']),('MRNA',[]),('MRNA',['Azora Therapeutics, Inc.']),('UNKNOWN',['Unknown Inc.'])]:
   with self.subTest(ticker=ticker,names=names),self.assertRaises(ValueError):self.check(ticker=ticker,names=names)
 def test_signature_truncation_and_channel_time_fail_closed(self):
  for old,new in [(b'Adial Pharmaceuticals',b'Moderna'),(b'Azora Therapeutics',b'Sandisk'),(b'id=ECA2026-776',b'id=ECA2026-778'),(b'Business Combination',b'Merger'),(b'The Nasdaq Stock Market',b'The Nasdaq Stock Market MRNA'),(b'17:50:04',b'22:50:04')]:
   with self.subTest(old=old),self.assertRaises(ValueError):self.check(self.raw().replace(old,new))
  with self.assertRaises(ValueError):self.check(truncated=True)

if __name__=='__main__':unittest.main()
