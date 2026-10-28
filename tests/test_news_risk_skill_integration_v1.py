import sys,importlib.util,unittest,tempfile,json,hashlib,shutil,os
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));STAGE=Path(os.environ.get('NEWS_SKILL_STAGE_DIRECTORY',str(ROOT)))
import data
for name in ['news_risk_skill_v1','news_investment_model_v1','news_event_model_v1','news_investment_service_v1','news_investment_composition_v1']:
 spec=importlib.util.spec_from_file_location('data.'+name,STAGE/'data'/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;setattr(data,name,m);spec.loader.exec_module(m)
from data import news_risk_skill_v1 as skill,news_investment_model_v1 as model,news_event_model_v1 as event,news_investment_composition_v1 as comp
SOURCE=dict(id='s',title='Release',url='https://example.org/a',text='Material operating loss confirmed.',security_ids=['sid'],tickers=['X'],content_kind='FULL_TEXT',published_at='2026-10-28T10:00:00Z',observed_at='2026-10-28T10:01:00Z')
SOURCE['text_sha256']=hashlib.sha256(SOURCE['text'].encode()).hexdigest()
POSITION=dict(security_id='sid',ticker='X',original_qty=10,target_qty=12)
def response():return {'rows':[dict(security_id='sid',ticker='X',action='REDUCE_HOLDING',reason='risk',counterevidence=[],uncertainty=[],buy_fraction='0',holding_fraction='1/2',evidence=[dict(source_id='s',quote=SOURCE['text'])])]}
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  shutil.copytree(STAGE/'skills',self.root/'skills')
  p=patch('subprocess.Popen',side_effect=AssertionError('NO_REAL_MODEL'));p.start();self.addCleanup(p.stop)
 def test_loader_only_core_and_tamper(self):
  first=skill.load_risk_skill(self.root)
  ref=self.root/'skills/us-equity-news-risk/references';ref.mkdir(exist_ok=True);(ref/'leak.txt').write_text('FUTURE_RETURN_SECRET')
  self.assertEqual(first,skill.load_risk_skill(self.root));self.assertNotIn('FUTURE_RETURN_SECRET',first['prompt'])
  (self.root/'skills/us-equity-news-risk/SOUL.md').write_text('tampered')
  with self.assertRaisesRegex(ValueError,'HASH'):skill.load_risk_skill(self.root)
 def test_missing_before_model(self):
  for module,fn in [(model,model.analyze_review),(event,event.analyze_event)]:
   with patch.object(module,'load_risk_skill',side_effect=FileNotFoundError()),patch.object(module,'_invoke') as call:
    with self.assertRaises(FileNotFoundError):fn([SOURCE],[POSITION],self.root/'cache')
    call.assert_not_called()
 def test_both_cache_receipt_and_prompt(self):
  for module,fn in [(model,model.analyze_review),(event,event.analyze_event)]:
   with self.subTest(module=module.__name__),patch.object(module,'ModelCoordinator') as coordinator,patch.object(module,'_invoke',side_effect=lambda *a:(response(),{})) as call:
    coordinator.return_value.reserve.return_value=nullcontext()
    cache=self.root/module.__name__
    first=fn([SOURCE],[POSITION],cache);self.assertEqual(first['status'],'SUCCEEDED')
    self.assertEqual(first['skill_context_binding'],first['receipt']['skill_context_binding'])
    self.assertIn('PINNED_RISK_REVIEW_PRINCIPLES',call.call_args.args[0]);self.assertNotIn('FUTURE_RETURN',call.call_args.args[0])
    self.assertEqual(fn([SOURCE],[POSITION],cache)['status'],'CACHED');self.assertEqual(call.call_count,1)
    receipt=cache/first['cache_key']/'receipt.json';r=json.loads(receipt.read_text());r.pop('skill_context_binding');receipt.write_text(json.dumps(r))
    self.assertEqual(fn([SOURCE],[POSITION],cache)['status'],'PREVIOUS_ATTEMPT_NOT_RETRIED');self.assertEqual(call.call_count,1)
 def test_post_invoke_tamper_rejected(self):
  with patch.object(model,'ModelCoordinator') as coordinator,patch.object(model,'_invoke',return_value=(response(),{})),patch.object(model,'require_risk_skill',side_effect=[None,ValueError('CHANGED')]):
   coordinator.return_value.reserve.return_value=nullcontext()
   result=model.analyze_review([SOURCE],[POSITION],self.root/'cache');self.assertEqual(result['status'],'FAILED');self.assertEqual(result['rows'],[])
 def test_composition_without_background_rejects_old_pending_and_complete(self):
  account={'revision':'r','events':[]};target={'target_id':'t','proposal_id':'p','payload':{'decision':{'payload':{'input_binding':{'search_arguments':{'metadata':{'sid':{'ticker':'X'}}}}}}}}
  monthly=SimpleNamespace(snapshot_operation=nullcontext,accounts=SimpleNamespace(read=lambda:account),current=lambda:target)
  captured=[];pipelines=[];real=comp.NewsInvestmentService
  from data.news_event_pipeline_v1 import EventNewsPipeline
  def service(**kw):s=real(**kw);captured.append(s);return s
  def pipeline(*a,**kw):p=EventNewsPipeline(*a,**kw);pipelines.append(p);return p
  with patch.object(comp,'NewsInvestmentService',side_effect=service),patch('data.news_event_pipeline_v1.EventNewsPipeline',side_effect=pipeline):
   comp.compose(root=self.root,monthly_view=monthly,observed_daily=SimpleNamespace(preview=lambda **k:None,service=SimpleNamespace(reader=None)),validate=lambda:None)
  s=captured[0];p=pipelines[0];s.background_guard({'skill_context_binding':skill.load_risk_skill(self.root)['binding']})
  with self.assertRaisesRegex(ValueError,'VERSION'):s.background_guard({})
  self.assertFalse(p.valid_event({'answer':{}}))
  bad=dict(job_id='j',status='COMPLETE',binding={'expected_revision':'r','target_id':'t','expected_proposal_id':'p'},proposal={'review_valid_until':'2099-10-28T13:00:00Z'},started_at='2026-10-28T12:00:00Z')
  with s.connection() as db:s.save(db,bad)
  db.close()
  self.assertEqual(s.status('j')['status'],'STALE')
 def test_actual_service_preserves_skill_binding_and_status_checks_it(self):
  sys.path.insert(0,str(ROOT/'tests'))
  from test_news_investment_service_v1 import ServiceTests
  fixture=ServiceTests();fixture.setUp()
  try:
   binding=skill.load_risk_skill(self.root)['binding'];fixture.answer['skill_context_binding']=binding
   fixture.service.background_guard=lambda answer:skill.require_risk_skill(answer.get('skill_context_binding'),self.root)
   result=fixture.run_job();self.assertEqual(result['status'],'COMPLETE')
   self.assertEqual(result['proposal']['skill_context_binding'],binding)
   (self.root/'skills/us-equity-news-risk/SOUL.md').write_text('changed')
   self.assertEqual(fixture.service.status(result['job_id'])['status'],'STALE')
  finally:fixture.doCleanups()
 def test_background_guard_combines_skill_and_background(self):
  sys.path.insert(0,str(ROOT/'tests'))
  # Load only the fixture factory; model/compose objects stay stage versions.
  from test_news_background_context_v1 import synthetic_package
  for module in (skill,model,event,comp):
   sys.modules[module.__name__]=module;setattr(data,module.__name__.split(".")[-1],module)
  synthetic_package(self.root)
  account={'revision':'r','events':[]};target={'target_id':'t','proposal_id':'p','payload':{'decision':{'payload':{'input_binding':{'search_arguments':{'metadata':{'S':{'ticker':'SNDK'}}}}}}}}
  monthly=SimpleNamespace(snapshot_operation=nullcontext,accounts=SimpleNamespace(read=lambda:account),current=lambda:target)
  answer={'status':'SUCCEEDED','skill_context_binding':skill.load_risk_skill(self.root)['binding']}
  pm=patch.object(model,'analyze_review',side_effect=lambda *a,**k:dict(answer));manual=pm.start();self.addCleanup(pm.stop)
  pe=patch.object(event,'analyze_event',side_effect=lambda *a,**k:dict(answer));automatic=pe.start();self.addCleanup(pe.stop)
  services=[];pipelines=[];real=comp.NewsInvestmentService
  from data.news_event_pipeline_v1 import EventNewsPipeline
  def service(**kw):s=real(**kw);services.append(s);return s
  def pipeline(*a,**kw):p=EventNewsPipeline(*a,**kw);pipelines.append(p);return p
  with patch.object(comp,'NewsInvestmentService',side_effect=service),patch('data.news_event_pipeline_v1.EventNewsPipeline',side_effect=pipeline):
   comp.compose(root=self.root,monthly_view=monthly,observed_daily=SimpleNamespace(preview=lambda **k:None,service=SimpleNamespace(reader=None)),validate=lambda:None)
  from datetime import datetime,timezone
  s=services[0];p=pipelines[0];s.clock=lambda:datetime(2026,10,28,12,tzinfo=timezone.utc)
  answer={'status':'SUCCEEDED','skill_context_binding':skill.load_risk_skill(self.root)['binding']}
  source={'id':'t','security_ids':['S'],'published_at':'2026-10-27T12:00:00Z'}
  with nullcontext():
   first=s.model([source],[{'security_id':'S','ticker':'SNDK'}],self.root/'cache');second=p.analyzer([source],[{'security_id':'S','ticker':'SNDK'}],self.root/'cache')
   self.assertEqual(len(manual.call_args.kwargs['background_sources']),2);self.assertEqual(len(automatic.call_args.kwargs['background_sources']),2)
   s.background_guard(first);s.background_guard(second)
   with self.assertRaisesRegex(ValueError,'BACKGROUND'):s.background_guard(answer)
   without_skill=dict(first);without_skill.pop('skill_context_binding')
   with self.assertRaisesRegex(ValueError,'SKILL'):s.background_guard(without_skill)
   self.assertFalse(p.valid_event({'answer':without_skill}))
if __name__=='__main__':unittest.main()
