"""Synthetic composition wiring and invalidation; model functions are mocked."""
import unittest,sys,importlib.util,json,os
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
from tempfile import TemporaryDirectory
from datetime import datetime,timezone,timedelta
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path('.').resolve()));sys.path.insert(0,str(Path('tests').resolve()))
from test_news_background_context_v1 import synthetic_package
STAGE=Path(os.environ.get('NEWS_BACKGROUND_STAGE_DIRECTORY','data'))
for name in ('news_investment_service_v1','news_investment_composition_v1'):
 spec=importlib.util.spec_from_file_location('data.'+name,STAGE/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);setattr(__import__('data'),name,m)
import test_news_investment_service_v1 as service_tests
comp=sys.modules['data.news_investment_composition_v1'];model=sys.modules['data.news_investment_model_v1'];evmodel=sys.modules['data.news_event_model_v1']
class Wiring(unittest.TestCase):
 def setUp(self):
  guard=patch('subprocess.Popen',side_effect=AssertionError('REAL_PROCESS_FORBIDDEN_IN_BACKGROUND_TEST'));self.no_process=guard.start();self.addCleanup(guard.stop);self.addCleanup(self.no_process.assert_not_called)
 def setup_composed(self,root):
  synthetic_package(root)
  account={'revision':'r','events':[]};target={'target_id':'t','proposal_id':'p','payload':{'decision':{'payload':{'input_binding':{'search_arguments':{'metadata':{'S':{'ticker':'SNDK'}}}}}}}}
  monthly=SimpleNamespace(snapshot_operation=nullcontext,accounts=SimpleNamespace(read=lambda:account),current=lambda:target)
  captured=[];pipelines=[];real=comp.NewsInvestmentService
  from data.news_event_pipeline_v1 import EventNewsPipeline
  def make_service(**kw):s=real(**kw);captured.append(s);return s
  def make_pipeline(*a,**kw):p=EventNewsPipeline(*a,**kw);pipelines.append(p);return p
  with patch.object(comp,'NewsInvestmentService',side_effect=make_service),patch('data.news_event_pipeline_v1.EventNewsPipeline',side_effect=make_pipeline):
   comp.compose(root=root,monthly_view=monthly,observed_daily=SimpleNamespace(preview=lambda **k:None,service=SimpleNamespace(reader=None)),validate=lambda:None)
  captured[0].clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc)
  return captured[0],pipelines[0]
 def source(self):
  return dict(id='t',security_ids=['S'],published_at='2026-10-27T12:00:00Z')
 def test_both_actual_composition_callbacks_and_pending_rejection(self):
  with TemporaryDirectory() as d:
   positions=[{'security_id':'S','ticker':'SNDK'}]
   with patch.object(model,'analyze_review',return_value={'status':'SUCCEEDED'}) as manual,patch.object(evmodel,'analyze_event',return_value={'status':'SUCCEEDED'}) as event:
    service,pipeline=self.setup_composed(Path(d))
    one=service.model([self.source()],positions,Path(d));two=pipeline.analyzer([self.source()],positions,Path(d))
    self.assertEqual(len(manual.call_args.kwargs['background_sources']),2);self.assertEqual(len(event.call_args.kwargs['background_sources']),2)
    self.assertEqual(one['background_context_binding'],two['background_context_binding']);service.background_guard(one)
    with patch.object(pipeline,'load',side_effect=AssertionError('must reject missing context before old event guard')):
     self.assertFalse(pipeline.valid_event({'answer':{}}))
   bad=dict(job_id='j',status='COMPLETE',binding={'expected_revision':'r','target_id':'t','expected_proposal_id':'p'},proposal={'review_valid_until':'2026-10-28T13:00:00Z'},started_at='2026-10-28T12:00:00Z')
   with service.connection() as db:service.save(db,bad)
   db.close()
   with patch.object(service,'background_guard',wraps=service.background_guard) as checked:
    self.assertEqual(service.status('j')['status'],'STALE')
    checked.assert_called_once_with({'background_context_binding':None})
   index=Path(d)/'data/cache/news/background_index_v1.json';index.write_text('{}')
   with self.assertRaisesRegex(ValueError,'INDEX_CHANGED'):service.background_guard(one)
   self.assertFalse(pipeline.valid_event({'answer':one}))
 def test_real_service_final_guard_rejects_index_changed_during_projection(self):
  with TemporaryDirectory() as d:
   composed,_=self.setup_composed(Path(d));t=service_tests.ServiceTests();t.setUp()
   try:
    binding={'manifest_sha256':json.loads((Path(d)/'data/cache/news/background_index_v1.json').read_text())['manifest_sha256'],'role':'BACKGROUND_NOT_TRIGGER'}
    t.answer['background_context_binding']=binding;t.service.background_guard=composed.background_guard
    def corrupt(**kw):(Path(d)/'data/cache/news/background_index_v1.json').write_text('{}');return {'status':'WAIT'}
    t.service.risk_plan_provider=corrupt
    result=t.run_job();self.assertEqual(result['status'],'FAILED');self.assertEqual(result['error'],'BACKGROUND_INDEX_CHANGED');self.assertNotIn('proposal',result)
   finally:t.doCleanups()
if __name__=='__main__':unittest.main()
