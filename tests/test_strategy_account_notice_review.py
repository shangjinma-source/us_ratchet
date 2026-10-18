import unittest
from data.strategy_account_notice_review import review_notices


class NoticeTests(unittest.TestCase):
    def check(self,title,body='',ticker='AMD',names=()):
        raw=('<rss><channel><item><title>'+title+'</title><description>'+body+
             '</description><pubDate>Fri, 01 Mar 2024 12:00:00 GMT</pubDate>'
             '<link>https://example/MAR</link><guid>MAR</guid></item></channel></rss>').encode()
        return review_notices(raw,ticker=ticker,issuer_names=names)

    def test_dates_and_links_never_identity(self):
        self.assertEqual(self.check('Unrelated',ticker='MAR')['matches'],[])

    def test_exact_etf_title_retained_but_underlying_body_blocks(self):
        title='ETP2025-08 - Nasdaq to Begin Listing Leverage Shares 2X Long AMD Daily ETF on Friday, January 24, 2025'
        result=self.check(title)
        self.assertFalse(result['blocking'])
        self.assertEqual(result['matches'][0]['disposition'],'ETF_LISTING_TITLE_UNDERLYING_MENTION')
        self.assertTrue(self.check(title,'AMD announces a stock split')['blocking'])
        self.assertTrue(self.check(title.replace('January 24','January 25'))['blocking'])
        self.assertTrue(self.check(title+' and AMD split')['blocking'])

    def test_ordinary_issuer_and_future_notices_block(self):
        for title in ['AMD announces split','AMD future name change effective in 2027']:
            self.assertTrue(self.check(title)['blocking'])
        title='ETP2025-08 - Nasdaq to Begin Listing Advanced Micro Devices ETF on Friday, January 24, 2025'
        self.assertTrue(self.check(title,names=['Advanced Micro Devices'])['blocking'])
        self.assertTrue(self.check('Unrelated','Advanced Micro Devices announces split',names=['Advanced Micro Devices'])['blocking'])


if __name__=='__main__':unittest.main()
