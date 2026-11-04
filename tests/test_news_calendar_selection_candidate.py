import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from docs.candidates import news_issuer_calendar_source as candidate
from docs.candidates.news_issuer_source_calendar_hook import candidate_headlines
from data.news_issuer_source import candidate_headlines as original
from docs.candidates.news_scheduled_service_calendar_selection import ScheduledEarningsService
from test_news_scheduled_earnings_v1 import ScheduledEarningsTests
class Response:
 status_code=200
 def __init__(self,body):self.body=body
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def raise_for_status(self):pass
 def iter_content(self,size):yield self.body
NOW=datetime.fromisoformat('2026-11-04T16:00:00+00:00')
class FixedDatetime(datetime):
 @classmethod
 def now(cls,tz=None):return NOW
class CalendarSelectionTests(unittest.TestCase):
 def setUp(self):
  timer=patch('docs.candidates.news_issuer_source_calendar_hook.datetime',FixedDatetime);timer.start();self.addCleanup(timer.stop)

 def fixture(self,root,change=None):
  saved=ScheduledEarningsTests().fixture(root)
  docs=[json.loads((root/'raw'/('issuer-'+r['sha256']+'.json')).read_bytes()) for r in saved['source_receipts']]
  headline=docs[0]['results']['news'][0]['newsitem'][0];story=docs[1]
  rows=[dict(headline,headline='Moderna Announces Clinical Data',newsid='clinical',datetime='2026-11-04T04:00:00+00:00'),dict(headline,headline='Moderna Announces Oncology Results',newsid='oncology',datetime='2026-11-03T04:00:00+00:00'),headline]
  stories={str(headline['newsid']):story}
  if change:
   altered=dict(headline,headline='Moderna '+change+' Earnings Conference Call',newsid='change',datetime='2026-11-04T04:30:00+00:00')
   body=json.loads(json.dumps(story));body['qmcistory']['storyid']='change';body['qmcistory']['qmnews']['qmstory'].update(qmheadline=altered['headline'],datetime=altered['datetime'])
   rows.insert(0,altered);stories['change']=body
  document={'results':{'news':[{'topicstring':'MRNA','newsitem':rows}]}}
  calls=[]
  class Session:
   def get(self,url,params,**kwargs):
    calls.append((url,params));return Response(json.dumps(document if url.endswith('getHeadlines.json') else stories[params['storyId']]).encode())
  return document,Session(),calls
 def test_selection_transport_and_real_calendar(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);document,session,calls=self.fixture(root)
   self.assertEqual(candidate_headlines(document),original(document))
   result=candidate.capture(root,session=session,now=NOW)
   self.assertEqual(len(calls),2);self.assertFalse(result['errors']);self.assertEqual(len(result['events']),1)
   service=ScheduledEarningsService(root,collector=lambda *a,**kw:result,clock=lambda:NOW)
   self.assertTrue(service._collect());out=service.read();self.assertEqual(len(out['events']),1)
   self.assertEqual(out['events'][0]['published_at'],'2026-10-13T11:00:00+00:00');self.assertFalse(out['events'][0]['eligible_as_new_trigger'])
 def test_change_blocks_old_date(self):
  for change in ('Cancels','Reschedules','Postpones'):
   with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);document,session,calls=self.fixture(root,change)
    result=candidate.capture(root,session=session,now=NOW);self.assertEqual(len(calls),3)
    self.assertTrue(any(e.get('message')=='SCHEDULE_CHANGE_REQUIRES_REVIEW' for e in result['errors']))
    service=ScheduledEarningsService(root,collector=lambda *a,**kw:result,clock=lambda:NOW)
    self.assertFalse(service._collect());self.assertEqual(service.read()['events'],[])
if __name__=='__main__':unittest.main()
