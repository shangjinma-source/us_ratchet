"""Saved real synthetic model output through actual composition/service/risk arithmetic.
No live market, account, discovery, network or inference. Transport/clock fixtures
are explicit; this cannot certify an actual market-open transaction.
"""
import sys,json,hashlib,tempfile,shutil,unittest
from pathlib import Path
from copy import deepcopy
from contextlib import nullcontext,closing
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data import news_investment_composition_v1 as comp
from data.news_event_pipeline_v1 import EventNewsPipeline
from data.news_investment_service_v1 import NewsInvestmentService
from test_news_risk_plan_v1 import fixture
ROOT=Path(__file__).resolve().parents[1]
PINS={'model_smoke_input.json':'d79ce261410763108991899323e7a854a4c9f0409b6e368b239d50c569607aeb','model_smoke_result.json':'33a565c7d835cc898d7f9498d1e103bf3e476935fa83d59ccc8262decf56d35e'}
class EndToEnd(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
  shutil.copytree(ROOT/'skills/us-equity-news-risk',root/'skills/us-equity-news-risk')
  for n,h in PINS.items():self.assertEqual(hashlib.sha256((ROOT/'tests/fixtures/news_skill_synthetic_r32'/n).read_bytes()).hexdigest(),h)
  public=json.loads((ROOT/'tests/fixtures/news_skill_synthetic_r32/model_smoke_input.json').read_bytes())
  self.answer=json.loads((ROOT/'tests/fixtures/news_skill_synthetic_r32/model_smoke_result.json').read_bytes())['result']
  self.sid='synthetic:factory';self.now=datetime(2026,10,28,14,tzinfo=timezone.utc)
  self.account,self.preview,_=fixture(held={self.sid:7},targets={self.sid:10},cash='100')
  self.before=deepcopy(self.account)
  self.target={'target_id':'target','proposal_id':'original','payload':{'target_quantities':{self.sid:10},'decision':{'payload':{'input_binding':{'search_arguments':{'metadata':{self.sid:{'ticker':'SYNTHETIC'}}}}}}}}
  monthly=SimpleNamespace(snapshot_operation=nullcontext,accounts=SimpleNamespace(read=lambda:deepcopy(self.account)),current=lambda:deepcopy(self.target))
  self.preview_call=Mock(side_effect=lambda **k:deepcopy(self.preview));services=[];pipelines=[]
  def service(**kw):s=NewsInvestmentService(**kw);services.append(s);return s
  def pipeline(*a,**kw):p=EventNewsPipeline(*a,**kw);pipelines.append(p);return p
  with patch.object(comp,'NewsInvestmentService',side_effect=service),patch('data.news_event_pipeline_v1.EventNewsPipeline',side_effect=pipeline):
   comp.compose(root=root,monthly_view=monthly,observed_daily=SimpleNamespace(preview=self.preview_call,service=SimpleNamespace(reader=None)),validate=lambda:None)
  self.service=services[0];self.pipeline=pipelines[0];self.service.clock=lambda:self.now;self.pipeline.clock=lambda:self.now
  self.pipeline.calendar_window=lambda stamp:{'not_before':'2026-10-28T14:00:00+00:00','valid_until':'2026-10-28T14:10:00+00:00','calendar_sha256':'synthetic-calendar'}
  self.pipeline.set_enabled(True)
  self.binding,positions=self.pipeline.domain();self.assertEqual(positions,public['positions'])
  self.source_result={'sources':{s['id']:s for s in public['sources']},'coverage':[],'fingerprint':'synthetic-source-fixed'}
  self.builder=Mock(return_value=deepcopy(self.source_result));self.service.source_builder=self.builder
  self.service.model=Mock(side_effect=AssertionError('NO_NEW_MODEL'));self.service.collector=Mock(side_effect=AssertionError('NO_NEW_COLLECTION'))
  snapshot={'events':[dict(s,discovered_at=s['observed_at']) for s in public['sources']]};window=self.pipeline.publication_window(snapshot['events'])
  state=self.pipeline.load();state.update(source_generation=1,source_confirmed=True)
  self.pending={'discovered_at':public['sources'][0]['observed_at'],'binding':self.binding,'control_generation':state['control_generation'],'source_generation':1,'snapshot':snapshot,'answer':deepcopy(self.answer),'positions':positions,'source_fingerprint':'synthetic-source-fixed','execution_window':window,'opinion_valid_until':window['valid_until']}
  state['pending']=deepcopy(self.pending);self.pipeline.save(state)
  p=patch('requests.sessions.Session.request',side_effect=AssertionError('NO_NETWORK'));p.start();self.addCleanup(p.stop)
  p=patch('subprocess.Popen',side_effect=AssertionError('NO_PROCESS'));p.start();self.addCleanup(p.stop)
 def start(self):
  with patch('data.news_investment_sources_v1.build_sources',self.builder),patch('data.news_investment_service_v1.Thread.start'):
   code,response=self.service.start_event(self.binding,self.pending)
  self.assertEqual(code,202)
  with closing(self.service.connection()) as c:job=json.loads(c.execute('select document from jobs where id=?',(response['job_id'],)).fetchone()[0])
  return job
 def test_actual_output_to_integer_sell_with_original_cash_and_no_new_inference(self):
  self.assertTrue(self.pipeline.valid_event(self.pending));job=self.start();self.service.run(job);r=self.service.status(job['job_id'])
  self.assertEqual(r['status'],'COMPLETE',r)
  row=r['proposal']['rows'][0];self.assertEqual(row['proposed_target_quantity'],3)
  plan=r['proposal']['risk_plan'];self.assertEqual(plan['status'],'READY',plan)
  self.assertEqual([(x['side'],x['quantity']) for x in plan['candidate_orders']],[('SELL',4)])
  self.assertEqual(plan['cash']['spendable_cash'],'100');self.assertEqual(plan['cash']['new_buy_cash_required'],'0');self.assertFalse(plan['cash']['sell_proceeds_assumed'])
  self.assertFalse(plan['executable']);self.assertFalse(plan['orders_created']);self.assertEqual(self.account,self.before)
  self.assertEqual(self.preview_call.call_count,2);self.service.model.assert_not_called();self.service.collector.assert_not_called()
 def test_before_open_and_account_revision_inflight_refused(self):
  self.now-=timedelta(seconds=1);self.assertFalse(self.pipeline.valid_event(self.pending))
  with self.assertRaisesRegex(ValueError,'EVENT_PIPELINE'):self.start()
  self.now+=timedelta(seconds=1);job=self.start()
  def quote(**kw):self.account['revision']='synthetic-changed';return deepcopy(self.preview)
  self.preview_call.side_effect=quote;self.service.run(job)
  with closing(self.service.connection()) as c:saved=json.loads(c.execute('select document from jobs where id=?',(job['job_id'],)).fetchone()[0])
  self.assertEqual(saved['status'],'FAILED');self.assertNotIn('proposal',saved);self.assertEqual(saved['error'],'STALE_ACCOUNT_OR_TARGET')
  self.service.model.assert_not_called()
if __name__=='__main__':unittest.main()
