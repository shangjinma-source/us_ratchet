from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import unittest
from data import saved_frontier_first_window_v1 as original
from scripts.current_research_official_alert_capture import parse_official_feed
spec=importlib.util.spec_from_file_location('candidate','docs/candidates/saved_frontier_first_window_dtn26_20261106.py')
candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
class NoticeTests(unittest.TestCase):
 def setUp(self):
  category,title,description=candidate.VERIFIED_UNRELATED_FUTURE_NOTICES['DTN2026-26']
  self.raw=('<rss><channel><pubDate>Thu, 05 Nov 2026 17:00:00 GMT</pubDate><item><title>'+title+'</title><link>http://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2026-26</link><pubDate>Thu, 05 Nov 2026 20:00:00 GMT</pubDate><category>'+category+'</category><description>'+description+'</description></item></channel></rss>').encode()
  self.feed=parse_official_feed(self.raw,observed_at=datetime(2026,11,5,17,30,tzinfo=timezone.utc))
  # Category extraction in production parser is description-driven; exact observed row supplied.
  self.feed['items'][0]['news_category']=category
 def review(self,raw=None,feed=None):
  return candidate.review_future_notice_scope(raw or self.raw,feed=feed or self.feed,ticker='SNDK',issuer_names=['Sandisk Corporation'])
 def test_exact_notice(self):
  result=self.review();self.assertEqual(len(result['ignored_future_items']),1)
 def test_changed_and_truncated_rejected(self):
  for key,value in [('description_summary','changed'),('description_truncated',True),('link','http://example.org'),('title','changed')]:
   feed=deepcopy(self.feed);feed['items'][0][key]=value
   with self.assertRaises(ValueError):self.review(feed=feed)
 def test_target_mention_still_blocked(self):
  with self.assertRaises(ValueError):self.review(raw=self.raw.replace(b'</description>',b' SNDK split</description>'))
 def test_future_channel_still_blocked(self):
  feed=deepcopy(self.feed);feed['channel']['future_publication']=True
  with self.assertRaises(ValueError):self.review(feed=feed)
if __name__=='__main__':unittest.main()
