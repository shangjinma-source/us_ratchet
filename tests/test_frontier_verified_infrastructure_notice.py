"""Exact reviewed infrastructure signature only; no broad ETA exemption."""
import importlib.util,os,unittest
from datetime import datetime,timezone
from xml.sax.saxutils import escape
from scripts.current_research_official_alert_capture import parse_official_feed
candidate=os.environ.get('FRONTIER_SCOPE_TEST_CANDIDATE_PATH')
if candidate:
    spec=importlib.util.spec_from_file_location('eta_scope_candidate',candidate)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
else:
    from data import saved_frontier_first_window_v1 as module

class EtaScopeTests(unittest.TestCase):
    def raw(self):
        return ('<rss><channel><pubDate>Tue, 27 Oct 2026 19:34:03 GMT</pubDate><item>'
        '<title>ETA2026-61 - UPDATED: FINRA/Nasdaq TRF Software Change Scheduled for November 2, 2026</title>'
        '<NewsCategory>Equity Trader Alert</NewsCategory><link>http://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2026-61</link>'
        '<description>News Category Alert Markets What You Need To Know Equity Trader Alert #2026-061 Post - Trade</description>'
        '<pubDate>Tue, 27 Oct 2026 23:00:00 GMT</pubDate></item></channel></rss>').encode()
    def check(self,raw,truncate=False):
        feed=parse_official_feed(raw,observed_at=datetime(2026,10,27,19,34,27,tzinfo=timezone.utc))
        if truncate:feed['items'][0]['description_truncated']=True
        return module.review_future_notice_scope(raw,feed=feed,ticker='MRNA',issuer_names=['Moderna, Inc.'])
    def test_exact_retains_future_time(self):
        result=self.check(self.raw())
        self.assertEqual(result['ignored_future_items'][0]['identifier'],'ETA2026-61')
        self.assertEqual(result['ignored_future_items'][0]['published_at_utc'],'2026-10-27T23:00:00+00:00')
        self.assertFalse(result['original_times_modified'])
    def test_target_mentions_block(self):
        for name in (b'MRNA',b'Moderna, Inc.'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                self.check(self.raw().replace(b'Post - Trade',b'Post - Trade '+name))
    def test_signature_changes_block(self):
        changes=[(b'Equity Trader Alert',b'Equity Technical Update'),(b'November 2,',b'November 3,'),(b'id=ETA2026-61',b'id=ETA2026-62'),(b'Post - Trade',b'Post Trade')]
        for old,new in changes:
            with self.subTest(old=old),self.assertRaises(ValueError):self.check(self.raw().replace(old,new))
    def test_truncation_channel_future_and_invalid_time_block(self):
        with self.assertRaises(ValueError):self.check(self.raw(),truncate=True)
        with self.assertRaises(ValueError):self.check(self.raw().replace(b'19:34:03',b'23:34:03'))
        with self.assertRaises(ValueError):self.check(self.raw().replace(b'23:00:00 GMT',b'invalid'))

if __name__=='__main__':unittest.main()
