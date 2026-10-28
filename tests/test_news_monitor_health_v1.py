"""Offline monitor-health status regression. Does not alter admission or cadence."""
import sys,os,unittest,importlib.util
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_news_event_pipeline_v1 as fixtures
candidate=os.environ.get('NEWS_MONITOR_PIPELINE_CANDIDATE')
if candidate:
 spec=importlib.util.spec_from_file_location('monitor_candidate',candidate);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);Pipeline=module.EventNewsPipeline
else:
 from data.news_event_pipeline_v1 import EventNewsPipeline as Pipeline
class Health(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.EventPipelineTests()
  with patch.object(fixtures,'EventNewsPipeline',Pipeline):self.fixture.setUp()
  self.addCleanup(self.fixture.doCleanups);self.f=self.fixture;self.p=self.f.pipeline
  self.p.set_enabled(True)
 def test_failed_listing_without_pending_is_wait_not_no_news(self):
  self.f.fail_list=True;result=self.p.tick()
  self.assertEqual(result['status'],'WAIT_SOURCE_RECONFIRMATION');self.assertFalse(self.p.load()['source_confirmed'])
  self.assertEqual(result['source_status'][0]['status'],'LIST_FAILED_NO_WATERMARK');self.assertEqual(self.p.load()['seen'],{})
  self.assertEqual((self.f.model_calls,self.f.finalize_calls),(0,0))
 def test_recovered_listing_can_return_no_new_body_without_model(self):
  self.f.fail_list=True;self.p.tick();self.f.fail_list=False;self.f.old=True;self.f.now+=timedelta(seconds=61)
  result=self.p.tick();self.assertEqual(result['status'],'NO_NEW_TIMELY_BODY');self.assertTrue(self.p.load()['source_confirmed'])
  self.assertEqual((self.f.model_calls,self.f.finalize_calls),(0,0))
 def test_partial_failed_listing_not_silently_healthy(self):
  old=self.p.service.context
  def context():
   account,target,names=old();account['shares']['other']=1;names['other']='SNDK';return account,target,names
  self.p.service.context=context
  parent=self.f.factory
  class Sources(parent):
   def discover(self,ticker):
    self.request_count+=1
    if ticker=='SNDK':raise ValueError('SIMULATED_LIST_FAILURE')
    return []
  self.p.sources_factory=Sources;r=self.p.tick()
  self.assertEqual(r['status'],'WAIT_SOURCE_RECONFIRMATION');self.assertEqual([x['status'] for x in r['source_status']],['LIST_OK','LIST_FAILED_NO_WATERMARK'])
  self.assertFalse(self.p.load()['source_confirmed']);self.assertEqual((self.f.model_calls,self.f.finalize_calls),(0,0))
if __name__=='__main__':unittest.main()
