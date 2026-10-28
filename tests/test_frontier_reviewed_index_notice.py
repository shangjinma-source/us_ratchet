"""Synthetic exact-scope regression; no private captures or official full text needed."""
import os,sys,unittest,importlib.util
from pathlib import Path
from datetime import datetime
from copy import deepcopy
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from scripts.current_research_official_alert_capture import parse_official_feed
from xml.sax.saxutils import escape
path=Path(os.environ.get('NEWS_FRONTIER_SCOPE_CANDIDATE','data/saved_frontier_first_window_v1.py'))
spec=importlib.util.spec_from_file_location('indexscope_portable',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class IndexScope(unittest.TestCase):
 def raw(self):
  category,title,description=module.VERIFIED_UNRELATED_FUTURE_NOTICES['fpnews2026-74']
  return ('<rss><channel><pubDate>Wed, 28 Oct 2026 15:35:15 GMT</pubDate><item><title>'+escape(title)+'</title><NewsCategory>'+category+'</NewsCategory><link>http://www.nasdaqtrader.com/TraderNews.aspx?id=fpnews2026-74</link><description>'+description+'</description><pubDate>Wed, 28 Oct 2026 16:00:00 GMT</pubDate></item></channel></rss>').encode()
 def check(self,raw,ticker='MRNA',names=('Moderna, Inc.',),alter=None):
  feed=parse_official_feed(raw,observed_at=datetime.fromisoformat('2026-10-28T15:35:31.823216+00:00'))
  if alter:alter(feed)
  return module.review_future_notice_scope(raw,feed=feed,ticker=ticker,issuer_names=names)
 def test_reviewed_exact_signature_with_preserved_future_and_body_evidence(self):
  row=self.check(self.raw())['ignored_future_items'][0];self.assertEqual(row['published_at_utc'],'2026-10-28T16:00:00+00:00');self.assertEqual(row['scope_classification']['reviewed_body_sha256'],'c73d2260444a8b7360a78762a7432d003ab0cc54edb631f2833f4c0e06ecbacd');self.assertFalse(row['scope_classification']['runtime_full_body_refetched']);self.assertFalse(self.check(self.raw())['original_times_modified'])
 def test_no_id_only_or_category_only_exemption(self):
  for before,after in [(b'Six New Indexes',b'MRNA Dividend'),(b'fpnews2026-74</link>',b'fpnews2026-75</link>'),(b'Financial Products News</NewsCategory>',b'Equity Corporate Actions Alert</NewsCategory>'),(b'#2026-074</description>',b'#2026-074 changed</description>')]:
   with self.subTest(after=after),self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(self.raw().replace(before,after))
 def test_target_mention_still_blocks(self):
  for name in [b'MRNA',b'Moderna',b'SNDK',b'Sandisk']:
   raw=self.raw().replace(b'#2026-074</description>',b'#2026-074 '+name+b'</description>')
   with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(raw,ticker='SNDK' if name in [b'SNDK',b'Sandisk'] else 'MRNA',names=('Sandisk Corporation',) if name in [b'SNDK',b'Sandisk'] else ('Moderna, Inc.',))
 def test_truncated_and_invalid_time_refused(self):
  with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(self.raw(),alter=lambda f:f['items'][0].update(description_truncated=True))
  with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION'):self.check(self.raw().replace(b'16:00:00 GMT',b'not-a-time'))
 def test_same_synthetic_unrelated_index_notice_other_target(self):
  result=self.check(self.raw(),ticker='SNDK',names=('Sandisk Corporation',));self.assertEqual(len(result['ignored_future_items']),1);self.assertFalse(result['issuer_notice_review']['blocking'])
if __name__=='__main__':unittest.main()
