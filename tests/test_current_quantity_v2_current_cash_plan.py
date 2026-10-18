import json
import unittest
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
from test_current_quantity_portfolio_research_v2 import fixture as source_fixture
from test_current_quantity_v2_intraday_reference import NOW,raw
from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2
from data.current_quantity_v2_current_cash_plan import build_current_cash_plan,rebuild_current_cash_plan,BASIS


def package_fixture(root,decision):
    files={p:(root/p).read_bytes() for p in decision['binding']['source_hashes']}
    pins={p:sha256(v).hexdigest() for p,v in files.items()}
    def put(name,value):
        files[name]=json.dumps(value,sort_keys=True).encode();pins[name]=sha256(files[name]).hexdigest();return name
    evidence=put('current/review-evidence.json',{'synthetic':True,'scope':'current quote identity only'})
    identities={};reviews={};receipts={}
    for sid,q in decision['target_quantities'].items():
        if not q:continue
        meta=decision['binding']['search_arguments']['metadata'][sid];ticker=meta['ticker']
        rawpath='current/'+sid+'.raw';files[rawpath]=raw(ticker,10);pins[rawpath]=sha256(files[rawpath]).hexdigest()
        receiptpath=put('current/'+sid+'.receipt',dict(security_id=sid,ticker=ticker,raw_path=rawpath,
            raw_sha256=pins[rawpath],captured_at=NOW.isoformat()));receipts[sid]=receiptpath
        identities[sid]=dict(security_id=sid,ticker=ticker,issuer_id=meta['issuer_id'],currency='USD',
            security_class='COMMON_SYNTHETIC',source_references=[evidence])
        reviews[sid]=dict(identities[sid],status='CONDITIONAL_CURRENT_QUOTE_IDENTITY',price_basis=BASIS,
            session=NOW.date().isoformat(),quote_captured_at=NOW.isoformat(),reviewed_at=(NOW+timedelta(seconds=1)).isoformat(),
            reference_source_hashes={rawpath:pins[rawpath],receiptpath:pins[receiptpath]},known_actions=[])
    docs=dict(identities=put('current/identities.json',identities),current_unit_reviews=put('current/units.json',reviews),quote_receipts=receipts)
    anchor=next(iter(decision['binding']['source_hashes']))
    docs['execution_month_mandate']=put('current/month.json',dict(schema='V2_INITIAL_EXECUTION_MONTH_V1',
        mode='INITIAL_CURRENT_MONTH_BOOTSTRAP',decision_date=decision['decision_date'],target_month='2026-10',
        first_active_session=decision['decision_date'],original_source_hashes=deepcopy(decision['binding']['source_hashes']),source_hashes={},calendar_path=None))
    b=decision['binding'];observed=(NOW-timedelta(seconds=10)).isoformat()
    account=dict(account_id='synthetic-new-pool',revision=b['state_revision'],cash=b['available_cash'],shares={},
        observed_at=observed,open_orders=[],reserved_cash='0',reserved_shares={},pending_rights=[])
    genesis=dict(purpose='PAPER_INITIALIZATION_NOT_BROKER_BALANCE',account_id=account['account_id'],
        decision_id=decision['decision_id'],research_id=decision['research_id'],capital_origin_revision=b['state_revision'],
        initial_cash_exact=b['available_cash'],target_month='2026-10',active_date='2026-10-15',declared_at=observed,source_references=[evidence])
    return dict(capital_decision=deepcopy(decision),account_state=account,genesis_declaration=genesis,
        execution_package=dict(files=files,source_hashes=pins,documents=docs),now=(NOW+timedelta(seconds=2)).isoformat())


def resign(args,key,change):
    p=args['execution_package'];path=p['documents'][key];value=json.loads(p['files'][path]);change(value)
    p['files'][path]=json.dumps(value).encode();p['source_hashes'][path]=sha256(p['files'][path]).hexdigest()


class CurrentCashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();root=Path(cls.temp.name);_,_,descriptor=source_fixture(root)
        service=CurrentQuantityPortfolioResearchV2(root=root,source_loader=lambda:deepcopy(descriptor))
        with patch('data.current_quantity_portfolio_research_v2.subprocess.run',wraps=subprocess.run) as worker:
            view=service.calculate('110');decision=service.decision(view['research_id'])
            cls.args=package_fixture(root,decision);cls.worker_calls=worker.call_count
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_real_tiny_original_decision_dollar_envelopes_allow_more_shares_and_replay(self):
        args=deepcopy(self.args);before=deepcopy(args);r=build_current_cash_plan(**args)
        self.assertEqual(r['status'],'READY',r);self.assertEqual(self.worker_calls,1)
        self.assertEqual(r['execution_target_quantities'],{'A':6,'B':4})
        self.assertEqual(r['original_residual_cash'],'10');self.assertEqual(r['remaining_cash'],'20')
        self.assertEqual(r['indicative_notional'],'90');self.assertEqual(r['frozen_allocation_total'],'100')
        self.assertTrue(all(row['current_quantity']>row['historical_reference_quantity'] for row in r['rows']))
        self.assertEqual(sum(Fraction(row['notional'])+Fraction(row['allocation_residual']) for row in r['rows']),100)
        self.assertEqual(args,before);self.assertEqual(rebuild_current_cash_plan(r,args['execution_package']),r)
        self.assertFalse(r['source_authenticated']);self.assertFalse(r['ledger_acceptance_supported']);json.dumps(r)
        bad=deepcopy(r);bad['orders'][0]['quantity']+=1
        with self.assertRaises(ValueError):rebuild_current_cash_plan(bad,args['execution_package'])

    def test_missing_identity_units_source_or_account_encumbrance_rejected(self):
        modes=['shares','orders','rights','missingfield','cash','genesis','unit','class','knownaction','bytes','path','nan']
        for mode in modes:
            a=deepcopy(self.args)
            if mode=='shares':a['account_state']['shares']={'A':1}
            elif mode=='orders':a['account_state']['open_orders']=[{'id':'open'}]
            elif mode=='rights':a['account_state']['pending_rights']=[{'id':'unknown'}]
            elif mode=='missingfield':a['account_state'].pop('pending_rights')
            elif mode=='cash':a['account_state']['cash']='109'
            elif mode=='genesis':a['genesis_declaration']['active_date']='2026-10-14'
            elif mode=='unit':resign(a,'current_unit_reviews',lambda v:v.pop('A'))
            elif mode=='class':resign(a,'current_unit_reviews',lambda v:v['A'].update(security_class='OTHER'))
            elif mode=='knownaction':resign(a,'current_unit_reviews',lambda v:v['A'].update(known_actions=[{'split':2}]))
            elif mode=='bytes':a['execution_package']['files']['current/A.raw']+=b' '
            elif mode=='path':a['execution_package']['files']['../bad']=b'x';a['execution_package']['source_hashes']['../bad']=sha256(b'x').hexdigest()
            else:a['genesis_declaration']['extra']=float('nan')
            with self.subTest(mode=mode):self.assertEqual(build_current_cash_plan(**a)['status'],'BLOCKED')

    def test_future_capture_tick_partial_minute_and_expiry_rejected(self):
        for mode in ('capture','tick','partial','stale','deadline','action'):
            a=deepcopy(self.args);p=a['execution_package'];rp=p['documents']['quote_receipts']['A'];receipt=json.loads(p['files'][rp]);rawpath=receipt['raw_path'];value=json.loads(p['files'][rawpath]);r=value['chart']['result'][0]
            if mode=='capture':receipt['captured_at']=(NOW+timedelta(seconds=5)).isoformat()
            elif mode=='tick':r['meta']['regularMarketTime']=int(NOW.timestamp())+1
            elif mode=='partial':r['timestamp']=[int(NOW.replace(second=0).timestamp())]
            elif mode=='stale':a['now']=(NOW+timedelta(seconds=121)).isoformat()
            elif mode=='deadline':a['now']=(NOW.replace(second=0)+timedelta(seconds=120)).isoformat()
            else:r['events']={'splits':{'1':{'numerator':2,'denominator':1}}}
            p['files'][rawpath]=json.dumps(value).encode();p['source_hashes'][rawpath]=sha256(p['files'][rawpath]).hexdigest();receipt['raw_sha256']=p['source_hashes'][rawpath]
            p['files'][rp]=json.dumps(receipt).encode();p['source_hashes'][rp]=sha256(p['files'][rp]).hexdigest()
            with self.subTest(mode=mode):self.assertEqual(build_current_cash_plan(**a)['status'],'BLOCKED')

if __name__=='__main__':unittest.main()
