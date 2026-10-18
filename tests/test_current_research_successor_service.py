from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.current_research_paper_service import CurrentResearchPaperService
from data.current_research_paper_store import ResearchPaperStore
from data.current_research_successor_service import CurrentResearchSuccessorService, MONTHLY_CONTRACT
from data.current_research_limit_plan import build_current_research_limit_plan
import test_current_research_monthly_plan as fixtures


class SuccessorServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=datetime.fromisoformat('2026-10-30T17:00:00-04:00')
        self.base=CurrentResearchPaperService(root=self.root,directory=self.root/'paper',clock=lambda:self.now)
        self.f=fixtures.MonthlyPlanTests();self.f.setUp()
        plan=self.f.state['plan'];self.account='paper-'+plan['plan_id'][:24]
        self.store=ResearchPaperStore(self.base.directory)
        initial=self.store.create(self.account,plan)
        order=plan['orders'][0]
        self.state=self.store.record_fill(self.account,dict(event_id='first',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],order_id=order['order_id'],qty=2,price='50',fees='0',session='2026-10-14',expected_revision=initial['revision']))
        f=self.f.f
        self.bundle=dict(account_id=self.account,revision=self.state['revision'],parent_plan_id=plan['plan_id'],decision_date='2026-10-30',active_date='2026-11-02',calendar=['2026-10-30','2026-11-02'],
            valuation_quotes=[dict(q,as_of='2026-10-30') for q in f.quotes],source_hashes=f.pins,
            held_unit_continuity={'X':dict(f.continuity['X'],to_date='2026-10-30')},
            decision_session=fixtures.session('2026-10-30'),market_session=fixtures.session('2026-11-02'),
            search_arguments=dict(f.args,decision_date='2026-10-30',quote_as_of='2026-10-30',scenario_dates=['2026-10-30']))
        self.bundle['admission'] = dict(reviewed_at=self.now.isoformat())
        self.service=CurrentResearchSuccessorService(base_service=self.base,input_provider=lambda _:deepcopy(self.bundle),search=f.stub)

    def preview(self):
        return self.service.preview(self.account,'input1',self.state['revision'])

    def test_concurrent_cache_one_search_and_immutable_copy(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.preview(),range(2)))
        self.assertEqual(len(self.f.f.calls),1)
        self.assertEqual(results[0]['preview_id'],results[1]['preview_id'])
        results[0]['plan']['orders'].clear()
        self.assertTrue(self.preview()['plan']['orders'])

    def test_activate_atomic_and_exact_retry_after_expiry(self):
        preview=self.preview();revision=self.state['revision']
        activated=self.service.activate(self.account,preview['preview_id'],'activate1',revision)
        self.assertEqual(activated['review']['cash'],'0')
        self.assertEqual(activated['review']['shares'],{'X':2})
        self.bundle['admission']='withdrawn'
        self.now=datetime.fromisoformat('2026-11-03T17:00:00-05:00')
        retried=self.service.activate(self.account,preview['preview_id'],'activate1',revision)
        self.assertTrue(retried['idempotent_replay'])
        self.assertEqual(retried['review']['revision'],activated['review']['revision'])
        with self.assertRaises(ValueError):self.service.activate(self.account,preview['preview_id'],'different',revision)
        self.assertEqual(len(self.f.f.calls),1)

    def test_clocks_missing_provider_expired_cache_and_stale_revision(self):
        self.now=datetime.fromisoformat('2026-10-30T15:00:00-04:00')
        with self.assertRaises(ValueError):self.preview()
        self.assertEqual(self.f.f.calls,[])
        self.now=datetime.fromisoformat('2026-10-30T17:00:00-04:00');p=self.preview()
        self.now=datetime.fromisoformat('2026-11-02T16:00:00-05:00')
        with self.assertRaises(ValueError):self.preview()
        with self.assertRaises(ValueError):self.service.activate(self.account,p['preview_id'],'late',self.state['revision'])
        with self.assertRaises(ValueError):self.service.preview(self.account,'input1','old')
        with self.assertRaisesRegex(ValueError,'UNAVAILABLE'):
            CurrentResearchSuccessorService(base_service=self.base).preview(self.account,'a'*64,self.state['revision'])
        with self.assertRaises(ValueError):self.service.activate(self.account,'missing','id',self.state['revision'])

    def test_cached_preview_and_first_activation_recheck_input(self):
        p=self.preview()
        self.bundle['extra']='changed'
        with self.assertRaises(ValueError):self.preview()
        with self.assertRaises(ValueError):self.service.activate(self.account,p['preview_id'],'changed',self.state['revision'])
        self.assertEqual(len(self.f.f.calls),1)
        self.assertEqual(self.store.read(self.account),self.state)

    def test_initial_policy_adoption_requires_contract_and_exact_initial_kind(self):
        c=deepcopy(self.f.f.initial['plan']['causal_inputs'])
        plan=build_current_research_limit_plan(research_snapshot=c['research_snapshot'],quotes=[dict(v,security_id=s) for s,v in c['quotes'].items()],
            available_cash=c['available_cash'],shares=c['shares'],account_revision=c['account_revision'],decision_date=c['decision_date'],active_date=c['active_date'],calendar=c['calendar'],strategy_version='PAPER_FROZEN_QUANTITY_V1',target_quantities={})
        account='paper-'+plan['plan_id'][:24];state=self.store.create(account,plan)
        bundle=deepcopy(self.bundle);bundle['valuation_quotes']=[];bundle['held_unit_continuity']={}
        bundle.update(account_id=account,revision=state['revision'],parent_plan_id=plan['plan_id'],policy_mode='ADOPT_INITIAL_FROZEN_MONTHLY_POLICY',decision_date='2026-10-14',active_date='2026-10-15',calendar=['2026-10-14','2026-10-15'],decision_session=fixtures.session('2026-10-14'),market_session=fixtures.session('2026-10-15'))
        self.now=datetime.fromisoformat('2026-10-14T17:00:00-04:00')
        bundle['admission'] = dict(reviewed_at=self.now.isoformat())
        service=CurrentResearchSuccessorService(base_service=self.base,input_provider=lambda _:deepcopy(bundle),search=lambda **_:self.fail('ROLL searched'))
        with self.assertRaises(ValueError):service.preview(account,'adopt',state['revision'])
        contract=self.root/MONTHLY_CONTRACT;contract.parent.mkdir();contract.write_bytes(b'synthetic confirmed policy')
        bundle['source_hashes'][MONTHLY_CONTRACT]=hashlib.sha256(contract.read_bytes()).hexdigest()
        result=service.preview(account,'adopt',state['revision'])
        self.assertEqual(result['route']['action'],'ROLL')
        self.assertEqual(result['plan']['causal_inputs']['research_snapshot']['target_month'],'2026-10')
        self.assertNotIn('target_month',self.base._read_account(account)['plan']['causal_inputs']['research_snapshot'])


if __name__=='__main__':unittest.main()
