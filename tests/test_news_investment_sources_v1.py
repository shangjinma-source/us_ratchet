import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from data.news_issuer_source import API,parse_issuer_story
from data.news_investment_sources_v1 import build_sources

class SourcesTests(unittest.TestCase):
    def fixture(self,root):
        now='2026-10-27T15:00:00+00:00';published='2026-10-27T14:00:00+00:00'
        headline=dict(newsid='1',headline='Moderna release',datetime=published,qmsource='bayaw',topic='MRNA',storyurl='https://api.quotemedia.com/supplement/news-story/?id=1')
        body='SOURCE: Moderna, Inc. NASDAQ:MRNA press@modernatx.com '+('full details '*700)
        doc={'qmcistory':{'storyid':'1','source':'ACCESS Newswire','qmnews':{'qmstory':{'qmheadline':headline['headline'],'datetime':published,'qmtext':body}}}}
        event=parse_issuer_story(headline,doc,now)
        receipts=[]
        for endpoint,value,params in [('getHeadlines.json',{'results':{'news':[{'topicstring':'MRNA','newsitem':[headline]}]}},{}),('getStory.json',doc,{'storyId':'1'})]:
            raw=json.dumps(value).encode();digest=sha256(raw).hexdigest()
            (root/'raw'/('issuer-'+digest+'.json')).write_bytes(raw)
            receipts.append(dict(url=API+endpoint,params=params,sha256=digest,fetched_at=now))
        return dict(generated_at=now,events=[event],source_receipts=receipts),[dict(security_id='A',ticker='MRNA',original_qty=1,target_qty=2)]

    def test_full_body_recovered_not_display_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'raw').mkdir();snap,pos=self.fixture(root)
            result=build_sources(snap,root,pos);source=next(iter(result['sources'].values()))
            self.assertGreater(len(source['text']),6000)
            self.assertEqual(len(snap['events'][0]['source_text']),6000)
            self.assertEqual(source['text_sha256'],sha256(source['text'].encode()).hexdigest())
            self.assertEqual(result,build_sources(snap,root,pos))

    def test_missing_raw_or_hash_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'raw').mkdir();snap,pos=self.fixture(root)
            snap['events'][0]['content_sha256']='bad'
            self.assertFalse(build_sources(snap,root,pos)['sources'])

    def test_old_and_macro_not_admitted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'raw').mkdir();snap,pos=self.fixture(root)
            snap['generated_at']='2026-11-10T15:00:00+00:00'
            self.assertEqual(build_sources(snap,root,pos)['coverage'][0]['reason'],'OLDER_THAN_SEVEN_DAYS')
            snap['events'][0]['relevance']='macro'
            self.assertEqual(build_sources(snap,root,pos)['coverage'][0]['reason'],'UNSCOPED_MACRO_NOT_ADMITTED')

    def test_no_silent_budget_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'raw').mkdir();snap,pos=self.fixture(root)
            from unittest.mock import patch
            with patch('data.news_investment_sources_v1.recover',return_value=('x'*60001,'raw')):
                result=build_sources(snap,root,pos)
            self.assertFalse(result['sources'])
            self.assertEqual(result['coverage'][0]['reason'],'FULL_TEXT_BATCH_BUDGET_EXCEEDED')

    def test_sandisk_full_html_and_receipt_identity(self):
        from data.news_sandisk_parser import parse_release
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'raw').mkdir()
            url='https://www.sandisk.com/company/newsroom/press-releases/2026/test'
            now='2026-10-27T15:00:00+00:00'
            body='Sandisk '+('official full text '*400)
            raw=('<html><head><link rel="canonical" href="'+url+'"><meta name="article:published_time" content="2026-10-27T14:00:00Z"></head><body><article><h1>Sandisk report</h1><p>October 27, 2026</p><div class="para-text">'+body+'</div></article></body></html>').encode()
            digest=sha256(raw).hexdigest();(root/'raw'/('sandisk-'+digest+'.raw')).write_bytes(raw)
            event=parse_release(raw,url,now)['event']
            snap=dict(generated_at=now,events=[event],source_receipts=[dict(url=url,status=200,sha256=digest,fetched_at=now)])
            pos=[dict(security_id='S',ticker='SNDK')]
            source=next(iter(build_sources(snap,root,pos)['sources'].values()))
            self.assertEqual(source['text'],body.strip())
            snap['source_receipts'][0]['url']=url+'wrong'
            self.assertFalse(build_sources(snap,root,pos)['sources'])

if __name__=='__main__':unittest.main()
