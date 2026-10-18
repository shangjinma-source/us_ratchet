import unittest,json
from copy import deepcopy
from datetime import datetime,timezone
from tempfile import TemporaryDirectory
from hashlib import sha256
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_training_reader import MonthlyMarketTrainingReader
from data.current_quantity_v2_monthly_training import build_monthly_training_package
from data.current_quantity_v2_paper_review_provider import DerivedPaperReviewProvider
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from test_current_quantity_v2_monthly_training import fixture as market_fixture
from test_current_quantity_v2_current_cash_continuation import fixture as cash_fixture
import test_current_quantity_v2_current_cash_plan as base

def fixture(folder,args):
    registry,_,package,days=market_fixture(folder);state,_,_=cash_fixture(args)
    clock=[datetime(2026,11,2,17,tzinfo=timezone.utc)];calls=[];registry.clock=lambda:clock[0]
    identities=json.loads(package['files']['identities.json']);identities['securities']['A']=deepcopy(state['ledger']['acceptance']['proposal']['securities']['A'])
    package['files']['identities.json']=canonical(identities);package['source_hashes']['identities.json']=sha256(package['files']['identities.json']).hexdigest()
    manifest=json.loads(package['files']['manifest.json']);manifest['source_hashes']['identities.json']=package['source_hashes']['identities.json']
    package['files']['manifest.json']=canonical(manifest);package['source_hashes']['manifest.json']=sha256(package['files']['manifest.json']).hexdigest()
    supplied=dict(source_package=package,manifest_path='manifest.json',calendar_path='calendar.json',identities_path='identities.json',held_bar_sources={'A':'A.held'})
    def daily(ticker,start,end):
        calls.append(ticker);chart=dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),
            timestamp=[int(start.timestamp()),int(end.timestamp())],indicators={'quote':[dict(open=[1,1],high=[1,1],low=[1,1],close=[1,1],volume=[1,1])]},events={})
        return dict(status=200,body=canonical({'chart':{'result':[chart],'error':None}}))
    def rss():
        calls.append('RSS');return dict(status=200,body=b'<rss><channel><item><title>Unrelated notice</title><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>')
    actions=PaperActionEvidenceSources(fetch=daily,rss_fetch=rss,clock=lambda:clock[0])
    provider=DerivedPaperReviewProvider(storage_root=folder+'/proofs',evidence_reader=actions,clock=lambda:clock[0])
    reader=MonthlyMarketTrainingReader(market_reader=lambda _:deepcopy(supplied),paper_review_provider=provider,clock=lambda:clock[0])
    return reader,state,supplied,clock,calls,registry

class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):base.CurrentCashTests.setUpClass();cls.args=base.CurrentCashTests.args
    @classmethod
    def tearDownClass(cls):base.CurrentCashTests.tearDownClass()
    def test_real_cash_chain_derived_training_no_reinjection_and_read_zero_fetch(self):
        with TemporaryDirectory() as folder:
            reader,state,_,clock,calls,registry=fixture(folder,self.args);self.assertEqual(calls,[])
            supplied=reader(state);self.assertEqual(calls,['AAA','BBB','RSS']);before=deepcopy(calls)
            training=build_monthly_training_package(state,**supplied,now=clock[0]);_,arguments,_,_,_=registry._prepare(state,training)
            self.assertEqual(arguments['account_state']['cash'],state['ledger']['cash']);self.assertEqual(arguments['account_state']['shares'],{'A':2})
            self.assertEqual(set(arguments['search_arguments']['prices']),{'B'});self.assertEqual(reader.read(state),supplied);self.assertEqual(calls,before)
            review=json.loads(supplied['source_package']['files'][supplied['account_review_path']]);self.assertFalse(review['coverage_complete'])
    def test_preflight_before_capture_and_saved_market_actions(self):
        for mode in ('pastclose','same_month','identity','action','missing'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                reader,state,supplied,clock,calls,_=fixture(folder,self.args);p=supplied['source_package'];files=p['files'];pins=p['source_hashes']
                path='calendar.json'
                if mode in ('pastclose','same_month'):
                    d=json.loads(files[path]);d['decision_close_at']='2026-10-01T20:00:00+00:00' if mode=='pastclose' else d['decision_close_at']
                    if mode=='same_month':d['target_month']='2026-10'
                elif mode=='identity':path='identities.json';d=json.loads(files[path]);d['securities']['A']['issuer_id']='other'
                elif mode=='action':path='A.held';d=json.loads(files[path]);d['chart']['result'][0]['events']={'dividends':{'x':{'date':int(datetime(2026,10,29,tzinfo=timezone.utc).timestamp()),'amount':1}}}
                else:supplied['held_bar_sources']={};d=None
                if d is not None:
                    files[path]=canonical(d);pins[path]=sha256(files[path]).hexdigest();m=json.loads(files['manifest.json']);m['source_hashes'][path]=pins[path];files['manifest.json']=canonical(m);pins['manifest.json']=sha256(files['manifest.json']).hexdigest()
                with self.assertRaises(ValueError):reader(state)
                if mode in ('pastclose','same_month','missing'):self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
