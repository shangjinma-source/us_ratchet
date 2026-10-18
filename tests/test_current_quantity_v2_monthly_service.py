import json,unittest
from copy import deepcopy
from datetime import datetime,timedelta
from hashlib import sha256
from tempfile import TemporaryDirectory
from test_current_quantity_v2_continuation_service import fixture as prior_fixture
from test_current_quantity_v2_monthly_retarget import fixture as monthly_fixture
from test_current_quantity_v2_intraday_reference import raw
from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account
from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge


def fixture(folder):
    paper,_,package,_,closed=prior_fixture(folder);store=paper.store;state=store.read(closed['account_id'])
    old=state['ledger']['acceptance']['proposal']['causal_inputs']
    state,a,at=monthly_fixture((state,old));clock=[datetime.fromisoformat(at)+timedelta(seconds=2)]
    files=package['files'];pins=package['source_hashes'];paths={}
    for name in a['source_hashes']:
        if name not in files:files[name]=b'SYNTHETIC METHOD OR REVIEW SOURCE';pins[name]=sha256(files[name]).hexdigest()
    def put(name,value):
        files[name]=json.dumps(value,sort_keys=True).encode();pins[name]=sha256(files[name]).hexdigest();return name
    d=a['capital_decision'];b=d['binding'];search=deepcopy(b['search_arguments'])
    search.update(quote_as_of=d['decision_date'],price_basis='SYNTHETIC_USD')
    d=decide_quantity_v2_for_account(decision_date=d['decision_date'],account_state=dict(asof=d['decision_date'],
        revision=state['ledger']['revision'],cash=state['ledger']['cash'],shares=state['ledger']['shares'],reserved_cash='0'),
        valuation_quotes=[dict(security_id=s,**v) for s,v in b['valuation_quotes'].items()],search_arguments=search,source_hashes=deepcopy(pins))
    a['target_mandate']['capital_decision_id']=d['decision_id'];paths['quote_receipts']={}
    capture=datetime.fromisoformat(at);t=int(capture.timestamp())
    for sid in ('A','B'):
        value=json.loads(raw(a['securities'][sid]['ticker'],2));r=value['chart']['result'][0]
        r['meta'].update(regularMarketTime=t-5,currentTradingPeriod={'regular':{'start':t-9030,'end':t+14370}})
        r['timestamp']=[t-90]
        rp=put(sid+'-new.raw',value);receipt=put(sid+'-new.receipt',dict(security_id=sid,ticker=a['securities'][sid]['ticker'],
            raw_path=rp,raw_sha256=pins[rp],captured_at=at))
        paths['quote_receipts'][sid]=receipt
        unit=a['unit_continuity'][sid];unit.update(capital_decision_id=d['decision_id'],reference_source_hashes={rp:pins[rp],receipt:pins[receipt]},reviewed_at=clock[0].isoformat())
        if sid in a['held_unit_continuity']:
            a['held_unit_continuity'][sid].update(reference_source_hashes=unit['reference_source_hashes'],reviewed_at=clock[0].isoformat())
    for key,val in [('capital_decision',d),('target_mandate',a['target_mandate']),('identities',dict(securities=a['securities'],source_references=['source'])),
        ('unit_continuity',a['unit_continuity']),('held_unit_continuity',a['held_unit_continuity']),
        ('account_review',dict(account_id=closed['account_id'],state_revision=state['ledger']['revision'],pending_rights=[],reviewed_at=at,source_references=['source']))]:
        paths[key]=put('monthly-'+key+'.json',val)
    package={'files':files,'source_hashes':pins,'documents':paths}
    bridge=QuantityV2MonthlySourceBridge(store=store,resolver=lambda aid,did:deepcopy(package),clock=lambda:clock[0])
    return paper,bridge,package,clock,state,d['decision_id']


class MonthlySourceTests(unittest.TestCase):
    def test_raw_preview_delayed_accept_and_source_free_retry(self):
        with TemporaryDirectory() as folder:
            paper,bridge,pkg,clock,state,did=fixture(folder);aid=state['ledger']['account_id']
            view=bridge.preview(account_id=aid,decision_id=did,expected_revision=state['ledger']['revision'])
            self.assertNotIn('causal_inputs',view);self.assertNotIn('binding',view);self.assertTrue(view['source_bytes_verified'])
            clock[0]+=timedelta(seconds=1)
            request=dict(account_id=aid,proposal_id=view['proposal_id'],operation_id='monthly',expected_revision=state['ledger']['revision'],
                factory=lambda c,n:bridge.monthly_resolver(c,view['proposal_id'],n),clock=lambda:clock[0])
            accepted=paper.store.accept_monthly_retarget(**request)
            self.assertEqual(accepted['ledger']['cash'],state['ledger']['cash']);self.assertEqual(accepted['genesis'],state['genesis'])
            bridge._proposals.clear();bridge.resolver=lambda *a:(_ for _ in ()).throw(ValueError('gone'))
            clock[0]+=timedelta(days=90)
            self.assertEqual(paper.store.accept_monthly_retarget(**request),accepted)

    def test_drift_mapping_expiry_rights_and_clockback(self):
        for mode in ('bytes','mapping','expired','rights','clockback'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                paper,bridge,pkg,clock,state,did=fixture(folder);aid=state['ledger']['account_id']
                view=bridge.preview(account_id=aid,decision_id=did,expected_revision=state['ledger']['revision'])
                if mode=='bytes':pkg['files']['A-new.raw']+=b' '
                elif mode=='mapping':pkg['documents']['held_unit_continuity']=pkg['documents']['unit_continuity']
                elif mode=='expired':clock[0]+=timedelta(seconds=121)
                elif mode=='clockback':clock[0]-=timedelta(seconds=1)
                else:pkg['documents'].pop('account_review')
                with self.assertRaises((ValueError,KeyError)):
                    bridge.monthly_resolver(state,view['proposal_id'],clock[0])
                self.assertEqual(paper.store.read(aid),state)

    def test_raw_split_and_final_clock_rejected(self):
        for mode in ('split','empty','slow'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                paper,bridge,pkg,clock,state,did=fixture(folder)
                if mode!='slow':
                    rawpath='A-new.raw';r=json.loads(pkg['files'][rawpath])
                    if mode=='split':r['chart']['result'][0]['events']={'splits':{'x':{'numerator':2,'denominator':1}}}
                    else:r['chart']['result']=[]
                    pkg['files'][rawpath]=json.dumps(r).encode();pkg['source_hashes'][rawpath]=sha256(pkg['files'][rawpath]).hexdigest()
                    rp='A-new.receipt';receipt=json.loads(pkg['files'][rp]);receipt['raw_sha256']=pkg['source_hashes'][rawpath]
                    pkg['files'][rp]=json.dumps(receipt).encode();pkg['source_hashes'][rp]=sha256(pkg['files'][rp]).hexdigest()
                else:
                    count=[0]
                    def slow(*args):
                        count[0]+=1
                        if count[0]==3:clock[0]+=timedelta(seconds=121)
                        return deepcopy(pkg)
                    bridge.resolver=slow
                with self.assertRaises((ValueError,IndexError)):
                    bridge.preview(account_id=state['ledger']['account_id'],decision_id=did,expected_revision=state['ledger']['revision'])
                self.assertEqual(len(bridge._proposals),0)


if __name__=='__main__':unittest.main()
