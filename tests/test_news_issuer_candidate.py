import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
from datetime import datetime,timezone
spec=importlib.util.spec_from_file_location('candidate_issuer',Path(__file__).resolve().parents[1]/'docs/candidates/news_desk_issuer.py')
issuer=importlib.util.module_from_spec(spec);spec.loader.exec_module(issuer)

def headline(identity,title='Moderna Reports Research Update'):
    return dict(newsid=identity,headline=title,datetime='2026-10-13T07:00:00-04:00',qmsource='bayaw',topic='[MRNA,PRESS001]',storyurl='https://api.quotemedia.com/supplement/news-story/?storyId='+str(identity))

def story(h):
    return dict(qmcistory=dict(storyid=h['newsid'],source='ACCESS Newswire via QuoteMedia',qmnews=dict(qmstory=dict(qmheadline=h['headline'],datetime=h['datetime'],qmtext='Moderna, Inc. (NASDAQ:MRNA) announced research findings. Investor contact ir@modernatx.com. SOURCE: Moderna, Inc.'))))

class Response:
    status_code=200
    def __init__(self,value):self.raw=json.dumps(value).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def raise_for_status(self):pass
    def iter_content(self,size):yield self.raw

class Session:
    def __init__(self,rows,bad=False):self.rows=rows;self.calls=[];self.bad=bad
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if url.endswith('getHeadlines.json'):return Response(dict(results=dict(news=[dict(topicstring='MRNA',newsitem=self.rows)])))
        h=next(h for h in self.rows if str(h['newsid'])==kwargs['params']['storyId']);value=story(h)
        if self.bad:value['qmcistory']['qmnews']['qmstory']['qmtext']='third party comment'
        return Response(value)

class IssuerTests(unittest.TestCase):
    def test_integrated_candidate_skips_headline_only_without_model(self):
        path=Path(__file__).resolve().parents[1]/'docs/candidates/news_desk_with_issuer.py'
        spec=importlib.util.spec_from_file_location('candidate_integrated_news',path)
        candidate=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'data.news_issuer_source':issuer}):spec.loader.exec_module(candidate)
        title='Federal Reserve '+('long headline '*15)
        event=dict(title=title,source='Fed',source_text=title,tickers=[],relevance='macro')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(candidate.shutil,'which',side_effect=AssertionError('Model must not run')):
                result=candidate.analyze(dict(events=[event]),directory)
        self.assertEqual(result['analysis_summary']['status'],'NO_ANALYZABLE_CONTENT')
        self.assertEqual(event['analysis_status'],'SKIPPED_INSUFFICIENT_TEXT')

    def test_bound_noise_and_receipts(self):
        rows=[headline(1,'Moderna Named a Top Employer'),headline(2),headline(3),headline(4)]
        session=Session(rows)
        with tempfile.TemporaryDirectory() as directory:
            result=issuer.capture(directory,session=session,now=datetime(2026,10,27,tzinfo=timezone.utc))
            self.assertEqual(len(session.calls),3);self.assertEqual(len(result['events']),2)
            self.assertEqual(len(result['receipts']),3);self.assertEqual(result['errors'],[])
            self.assertTrue(all(r['sha256'] and r['fetched_at'] for r in result['receipts']))
    def test_wrong_issuer_errors_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            result=issuer.capture(directory,session=Session([headline(1)],bad=True),now=datetime(2026,10,27,tzinfo=timezone.utc))
            self.assertEqual(result['events'],[]);self.assertEqual(len(result['errors']),1)
    def test_future_rejected(self):
        h=headline(1);h['datetime']='2030-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'FUTURE'):issuer.parse_issuer_story(h,story(h),'2026-10-27T00:00:00+00:00')
    def test_noncompany_filtered(self):
        h=headline(1);h['topic']='[MRNA,NONCOMPANY]'
        result=issuer.candidate_headlines(dict(results=dict(news=[dict(topicstring='MRNA',newsitem=[h])])))
        self.assertEqual(result,[])

if __name__=='__main__':unittest.main()

