"""Synthetic joint-issuer contract fixtures, not authentic company disclosures."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from data.news_issuer_source import API, candidate_headlines, parse_issuer_story, text
from data.news_investment_sources_v1 import recover


class JointIssuerOfflineTests(unittest.TestCase):
    def setUp(self):
        self.stamp = '2026-10-27T12:00:00+00:00'
        self.headline = dict(
            newsid=123456789, headline='Merck and Moderna Synthetic Fixture Announcement',
            datetime='2026-10-22T14:59:00-04:00', qmsource='bwi', topic='[MRK,MRNA]',
            storyurl='https://api.quotemedia.com/supplement/news-story/?webmasterId=0&storyId=123456789')
        body = ('SYNTHETIC TEST FIXTURE. Merck (NYSE: MRK), and Moderna, Inc. (NASDAQ: MRNA) today announced '
                'a synthetic test only. Merck Media Contacts: test@merck.com '
                'Moderna Media Contacts: test@modernatx.com '
                'View source version on businesswire.com: https://www.businesswire.com/news/home/00000000000000/en/ '
                + 'Synthetic filler, no factual claim. ' * 220)
        self.document = {'qmcistory': {'storyid':123456789, 'source':'Business Wire via QuoteMedia',
            'qmnews': {'qmstory': {'qmheadline':self.headline['headline'],
                'datetime':self.headline['datetime'], 'qmtext':body}}}}
        self.headlines = {'results': {'news':[{'topicstring':'MRNA','newsitem':[self.headline]}]}}

    def test_joint_selected_with_correct_label(self):
        self.assertEqual(candidate_headlines(self.headlines), [self.headline])
        event=parse_issuer_story(self.headline,self.document,self.stamp)
        self.assertIn('Business Wire',event['source'])
        self.assertNotIn('ACCESS',event['source'])
        self.assertEqual(event['published_at'],'2026-10-22T18:59:00+00:00')
        self.assertEqual(event['tickers'],['MRNA'])

    def test_wrong_identity_source_and_time_rejected(self):
        for kind in ('distributor','company','title','future','noncompany','missing_topic','wrong_channel'):
            with self.subTest(kind=kind):
                headline=deepcopy(self.headline);document=deepcopy(self.document);stamp=self.stamp
                if kind=='distributor':document['qmcistory']['source']='Unknown Wire'
                if kind=='company':document['qmcistory']['qmnews']['qmstory']['qmtext']=document['qmcistory']['qmnews']['qmstory']['qmtext'].replace('@modernatx.com','@other.example')
                if kind=='title':headline['headline']='Unrelated Company'
                if kind=='future':stamp='2026-10-21T00:00:00+00:00'
                if kind=='noncompany':headline['topic']='[MRK,MRNA,NONCOMPANY]'
                if kind=='missing_topic':headline['topic']='[MRNA]'
                if kind=='wrong_channel':headline['qmsource']='arbitrary'
                with self.assertRaises(ValueError):parse_issuer_story(headline,document,stamp)

    def test_full_body_recovered_with_receipt_hashes(self):
        event=parse_issuer_story(self.headline,self.document,self.stamp)
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);(cache/'raw').mkdir()
            receipts=[]
            for endpoint,payload,params in [('getHeadlines.json',self.headlines,{}),('getStory.json',self.document,{'storyId':'123456789'})]:
                raw=json.dumps(payload).encode();digest=sha256(raw).hexdigest()
                (cache/'raw'/('issuer-'+digest+'.json')).write_bytes(raw)
                receipts.append(dict(url=API+endpoint,params=params,sha256=digest,fetched_at=self.stamp))
            body,digest=recover(event,receipts,cache)
            self.assertGreater(len(body),len(event['source_text']))
            self.assertEqual(body,text(self.document['qmcistory']['qmnews']['qmstory']['qmtext']))
            self.assertEqual(sha256(body.encode()).hexdigest(),event['content_sha256'])
            self.assertEqual(digest,receipts[1]['sha256'])
            (cache/'raw'/('issuer-'+digest+'.json')).write_bytes(b'changed')
            with self.assertRaises(ValueError):recover(event,receipts,cache)

    def test_access_requirements_preserved(self):
        headline=deepcopy(self.headline);headline.update(headline='Moderna Synthetic Fixture',qmsource='bayaw',topic='[MRNA]')
        document=deepcopy(self.document);document['qmcistory']['source']='ACCESS Newswire via QuoteMedia'
        story=document['qmcistory']['qmnews']['qmstory'];story.update(qmheadline=headline['headline'],qmtext='Synthetic fixture. SOURCE: Moderna, Inc. NASDAQ:MRNA test@modernatx.com')
        self.assertIn('ACCESS',parse_issuer_story(headline,document,self.stamp)['source'])
        story['qmtext']=story['qmtext'].replace('SOURCE: Moderna, Inc.','SOURCE: Different Company')
        with self.assertRaises(ValueError):parse_issuer_story(headline,document,self.stamp)

if __name__=='__main__':unittest.main()
