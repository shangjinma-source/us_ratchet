import importlib.util,os,unittest
from pathlib import Path
from datetime import datetime,timezone
from xml.sax.saxutils import escape
from scripts.current_research_official_alert_capture import parse_official_feed
p=Path(os.environ.get('ECA772_CANDIDATE','data/saved_frontier_first_window_v1.py'));spec=importlib.util.spec_from_file_location('eca772',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ScopeTests(unittest.TestCase):
 def row(self):return dict(news_category='Equity Corporate Actions Alert',title='ECA2026-772 - Information Regarding the Formation of a Holding Company for Navient Corporation (NAVI & JSM)',description_summary='News Category Alert Markets What You Need To Know Equity Corporate Actions Alert #2026-772 The Nasdaq Stock Market',link='http://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-772',description_truncated=False)
 def test_only_two_reviewed_targets_and_all_affected_securities(self):
  for ticker,names in [('MRNA',['Moderna, Inc.']),('SNDK',['Sandisk Corporation'])]:
   r=m.reviewed_eca_772_scope(self.row(),ticker=ticker,issuer_names=names);self.assertEqual([s['ticker'] for s in r['securities']],['NAVI','JSM']);self.assertFalse(r['runtime_full_body_refetched'])
  for ticker,names in [('NAVI',['Navient Corporation']),('JSM',['Navient LLC']),('OTHER',['Other']),('MRNA',[]),('SNDK',['Sandisk','Other'])]:self.assertIsNone(m.reviewed_eca_772_scope(self.row(),ticker=ticker,issuer_names=names))
 def test_every_signature_field_is_required(self):
  for field in self.row():
   row=self.row();row[field]=True if field=='description_truncated' else 'different';self.assertIsNone(m.reviewed_eca_772_scope(row,ticker='MRNA',issuer_names=['Moderna']))
 def test_full_gate_preserves_future_channel_and_other_notice_rejection(self):
  row=self.row()
  def raw(channel,title):return ('<rss><channel><pubDate>'+channel+'</pubDate><item><title>'+escape(title)+'</title><NewsCategory>'+row['news_category']+'</NewsCategory><link>'+escape(row['link'])+'</link><description>'+escape(row['description_summary'])+'</description><pubDate>Wed, 28 Oct 2026 21:00:20 GMT</pubDate></item></channel></rss>').encode()
  for channel,title,passes in [('Wed, 28 Oct 2026 18:00:00 GMT',row['title'],True),('Wed, 28 Oct 2026 22:00:00 GMT',row['title'],False),('Wed, 28 Oct 2026 18:00:00 GMT',row['title']+' Moderna',False)]:
   b=raw(channel,title);feed=parse_official_feed(b,observed_at=datetime(2026,10,28,18,38,tzinfo=timezone.utc))
   if passes:self.assertEqual(len(m.review_future_notice_scope(b,feed=feed,ticker='MRNA',issuer_names=['Moderna'])['ignored_future_items']),1)
   else:
    with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION_REVIEW'):m.review_future_notice_scope(b,feed=feed,ticker='MRNA',issuer_names=['Moderna'])
if __name__=='__main__':unittest.main()
