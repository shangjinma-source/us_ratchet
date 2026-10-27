import importlib.util
from pathlib import Path
from datetime import datetime, timezone
from copy import deepcopy
import unittest
from scripts.current_research_official_alert_capture import parse_official_feed
from xml.sax.saxutils import escape
path=Path(__file__).resolve().parents[1]/'data/saved_frontier_first_window_v1.py'
spec=importlib.util.spec_from_file_location('eca_candidate',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class EcaTests(unittest.TestCase):
    def row(self,issuer='Solowin Holdings',symbol='AXG',number='768',par=True):
        action='Reverse Stock Split, Par Value and CUSIP Number Change' if par else 'Reverse Stock Split and CUSIP Number Change'
        return dict(title=f'ECA2026-{number} - Information Regarding the {action} for {issuer} ({symbol})',news_category='Equity Corporate Actions Alert',link=f'http://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-{number}',description_summary=f'News Category Alert Markets What You Need To Know Equity Corporate Actions Alert #2026-{number} The Nasdaq Stock Market',description_truncated=False)
    def check(self,row):return m.other_issuer_eca_scope(row,ticker='MRNA',issuer_names=['Moderna, Inc.','Moderna'])
    def full(self,row,channel='Tue, 27 Oct 2026 17:00:00 GMT'):
        raw=('<rss><channel><pubDate>'+channel+'</pubDate><item><title>'+escape(row['title'])+'</title><NewsCategory>'+row['news_category']+'</NewsCategory><link>'+escape(row['link'])+'</link><description>'+escape(row['description_summary'])+'</description><pubDate>Tue, 27 Oct 2026 21:00:00 GMT</pubDate></item></channel></rss>').encode()
        feed=parse_official_feed(raw,observed_at=datetime(2026,10,27,17,7,tzinfo=timezone.utc))
        return m.review_future_notice_scope(raw,feed=feed,ticker='MRNA',issuer_names=['Moderna, Inc.'])
    def test_observed_cases_and_same_template_new_id(self):
        for row in (self.row(),self.row('Odyssey Marine Exploration, Inc','OMEX','767',False),self.row('Example Corporation','EXMP','999',False)):
            self.assertIsNotNone(self.check(row));r=self.full(row);self.assertEqual(len(r['ignored_future_items']),1)
            self.assertFalse(r['ignored_future_items'][0]['scope_classification']['full_body_reviewed_for_this_item'])
    def test_target_name_punctuation_alias_and_target_ticker_reject(self):
        for issuer,symbol in [('Moderna, Inc','OTHER'),('MODERNA INC.','OTHER'),('Moderna Holdings','OTHER'),('Other Company','MRNA')]:
            row=self.row(issuer,symbol);self.assertIsNone(self.check(row))
            with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.full(row)
    def test_multi_issuer_unknown_action_category_and_inconsistent_metadata(self):
        rows=[self.row('Alpha and Beta','ZZZ'),self.row('Alpha, Beta','ZZZ'),self.row('Alpha formerly Beta','ZZZ')]
        for key,value in [('title',self.row()['title'].replace('Reverse Stock Split','Merger')),('news_category','Unknown'),('link','http://evil.example/'),('description_summary','different'),('description_truncated',True)]:
            row=self.row();row[key]=value;rows.append(row)
        for row in rows:self.assertIsNone(self.check(row))
    def test_empty_or_unusable_issuer_identity_rejects(self):
        for names in ([],[''],['...','---'],[None]):
            self.assertIsNone(m.other_issuer_eca_scope(self.row(),ticker='MRNA',issuer_names=names))

    def test_channel_future_target_description_and_missing_field_reject(self):
        with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.full(self.row(),channel='Tue, 27 Oct 2026 23:00:00 GMT')
        row=self.row();row['description_summary']+=' Moderna, Inc.'
        with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.full(row)
        row=self.row();del row['link'];self.assertIsNone(self.check(row))
if __name__=='__main__':unittest.main()
