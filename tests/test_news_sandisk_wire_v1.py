from copy import deepcopy
from hashlib import sha256
import importlib.util,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from data.news_sandisk_wire_v1 import parse_story,headlines
from data.news_issuer_source import API

class WireTests(unittest.TestCase):
    def setUp(self):
        self.link='https://www.businesswire.com/news/home/20261029487384/en/'
        self.row=dict(newsid=123,datetime='2026-10-29T16:05:00-04:00',qmsource='bwi',topic='[SNDK,EARNINGS]',headline='Sandisk Synthetic Test',permalink=self.link,storyurl='https://api.quotemedia.com/supplement/news-story/?webmasterId=102691&storyId=123')
        body='Sandisk Corporation (Nasdaq: SNDK) '+('Synthetic test information. '*400)+' investors@sandisk.com '+self.link
        self.doc=dict(qmcistory=dict(storyid=123,source='Business Wire via QuoteMedia',qmnews=dict(qmstory=dict(qmheadline=self.row['headline'],datetime=self.row['datetime'],qmtopics=dict(qmsymbol=['SNDK']),qmtext=body))))
        self.now='2026-11-04T08:00:00Z'
    def test_publication_and_discovery_are_distinct(self):
        event=parse_story(self.row,self.doc,self.now)
        self.assertEqual(event['published_at'],'2026-10-29T20:05:00+00:00')
        self.assertEqual(event['collected_at'],self.now)
        self.assertEqual(len(event['source_text']),6000)
    def test_mismatched_headline_identity_url_and_time_rejected(self):
        for key,value in [('qmsource','other'),('topic','[SNDK,NONCOMPANY]'),('newsid',999),('datetime','2026-10-29T20:30:00Z'),('storyurl','https://evil.example/'),('permalink','https://www.businesswire.com.evil/news/home/20261029487384/en/')]:
            row=dict(self.row,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):parse_story(row,self.doc,self.now)
        with self.assertRaisesRegex(ValueError,'FUTURE'):parse_story(self.row,self.doc,'2026-10-28T00:00:00Z')
    def test_wrong_story_symbol_rejected(self):
        self.doc['qmcistory']['qmnews']['qmstory']['qmtopics']['qmsymbol']=['MRNA']
        with self.assertRaisesRegex(ValueError,'SYMBOL'):parse_story(self.row,self.doc,self.now)
    def test_full_body_recovery_and_raw_tampering(self):
        path=Path(__file__).resolve().parents[1]/'docs/candidates/news_investment_sources_sandisk_wire.py'
        spec=importlib.util.spec_from_file_location('wire_sources',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        listing=dict(results=dict(news=[dict(topicstring='SNDK',newsitem=[self.row])]))
        self.assertEqual(headlines(listing),[self.row])
        with TemporaryDirectory() as directory:
            root=Path(directory);(root/'raw').mkdir();receipts=[]
            for endpoint,params,document in [('getHeadlines.json',{'topics':'SNDK'},listing),('getStory.json',{'storyId':'123'},self.doc)]:
                raw=json.dumps(document).encode();digest=sha256(raw).hexdigest();(root/'raw'/('wire-'+digest+'.json')).write_bytes(raw)
                receipts.append(dict(url=API+endpoint,params=params,status=200,sha256=digest,fetched_at=self.now))
            event=parse_story(self.row,self.doc,self.now)
            body,_=module.recover(event,receipts,root)
            self.assertGreater(len(body),6000);self.assertEqual(sha256(body.encode()).hexdigest(),event['content_sha256'])
            (root/'raw'/('wire-'+receipts[-1]['sha256']+'.json')).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'RAW_HASH_MISMATCH'):module.recover(event,receipts,root)

if __name__=='__main__':unittest.main()
