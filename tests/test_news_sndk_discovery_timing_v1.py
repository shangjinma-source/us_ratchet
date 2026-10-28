"""SNDK changed listings hydrate once before final publication admission."""
import importlib.util, os, sys, unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
import test_news_event_pipeline_v1 as base

candidate=os.environ.get('NEWS_SNDK_DISCOVERY_CANDIDATE')
if candidate:
 spec=importlib.util.spec_from_file_location('sndk_discovery_candidate',candidate)
 candidate_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate_module)
else:
 from data import news_event_pipeline_v1 as candidate_module

class SndkDiscoveryTests(unittest.TestCase):
 def setUp(self):
  with patch.object(base,'EventNewsPipeline',candidate_module.EventNewsPipeline):
   base.EventPipelineTests.setUp(self)
  original=self.service.context
  self.service.context=lambda:(original()[0],original()[1],{'sid':'SNDK'})
  self.url='https://www.sandisk.com/company/newsroom/press-releases/old'
  self.published=self.now-timedelta(days=1);self.article_time=None;self.hydrates=0
  owner=self
  class Sources:
   supported={'SNDK'}
   def __init__(self,*a,**k):self.request_count=0;self.receipts=[]
   def discover(self,ticker):
    self.request_count+=1
    return [dict(ticker=ticker,url=owner.url,title='Issuer release',published_at=owner.published.isoformat(),discovered_at=owner.now.isoformat())]
   def hydrate(self,row):
    self.request_count+=1;owner.hydrates+=1
    pub=owner.article_time or owner.published
    if pub!=owner.published:
     error=ValueError('TIMELY_TRIGGER_PUBLICATION_CONFLICT')
     error.publication_conflict=dict(ticker='SNDK',url=row['url'],listing_published_at=row['published_at'],article_published_at=pub.isoformat())
     raise error
    return dict(id='e',title=row['title'],url=row['url'],tickers=['SNDK'],published_at=pub.isoformat(),collected_at=owner.now.isoformat(),discovered_at=row['discovered_at'],content_sha256='hash')
  self.pipeline.sources_factory=Sources
  self.pipeline.set_enabled(True)
 def tick_later(self):
  self.now+=timedelta(seconds=61)
  return self.pipeline.tick()
 def test_initial_old_listing_is_baseline_no_body(self):
  self.pipeline.tick();self.tick_later()
  self.assertEqual((self.hydrates,self.model_calls),(0,0))
 def test_new_url_old_index_new_article_conflict_visible_once(self):
  self.pipeline.tick();self.url+='-new';self.article_time=self.now
  result=self.tick_later()
  self.assertEqual(result['status'],'WAIT_PUBLICATION_TIME_CONFLICT')
  self.assertEqual(result['publication_conflicts'][0]['ticker'],'SNDK')
  self.assertEqual(self.model_calls,0);self.assertIsNone(self.pipeline.load()['pending'])
  self.tick_later();self.assertEqual(self.hydrates,1)
 def test_consistent_new_article_runs_normal_window(self):
  self.pipeline.tick();self.url+='-new';self.published=self.now
  result=self.tick_later()
  self.assertEqual(result['status'],'SOURCE_OPINION_READY')
  self.assertEqual(self.model_calls,1)
  self.assertEqual(self.pipeline.load()['pending']['execution_window'],self.pipeline.publication_window([dict(published_at=self.published.isoformat())]))
 def test_new_url_actual_old_article_rejected_once_no_refresh(self):
  self.pipeline.tick();self.url+='-new'
  result=self.tick_later()
  self.assertEqual(self.hydrates,1);self.assertEqual(self.model_calls,0)
  self.assertIsNone(self.pipeline.load()['pending'])
  self.assertIn('BODY_WINDOW_EXPIRED',[x['status'] for x in self.pipeline.load()['seen'].values()])
  self.tick_later();self.assertEqual(self.hydrates,1)
 def test_metadata_change_same_url_checked_and_conflict_cannot_extend(self):
  self.pipeline.tick();self.published-=timedelta(minutes=1);self.article_time=self.now
  self.tick_later();self.assertEqual(self.hydrates,1)
  self.assertEqual(self.model_calls,0);self.assertIsNone(self.pipeline.load()['pending'])
  self.assertNotIn('opinion_valid_until',self.pipeline.load())

