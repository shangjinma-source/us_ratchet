"""Offline dispatch/service/real HOLD bridge integration with synthetic transport."""
from pathlib import Path
from contextlib import nullcontext
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
import importlib.util, inspect, json, os, sys, unittest

STAGE=Path(os.environ.get('NEWS_RISK_PLAN_STAGE_DIRECTORY','data'))
for name in ('news_risk_plan_v1','news_risk_execution_bridge_v1','news_investment_service_v1','news_investment_composition_v1'):
    spec=importlib.util.spec_from_file_location('data.'+name,STAGE/(name+'.py'));module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
composition=sys.modules['data.news_investment_composition_v1']
service_module=sys.modules['data.news_investment_service_v1']
os.environ['NEWS_HOLD_BRIDGE_CANDIDATE']=str(STAGE/'news_risk_execution_bridge_v1.py')
os.environ['NEWS_RISK_PLAN_CANDIDATE']=str(STAGE/'news_risk_plan_v1.py')
import test_news_risk_execution_bridge_v1 as hold_test
import test_news_risk_plan_v1 as ready_test
from core.strategy_account_ledger import canonical
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider

class CompositionTests(unittest.TestCase):
    def assembled(self,directory):
        callback,args,server,signal,calls,transport=hold_test.HoldBridgeTests().fixture(directory)
        daily=inspect.getclosurevars(callback).nonlocals['composition']
        decision=server['target']['payload']['decision'];p=decision['payload'];p['input_binding']['search_arguments']={'metadata':{'A':{'ticker':'AAA'}}};p['input_id']=sha256(canonical(p['input_binding'])).hexdigest();decision['decision_id']=sha256(canonical(p)).hexdigest()
        monthly_view=daily.monthly_view;monthly_view.accounts=daily.monthly.accounts;monthly_view.snapshot_operation=nullcontext
        observed=SimpleNamespace(service=daily,preview=lambda **kwargs:deepcopy(args['original']))
        captured=[]
        def construct(**kwargs):
            service=service_module.NewsInvestmentService(**kwargs);captured.append(service);return service
        factory_module=sys.modules['data.news_risk_execution_bridge_v1']
        with patch.object(composition,'NewsInvestmentService',side_effect=construct),patch.object(factory_module,'make_hold_risk_plan_adapter',wraps=factory_module.make_hold_risk_plan_adapter) as factory_spy:
            composition.compose(root=Path(directory),monthly_view=monthly_view,observed_daily=observed,validate=lambda:None)
        service=captured[0];service.test_factory_spy=factory_spy;service.clock=lambda:server['clock']
        source_text='Synthetic official evidence: deliveries delayed.';h=sha256(source_text.encode()).hexdigest()
        source=dict(id='s',content_kind='FULL_TEXT',security_ids=['A'],text=source_text,text_sha256=h,published_at='2026-10-28T13:00:00+00:00',observed_at='2026-10-28T13:01:00+00:00')
        service.collector=Mock(return_value={'events':[]})
        service.source_builder=Mock(return_value={'sources':{'s':source},'coverage':[],'fingerprint':'synthetic'})
        service.model=Mock(return_value={'status':'SUCCEEDED','model':'mock-not-an-actual-call','rows':[dict(security_id='A',action='REDUCE_HOLDING',holding_fraction='1/2',reason='Synthetic risk',counterevidence=[],uncertainty=['Synthetic test only'],evidence=[dict(source_id='s',source_sha256=h,quote=source_text)])]})
        return service,server,args,daily,calls,transport

    def run_service(self,service,server):
        binding=dict(expected_revision=server['state']['revision'],target_id='target',expected_proposal_id='monthly')
        service.run(dict(job_id='synthetic-hold',status='RUNNING',started_at=server['clock'].isoformat(),binding=binding))
        return service.status('synthetic-hold')

    def test_hold_real_review_to_real_adapter_to_status(self):
        with TemporaryDirectory() as directory:
            service,server,args,daily,calls,transport=self.assembled(directory);before=deepcopy(server['state'])
            with patch.object(StrategyAccountEvidenceProvider,'_assemble',transport):result=self.run_service(service,server)
            self.assertEqual(result['status'],'COMPLETE',result);self.assertIs(service.test_factory_spy.call_args.kwargs['composition'],daily)
            proposal=result['proposal'];plan=proposal['risk_plan'];self.assertEqual(plan['status'],'READY',plan)
            self.assertEqual(proposal['rows'][0]['proposed_target_quantity'],5)
            self.assertEqual([(x['side'],x['quantity']) for x in plan['candidate_orders']],[('SELL',5)])
            self.assertFalse(plan['cash']['sell_proceeds_assumed']);self.assertEqual(plan['cash']['new_buy_cash_required'],'0');self.assertEqual(before,server['state']);self.assertEqual(service.model.call_count,1)
            output_path=os.environ.get('NEWS_RISK_PLAN_FIXTURE_OUTPUT')
            if output_path:
                output=Path(output_path);output.parent.mkdir(parents=True,exist_ok=True)
                output.write_text(json.dumps(proposal,ensure_ascii=False,indent=2),encoding='utf-8')

    def test_news_generation_changes_during_capture_never_publishes(self):
        with TemporaryDirectory() as directory:
            service,server,args,daily,calls,transport=self.assembled(directory);generation=[0];service.news_generation=lambda:generation[0]
            def changed(*a,**k):
                result=transport(*a,**k);generation[0]+=1;return result
            with patch.object(StrategyAccountEvidenceProvider,'_assemble',changed):result=self.run_service(service,server)
            self.assertEqual(result['status'],'FAILED',result);self.assertEqual(result['error'],'NEWS_UPDATED_DURING_ANALYSIS');self.assertNotIn('proposal',result)

    def test_ready_dispatch_uses_pure_builder_without_hold_factory(self):
        with TemporaryDirectory() as directory:
            service,*_=self.assembled(directory);state,original,proposal=ready_test.fixture();proposal['rows'][0].update(action='REDUCE_HOLDING',proposed_target_quantity=2)
            with patch('data.news_risk_execution_bridge_v1.make_hold_risk_plan_adapter',side_effect=AssertionError('READY must not capture HOLD')):
                result=service.risk_plan_provider(original=original,proposal=proposal,account=state,target={},now=hold_test.NOW)
            self.assertEqual(result['status'],'READY',result);self.assertEqual(result['candidate_orders'][0]['quantity'],2);self.assertEqual(service.test_factory_spy.call_count,0)

if __name__=='__main__':unittest.main()
