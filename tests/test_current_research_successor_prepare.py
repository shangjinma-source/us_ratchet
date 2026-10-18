from copy import deepcopy
from datetime import datetime
import hashlib
import json
import unittest

from data.current_research_successor_prepare import prepare_successor_input, save_prepared_input
from data.current_research_successor_inputs import SuccessorInputLoader
from data.current_research_paper_service import CurrentResearchPaperService
from data.current_research_successor_service import CurrentResearchSuccessorService
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import initialize_paper_ledger, apply_paper_fill, apply_paper_order_event
from data.current_research_paper_store import ResearchPaperStore
import test_current_research_saved_quote as quote_fixtures
import test_current_research_monthly_plan as plan_fixtures


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.f=quote_fixtures.SavedQuoteTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        self.f.channel['timestamp']=[1791984600]
        self.f.channel['indicators']['quote']=[dict(open=[10],high=[11],low=[9],close=[10.25])]
        self.f.channel['meta']['regularMarketTime']=1792008000
        self.f.channel['events']={};self.f.received='2026-10-14T21:00:00+00:00'
        (self.root/'evidence').write_bytes(b'Synthetic reviewed units and session evidence')
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        self.pins={'evidence':digest(self.root/'evidence')}
        sessions=[dict(plan_fixtures.session(day),source='evidence') for day in ['2026-10-14','2026-10-15']]
        artifact=dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',calendar=[s['date'] for s in sessions],sessions=sessions,source_hashes=deepcopy(self.pins))
        (self.root/'calendar.json').write_text(json.dumps(artifact));self.pins['calendar.json']=digest(self.root/'calendar.json')
        plan=build_current_research_limit_plan(research_snapshot=dict(research_id='a'*24,as_of='2026-10-13',stocks=[dict(security_id='A',ticker='AAA')],source_hashes={'evidence':self.pins['evidence']},target_month='2026-10'),
            quotes=[dict(security_id='A',price='10',as_of='2026-10-13',price_kind='DECLARED_DECIMAL_REFERENCE',price_basis='UNIT',source_references=['evidence'])],available_cash='100',shares={},account_revision='initial',decision_date='2026-10-13',active_date='2026-10-14',calendar=['2026-10-13','2026-10-14'],strategy_version='old',target_quantities={'A':2})
        self.initial=initialize_paper_ledger(plan,'paper-'+plan['plan_id'][:24])
        self.fill=dict(event_id='fill',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],order_id=plan['orders'][0]['order_id'],qty=2,price='10',fees='0',session='2026-10-14',expected_revision=self.initial['revision'])
        self.state=apply_paper_fill(self.initial,self.fill)
        self.kw=dict(root=self.root,expected_revision=self.state['revision'],decision_date='2026-10-14',active_date='2026-10-15',calendar_path='calendar.json',source_hashes=self.pins,
            held_unit_continuity={'A':dict(from_date='2026-10-13',to_date='2026-10-14',price_basis='UNIT',status='NO_UNPROCESSED_ACTIONS',source_references=['evidence'])},
            admission=dict(status='ACCEPTED_CONDITIONAL_RESEARCH_INPUT',reviewer='synthetic',reviewed_at='2026-10-14T17:00:00-04:00',evidence_references=['evidence'],limitations=['Synthetic reviewed inputs; no real market certification.']))

    def raw(self):
        # Existing decoder fixture writes files before its intentionally mismatched old-date read.
        try:self.f.read()
        except ValueError:pass
        digest=lambda name:hashlib.sha256((self.root/name).read_bytes()).hexdigest()
        return {'A':dict(ticker='AAA',expected_security_type='EQUITY',relative_directory='.',price_basis='UNIT',source_references=['evidence'],entry=dict(raw_sha256=digest('AAA.response.bin'),receipt_sha256=digest('AAA.receipt.json'),decoded_sha256=digest('AAA.decoded.json')))}

    def prepare(self):
        return prepare_successor_input(self.state,raw_sources=self.raw(),**self.kw)

    def test_end_to_end_temp_export_loader_service_no_search(self):
        before=set(self.root.iterdir());sources=self.raw();before=set(self.root.iterdir())
        result=prepare_successor_input(self.state,raw_sources=sources,**self.kw)
        self.assertEqual(set(self.root.iterdir()),before)
        saved=save_prepared_input(result,root=self.root,relative_directory='prepared',registry_path='registry.json')
        loader=SuccessorInputLoader(root=self.root,registry_path='registry.json')
        self.assertEqual(loader(saved['input_id']),result['bundle'])
        base=CurrentResearchPaperService(root=self.root,directory=self.root/'paper',clock=lambda:datetime.fromisoformat('2026-10-14T17:00:00-04:00'))
        store=ResearchPaperStore(base.directory);store.create(self.state['account_id'],self.initial['plan']);store.record_fill(self.state['account_id'],self.fill)
        service=CurrentResearchSuccessorService(base_service=base,input_provider=loader,search=lambda **_:self.fail('Unexpected search'))
        preview=service.preview(self.state['account_id'],saved['input_id'],self.state['revision'])
        self.assertEqual(preview['route']['action'],'ROLL');self.assertEqual(preview['plan']['target_quantities'],{'A':2})
        self.assertEqual(store.read(self.state['account_id']),self.state)
        with self.assertRaises(ValueError):save_prepared_input(result,root=self.root,relative_directory='prepared',registry_path='registry.json')

    def test_split_blocks_and_dividend_only_disclosed(self):
        self.f.channel['events']={'splits':{'e':dict(date=1791984600,numerator=2,denominator=1)}}
        with self.assertRaisesRegex(ValueError,'RETURNED_SPLIT'):self.prepare()
        self.f.channel['events']={'dividends':{'d':dict(date=1791984600,amount=.1)}}
        result=self.prepare();self.assertEqual(len(result['bundle']['returned_dividends']),1)
        self.assertEqual(self.state['cash'],'80')

    def test_unknown_exposed_action_blocks_despite_continuity_declaration(self):
        self.f.channel['events']={'merger':{'m':dict(date=1791984600,successor='BBB')}}
        before=deepcopy(self.state)
        with self.assertRaisesRegex(ValueError,'UNKNOWN_EXPOSED_CORPORATE_ACTION'):
            self.prepare()
        self.assertEqual(self.state,before)

    def test_no_implicit_continuity_and_no_open_order_mutation(self):
        self.kw['held_unit_continuity']={}
        with self.assertRaisesRegex(ValueError,'CONTINUITY'):self.prepare()
        self.kw['expected_revision']=self.initial['revision']
        with self.assertRaisesRegex(ValueError,'OPEN_ORDERS'):prepare_successor_input(self.initial,raw_sources=self.raw(),**self.kw)
        self.assertEqual(self.initial['events'],[])

    def test_reselect_does_not_apply_old_unheld_target_split_block(self):
        c=deepcopy(self.initial['plan']['causal_inputs'])
        c['research_snapshot']['target_month']='2026-09'
        plan=build_current_research_limit_plan(research_snapshot=c['research_snapshot'],quotes=[dict(v,security_id=k) for k,v in c['quotes'].items()],available_cash=c['available_cash'],shares=c['shares'],account_revision=c['account_revision'],decision_date=c['decision_date'],active_date=c['active_date'],calendar=c['calendar'],strategy_version=c['strategy_version'],target_quantities=c['target_quantities'])
        state=initialize_paper_ledger(plan,'synthetic')
        state=apply_paper_order_event(state,dict(event_id='cancel',mode='PAPER_MANUAL_FILL',event_type='CANCEL',plan_id=plan['plan_id'],order_id=plan['orders'][0]['order_id'],expected_revision=state['revision']))
        self.state=state;self.kw['expected_revision']=state['revision'];self.kw['held_unit_continuity']={}
        self.kw['search_arguments']=dict(prices={'A':'10.25'},metadata={'A':dict(ticker='AAA',issuer_id='IA')},price_basis='UNIT',decision_date='2026-10-14',quote_as_of='2026-10-14')
        self.f.channel['events']={'splits':{'e':dict(date=1791984600,numerator=2,denominator=1)}}
        result=self.prepare()
        self.assertEqual(result['bundle']['preparation_route']['action'],'RESELECT')
        self.assertEqual(result['bundle']['held_unit_continuity'],{})

    def test_exact_raw_close_kept_despite_cent_matching_regular_price(self):
        self.f.channel['indicators']['quote'][0]['close']=[10.249999046325684]
        result=self.prepare()
        quote=result['bundle']['valuation_quotes'][0]
        self.assertEqual(quote['price'],'10.249999046325684')
        self.assertEqual(quote['price_kind'],'RAW_PROVIDER_CLOSE_DECIMAL')
        self.assertEqual(result['bundle']['saved_quote_observations']['A']['reference_quote']['price'],'10.25')

    def test_source_or_coordinate_mismatch_rejected(self):
        sources=self.raw();sources['A']['price_basis']='DIFFERENT'
        with self.assertRaisesRegex(ValueError,'BASIS'):prepare_successor_input(self.state,raw_sources=sources,**self.kw)
        (self.root/'evidence').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH'):self.prepare()

if __name__=='__main__':unittest.main()
