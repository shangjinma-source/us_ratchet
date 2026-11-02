import unittest
import xml.etree.ElementTree as ET

from data.strategy_account_notice_review import review_notices
from data.strategy_compiled_notice_review_v1 import CompiledNoticeReview


class CompiledNoticeTests(unittest.TestCase):
    def test_exact_audit_order_and_listing_exemptions(self):
        raw = b'''<rss xmlns:c="urn:content"><channel>
        <item><title>ETP2026-1 - Nasdaq to Begin Listing ABC ETF on Monday, November 2, 2026</title>
        <description>ABC shares and Issuer &amp; Company</description></item>
        <item><title>ETP2026-2 - Nasdaq to Begin Listing ABC ETF on Tuesday, November 2, 2026</title></item>
        <item><title>ABC</title><title>duplicate title</title><c:encoded>&lt;b&gt;abc&lt;/b&gt;</c:encoded></item>
        <item><link>https://ABC.example</link><pubDate>ABC</pubDate><summary>XABC ABC2 x-ABC-x</summary></item>
        </channel></rss>'''
        reviewer = CompiledNoticeReview(raw)
        for ticker, names in [('ABC', ['Issuer & Company', 'ABC']), ('abc', []), ('XABC', ['absent'])]:
            self.assertEqual(reviewer.review(ticker=ticker, issuer_names=names),
                             review_notices(raw, ticker=ticker, issuer_names=names))
        result = reviewer.review(ticker='ABC', issuer_names=[])
        self.assertTrue(result['blocking'])
        self.assertEqual(sum(row['disposition'] == 'ETF_LISTING_TITLE_UNDERLYING_MENTION'
                             for row in result['matches']), 1)

    def test_no_cross_body_or_result_state(self):
        first = CompiledNoticeReview(b'<rss><item><title>ABC</title></item></rss>')
        second = CompiledNoticeReview(b'<rss><item><title>XYZ</title></item></rss>')
        result = first.review(ticker='ABC', issuer_names=[])
        result['matches'][0]['title'] = 'tampered'
        self.assertEqual(first.review(ticker='ABC', issuer_names=[])['matches'][0]['title'], 'ABC')
        self.assertEqual(second.review(ticker='ABC', issuer_names=[]), dict(blocking=[], matches=[]))

    def test_malformed_xml_rejected(self):
        with self.assertRaises(ET.ParseError):
            CompiledNoticeReview(b'<rss>')


if __name__ == '__main__':
    unittest.main()
