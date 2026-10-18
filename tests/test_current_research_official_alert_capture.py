import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from scripts.current_research_official_alert_capture import capture_official_alerts,parse_official_feed,MAX_BYTES,NoRedirect

NOW=datetime(2026,10,15,12,tzinfo=timezone.utc)
def rss(title='SNDK notice',date='Thu, 15 Oct 2026 11:00:00 GMT'):
    return ('<rss><channel><item><title>'+title+'</title><link>https://external.invalid/notice</link><guid>x</guid><pubDate>'+date+'</pubDate><description>&lt;b&gt;Summary&lt;/b&gt;</description></item></channel></rss>').encode()

class CaptureTests(unittest.TestCase):
    def test_dry_run_and_createonly_fixed_capture(self):
        with tempfile.TemporaryDirectory() as root:
            result=capture_official_alerts('capture',root=root,fetch=lambda:self.fail('dry fetch'))
            self.assertEqual(result['http_calls'],0);self.assertFalse((Path(root)/'capture').exists())
            calls=[]
            def fetch():calls.append(1);return dict(status=200,headers={},body=rss())
            result=capture_official_alerts('capture',root=root,capture=True,fetch=fetch,clock=lambda:NOW)
            self.assertEqual(calls,[1]);self.assertEqual(result['matching_item_indexes'],[0]);self.assertFalse(result['entity_confirmed'])
            self.assertEqual((Path(root)/'capture/response.bin').read_bytes(),rss())
            with self.assertRaises(ValueError):capture_official_alerts('capture',root=root,capture=True,fetch=fetch,clock=lambda:NOW)
            self.assertEqual(calls,[1])
    def test_parser_candidate_not_confirmation_and_publication_times(self):
        result=parse_official_feed(rss('unrelated'),observed_at=NOW)
        self.assertEqual(result['status'],'NO_MATCH_IN_VISIBLE_FEED_NOT_NO_ACTION')
        self.assertFalse(result['coverage_complete'])
        result=parse_official_feed(rss('SanDisk','Fri, 16 Oct 2026 11:00:00 GMT'),observed_at=NOW)
        self.assertTrue(result['items'][0]['future_publication'])
        result=parse_official_feed(rss(date='Thu, 15 Oct 2026 11:00:00'),observed_at=NOW)
        self.assertIsNone(result['items'][0]['published_at_utc'])
        self.assertIsNotNone(result['items'][0]['publication_time_issue'])
    def test_bad_xml_and_oversize_failed_raw_preserved(self):
        cases=[b'<!DOCTYPE rss><rss><channel/></rss>',b'<!ENTITY x "x"><rss/>',b'<html>shell</html>',b'<rss><channel/></rss>',b'x'*(MAX_BYTES+1)]
        with tempfile.TemporaryDirectory() as root:
            for i,raw in enumerate(cases):
                result=capture_official_alerts(str(i),root=root,capture=True,fetch=lambda raw=raw:dict(status=200,body=raw),clock=lambda:NOW)
                self.assertEqual(result['status'],'UNAVAILABLE');self.assertEqual((Path(root)/str(i)/'response.bin').read_bytes(),raw)
    def test_no_redirect_network_retry_or_escape(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,None,None,None))
        with tempfile.TemporaryDirectory() as root:
            for path in ('../escape',str(Path(root)/'absolute')):
                with self.assertRaises(ValueError):capture_official_alerts(path,root=root)
            calls=[]
            def failure():calls.append(1);raise OSError('offline')
            result=capture_official_alerts('fail',root=root,capture=True,fetch=failure,clock=lambda:NOW)
            self.assertEqual(result['status'],'UNAVAILABLE');self.assertEqual(calls,[1]);self.assertTrue((Path(root)/'fail/receipt.json').exists())
            result=capture_official_alerts('redirect',root=root,capture=True,fetch=lambda:dict(status=302,body=b'redirect'),clock=lambda:NOW)
            self.assertEqual(result['status'],'UNAVAILABLE')
    def test_real_load_shape_and_declared_channel_metadata(self):
        def feed(count='715'):
            return (b'<rss xmlns:ndaq="urn:nasdaq"><channel><pubDate>Thu, 15 Oct 2026 21:00:00 GMT</pubDate><ttl>5</ttl><ndaq:numItems>'+count.encode()+b'</ndaq:numItems>'+b'<item><title>Notice</title></item>'*715+b'</channel></rss>')
        result=parse_official_feed(feed(),observed_at=NOW)
        self.assertEqual(len(result['items']),715);self.assertEqual(result['channel']['actual_num_items'],715)
        self.assertEqual(result['channel']['ttl'],'5');self.assertTrue(result['channel']['future_publication'])
        self.assertTrue(result['channel']['declared_count_matches']);self.assertFalse(result['coverage_complete'])
        for count in ('714','-1','invalid',''):
            with self.assertRaises(ValueError):parse_official_feed(feed(count),observed_at=NOW)

    def test_namespaced_category_preserved_and_counted(self):
        raw=b'<rss xmlns:ndaq="urn:nasdaq"><channel><item><title>A</title><ndaq:NewsCategory>ECA</ndaq:NewsCategory></item><item><title>B</title><ndaq:NewsCategory>ETP</ndaq:NewsCategory></item><item><title>C</title></item></channel></rss>'
        result=parse_official_feed(raw,observed_at=NOW)
        self.assertEqual([row['news_category'] for row in result['items']],['ECA','ETP',None])
        self.assertEqual(result['channel']['news_category_counts'],{'ECA':1,'ETP':1,'UNSPECIFIED':1})
        self.assertFalse(result['coverage_complete']);self.assertTrue(result['retention_unknown'])
        duplicate=raw.replace(b'</ndaq:NewsCategory>',b'</ndaq:NewsCategory><ndaq:NewsCategory>ECA</ndaq:NewsCategory>',1)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_ITEM_NEWS_CATEGORY'):parse_official_feed(duplicate,observed_at=NOW)

    def test_maximum_item_count(self):
        raw=b'<rss><channel>'+b'<item><title>Notice</title></item>'*1001+b'</channel></rss>'
        with self.assertRaises(ValueError):parse_official_feed(raw,observed_at=NOW)

if __name__=='__main__':unittest.main()
