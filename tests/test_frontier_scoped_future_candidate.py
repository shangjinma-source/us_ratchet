import importlib.util
from pathlib import Path
from datetime import datetime, timezone
import unittest
from xml.sax.saxutils import escape
from scripts.current_research_official_alert_capture import parse_official_feed

path=Path(__file__).resolve().parents[1]/'data/saved_frontier_first_window_v1.py'
spec=importlib.util.spec_from_file_location('scoped_future_candidate',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ScopedFutureTests(unittest.TestCase):
    def raw(self, notices=None, channel='Tue, 27 Oct 2026 16:20:43 GMT'):
        if notices is None:
            notices=[dict(identifier=k,category=v[0],title=v[1],description=v[2],date='Tue, 27 Oct 2026 19:30:00 GMT') for k,v in module.VERIFIED_UNRELATED_FUTURE_NOTICES.items()]
        items=[]
        for row in notices:
            items.append('<item><title>'+escape(row['title'])+'</title><NewsCategory>'+escape(row['category'])+'</NewsCategory><link>http://www.nasdaqtrader.com/TraderNews.aspx?id='+row['identifier']+'</link><description>'+escape(row['description'])+'</description><pubDate>'+row['date']+'</pubDate></item>')
        return ('<rss><channel><pubDate>'+channel+'</pubDate>'+''.join(items)+'</channel></rss>').encode()
    def check(self,raw,ticker='MRNA',names=('Moderna, Inc.',)):
        feed=parse_official_feed(raw,observed_at=datetime(2026,10,27,16,21,39,tzinfo=timezone.utc))
        return module.review_future_notice_scope(raw,feed=feed,ticker=ticker,issuer_names=names)
    def test_two_observed_unrelated_notices_retain_times(self):
        result=self.check(self.raw())
        self.assertEqual(len(result['ignored_future_items']),2)
        self.assertEqual(result['ignored_future_items'][0]['published_at_utc'],'2026-10-27T19:30:00+00:00')
        self.assertFalse(result['original_times_modified'])
        self.assertEqual(self.check(self.raw(),ticker='SNDK',names=('Sandisk Corporation',))['ticker'],'SNDK')
    def test_target_issuer_or_ticker_even_in_description_blocks(self):
        raw=self.raw().replace(b'UTP - SIP',b'UTP - SIP Moderna, Inc.')
        with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(raw)
        raw=self.raw().replace(b'UTP - SIP',b'UTP - SIP MRNA')
        with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(raw)
    def test_unknown_future_and_known_category_other_title_block(self):
        for raw in (self.raw().replace(b'UTP Vendor Alert',b'Unknown Category'),self.raw().replace(b'2027 Failover',b'2028 Failover')):
            with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(raw)
    def test_channel_future_blocks(self):
        with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(self.raw(channel='Tue, 27 Oct 2026 20:00:00 GMT'))
    def test_actual_target_corporate_action_notice_still_blocks(self):
        for date in ('Tue, 27 Oct 2026 16:00:00 GMT','Tue, 27 Oct 2026 19:30:00 GMT'):
            raw=self.raw([dict(identifier='ECA2026-1',category='Equity Corporate Actions Alert',title='MRNA cash dividend',description='Moderna, Inc. announces a cash dividend',date=date)])
            with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(raw)
    def test_invalid_time_and_changed_other_issuer_description_block(self):
        for raw in (self.raw().replace(b'19:30:00 GMT',b'bad-time'),self.raw().replace(b'#2026-175 NTX',b'#2026-175 NTX new unknown action')):
            with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(raw)

if __name__=='__main__':unittest.main()