class MixedDiscoveryTests(unittest.TestCase):
 setUp=SndkDiscoveryTests.setUp
 tick_later=SndkDiscoveryTests.tick_later
 def mixed_sources(self):
  owner=self
  prior=self.pipeline.sources_factory
  class Mixed(prior):
   supported={'MRNA','SNDK'}
   def discover(self,ticker):
    if ticker=='SNDK':return super().discover(ticker)
    self.request_count+=1
    return [dict(ticker='MRNA',url='https://issuer/mrna',title='MRNA',published_at=owner.mrna_pub.isoformat(),discovered_at=owner.now.isoformat())]
   def hydrate(self,row):
    if row['ticker']=='SNDK':return super().hydrate(row)
    self.request_count+=1
    return dict(id='mrna',title='MRNA',url=row['url'],tickers=['MRNA'],published_at=row['published_at'],collected_at=owner.now.isoformat(),discovered_at=row['discovered_at'],content_sha256='mrna')
  self.pipeline.sources_factory=Mixed
  self.service.context=lambda:(dict(revision='a',shares={'sid':2,'mrna':2}),dict(target_id='b',proposal_id='c',payload=dict(target_quantities={'sid':3,'mrna':2})),{'sid':'SNDK','mrna':'MRNA'})
  self.pipeline.source_builder=lambda snapshot,*a,**k:dict(sources={e['id']:dict(id=e['id']) for e in snapshot['events']},fingerprint='mixed')
  self.sent=[]
  def analyze(sources,*a,**k):
   self.sent.append(sources)
   return self.analyzer(sources,*a,**k)
  self.pipeline.analyzer=analyze
 def test_mixed_conflict_retained_but_only_timely_mrna_analyzed(self):
  self.mrna_pub=self.now-timedelta(days=1);self.mixed_sources();self.pipeline.tick()
  self.mrna_pub=self.now;self.url+='-new';self.article_time=self.now
  result=self.tick_later()
  self.assertEqual(result['status'],'SOURCE_OPINION_READY')
  self.assertEqual([x['id'] for x in self.sent[0]],['mrna'])
  self.assertEqual([x['tickers'] for x in self.pipeline.load()['pending']['snapshot']['events']],[['MRNA']])
  self.assertEqual(result['publication_conflicts'][0]['ticker'],'SNDK')
  self.assertLessEqual(result['request_count'],4)
 def test_pending_invalidated_by_new_conflict_before_execution(self):
  self.mrna_pub=self.now;self.mixed_sources();self.pipeline.tick()
  old=self.pipeline.load()['pending'];old_generation=old['source_generation']
  self.assertIsNotNone(old)
  self.url+='-new';self.article_time=self.now
  self.now=self.now.replace(hour=13,minute=30)
  result=self.pipeline.tick()
  self.assertGreater(self.pipeline.load()['source_generation'],old_generation)
  self.assertFalse(self.pipeline.valid_event(old))
  self.assertEqual(self.finalize_calls,0)
  self.assertEqual(result['publication_conflicts'][0]['ticker'],'SNDK')

class HydrateDiagnosticTests(unittest.TestCase):
 def test_source_conflict_preserves_both_times_and_ticker(self):
  candidate_source=os.environ.get('NEWS_SNDK_SOURCE_CANDIDATE')
  if candidate_source:
   spec=importlib.util.spec_from_file_location('sndk_source_candidate',candidate_source)
   source_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(source_module)
  else:
   from data import news_event_sources_v1 as source_module
  row=dict(ticker='SNDK',url='https://www.sandisk.com/company/newsroom/press-releases/new',title='New',published_at='2026-10-28T07:00:00Z',discovered_at='2026-10-28T14:01:00Z')
  event=dict(title='New',published_at='2026-10-28T14:00:00Z')
  collector=source_module.EventSources(Path('.'))
  collector.fetch=lambda *a,**k:(b'fixture',dict(fetched_at=row['discovered_at']))
  with patch.object(source_module,'parse_release',return_value=dict(event=event)):
   with self.assertRaisesRegex(ValueError,'TIMELY_TRIGGER_PUBLICATION_CONFLICT') as caught:
    collector.hydrate(row)
  self.assertEqual(caught.exception.publication_conflict,dict(ticker='SNDK',url=row['url'],listing_published_at=row['published_at'],article_published_at=event['published_at']))

if __name__=='__main__':unittest.main()
