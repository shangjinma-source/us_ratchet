from copy import deepcopy
import unittest
from data import saved_frontier_first_window_v1 as module

ROW = {'index': 0, 'title': 'DTN2026-25 - Information for Market Data Redistributors Regarding Symbol Reuse of SUPN', 'news_category': 'Data Technical News', 'link': 'http://www.nasdaqtrader.com/TraderNews.aspx?id=DTN2026-25', 'guid': '', 'pubDate': 'Tue, 03 Nov 2026 19:00:00 GMT', 'published_at_utc': '2026-11-03T19:00:00+00:00', 'publication_time_issue': None, 'future_publication': True, 'description_summary': 'News Category Alert Markets What You Need To Know Data Technical News #2026-025 The Nasdaq Stock Market On October 15, 2026 , the shareholders of Supernus Pharmaceuticals, Inc. (SUPN) approved the proposed merger with and into a subsidiary of Indivior Pharmaceuticals, Inc. (INDV). As a result of the merger, Supernus Pharmaceuticals, Inc. (SUPN) will be suspended from Nasdaq and Indivior Pharmaceuticals, Inc. will have a name and symbol change to Supernus, Inc., using the symbol SUPN previously used by Supernus Pharmaceuticals, Inc., effective November 3, 2026 . Nasdaq requests that market data redistributors note this is a symbol reuse and history should NOT carry over from the current SUPN to the new SUPN effective Tuesday, November 3, 2026. The history from INDV should carry over to SUPN effective November 3, 2026.', 'description_truncated': False, 'title_match_candidate': False, 'entity_confirmed': False}

class DtnScopeTests(unittest.TestCase):
    def test_verified_targets_only(self):
        for ticker,names in [('SNDK',['Sandisk Corporation']),('MRNA',['Moderna, Inc.'])]:
            self.assertEqual(module.reviewed_dtn_25_scope(ROW,ticker=ticker,issuer_names=names)['identifier'],'DTN2026-25')
        for ticker,names in [('SUPN',['Supernus']),('INDV',['Indivior']),('SNDK',[]),('SNDK',['Unknown'])]:
            self.assertIsNone(module.reviewed_dtn_25_scope(ROW,ticker=ticker,issuer_names=names))
    def test_changed_notice_rejected(self):
        for key,value in [('title',ROW['title']+' changed'),('description_summary',ROW['description_summary']+' MRNA'),('link','https://example.com'),('description_truncated',True),('news_category','Equity Corporate Actions Alert')]:
            row=deepcopy(ROW);row[key]=value
            self.assertIsNone(module.reviewed_dtn_25_scope(row,ticker='MRNA',issuer_names=['Moderna']))
if __name__=='__main__':unittest.main()
