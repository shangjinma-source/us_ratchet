from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from data.news_sandisk_wire_capture_v1 import capture
import test_news_sandisk_wire_v1 as fixtures

class Response:
    def __init__(self,value,status=200):self.raw=json.dumps(value).encode();self.status_code=status
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,size):yield self.raw

class Session:
    def __init__(self,responses):self.responses=iter(responses);self.calls=[]
    def get(self,url,**kwargs):self.calls.append((url,kwargs));return next(self.responses)

class CaptureTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.WireTests();f.setUp();self.row=f.row;self.story=f.doc
        self.clock=lambda:datetime.fromisoformat('2026-11-04T08:00:00+00:00')
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
    def listing(self,rows):return dict(results=dict(news=[dict(topicstring='SNDK',newsitem=rows)]))
    def test_duplicate_release_fetched_once_and_receipts_recoverable(self):
        session=Session([Response(self.listing([self.row,self.row])),Response(self.story)])
        result=capture(self.directory.name,session=session,clock=self.clock)
        self.assertEqual(result['request_count'],2);self.assertFalse(result['errors']);self.assertEqual(len(result['events']),1)
        for receipt in result['receipts']:
            self.assertTrue((Path(self.directory.name)/'raw'/('wire-'+receipt['sha256']+'.json')).is_file())
        self.assertTrue(all(not options['allow_redirects'] for _,options in session.calls))
    def test_at_most_two_stories(self):
        rows=[];stories=[]
        for number in range(4):
            row=deepcopy(self.row);row['newsid']=123+number;row['permalink']=f'https://www.businesswire.com/news/home/{20261029487384+number}/en/'
            rows.append(row);stories.append(Response({},status=503))
        session=Session([Response(self.listing(rows)),*stories])
        result=capture(self.directory.name,session=session,clock=self.clock)
        self.assertEqual(result['request_count'],3);self.assertEqual(len(result['errors']),2);self.assertFalse(result['events'])
    def test_failed_list_does_not_fetch_body(self):
        session=Session([Response({},status=403)])
        result=capture(self.directory.name,session=session,clock=self.clock)
        self.assertEqual(result['request_count'],1);self.assertFalse(result['events']);self.assertTrue(result['errors'])
    def test_future_release_never_fetched(self):
        row=dict(self.row,datetime='2027-01-01T00:00:00Z')
        session=Session([Response(self.listing([row]))])
        result=capture(self.directory.name,session=session,clock=self.clock)
        self.assertEqual(result['request_count'],1);self.assertFalse(result['events'])

if __name__=='__main__':unittest.main()
