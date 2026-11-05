from copy import deepcopy
from datetime import datetime, timezone
from xml.sax.saxutils import escape
import unittest

from data.saved_frontier_first_window_v1 import (
    VERIFIED_UNRELATED_FUTURE_NOTICES, review_future_notice_scope,
)
from scripts.current_research_official_alert_capture import parse_official_feed


class ReviewedIssuerNoticeTests(unittest.TestCase):
    def test_reviewed_notices_and_fail_closed_variants(self):
        for identifier in ('ECA2026-802', 'ECA2026-799', 'eca2026-798', 'ECA2026-796', 'ECA2026-800'):
            category, title, description = VERIFIED_UNRELATED_FUTURE_NOTICES[identifier]
            raw = ('<rss><channel><pubDate>Thu, 05 Nov 2026 18:00:00 GMT</pubDate>'
                   '<item><title>' + escape(title) + '</title><link>'
                   'http://www.nasdaqtrader.com/TraderNews.aspx?id=' + identifier +
                   '</link><pubDate>Thu, 05 Nov 2026 23:00:00 GMT</pubDate>'
                   '<description>' + escape(description) + '</description></item></channel></rss>').encode()
            feed = parse_official_feed(raw, observed_at=datetime(2026, 11, 5, 18, 10, tzinfo=timezone.utc))
            feed['items'][0]['news_category'] = category
            for ticker, names in [('SNDK', ['Sandisk Corporation']), ('MRNA', ['Moderna Inc'])]:
                def review(document=raw, parsed=feed):
                    return review_future_notice_scope(document, feed=parsed, ticker=ticker, issuer_names=names)
                with self.subTest(identifier=identifier, ticker=ticker):
                    self.assertEqual(len(review()['ignored_future_items']), 1)
                    for key, value in [('title', 'Changed'), ('description_summary', 'Changed'),
                                       ('link', 'http://example.org'), ('description_truncated', True)]:
                        changed = deepcopy(feed)
                        changed['items'][0][key] = value
                        with self.assertRaises(ValueError):
                            review(parsed=changed)
                    with self.assertRaises(ValueError):
                        review(document=raw.replace(b'</description>', (' ' + ticker + ' split</description>').encode()))
                    changed = deepcopy(feed)
                    changed['channel']['future_publication'] = True
                    with self.assertRaises(ValueError):
                        review(parsed=changed)


if __name__ == '__main__':
    unittest.main()
