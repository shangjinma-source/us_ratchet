import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from data import news_desk

class BodyPriorityTests(unittest.TestCase):
    def test_bodies_survive_more_recent_feed_excerpts(self):
        rows=[dict(id=str(i),url='https://example.com/'+str(i),source='RSS',tickers=['NVDA'],published_at='2026-10-21T00:00:00+00:00',collected_at='2026-10-27T00:00:00+00:00',source_text='excerpt',content_kind='RSS_EXCERPT') for i in range(30)]
        bodies=[dict(id='body'+str(i),url='https://example.com/body'+str(i),source='Sandisk 官方新闻室',tickers=['SNDK'],published_at='2026-10-13T00:00:00+00:00',collected_at='2026-10-27T00:00:00+00:00',source_text='official body',content_kind='OFFICIAL_RELEASE_BODY') for i in range(2)]
        with TemporaryDirectory() as folder, patch.object(news_desk,'SOURCES',()), patch.object(news_desk,'capture_issuer',return_value=dict(events=rows,receipts=[],errors=[])), patch.object(news_desk,'capture_sandisk',return_value=dict(events=bodies,receipts=[],errors=[])):
            result=news_desk.collect(folder)
        self.assertEqual(len(result['events']),20)
        self.assertTrue(all(body in result['events'] for body in bodies))
        self.assertEqual(next(r['displayed'] for r in result['source_coverage'] if r['source']=='Sandisk 官方新闻室'),2)
