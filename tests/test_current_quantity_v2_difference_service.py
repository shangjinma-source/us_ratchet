import json
import unittest
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_difference_plan import fixture as plan_fixture
from test_current_quantity_v2_intraday_reference import raw, NOW
from data.current_quantity_v2_difference_service import CurrentQuantityV2DifferenceService
from api.current_quantity_v2_difference import create_router


def fixture():
    a=plan_fixture();files={'source':b'SYNTHETIC REVIEW EVIDENCE ONLY'}
    pins={'source':sha256(files['source']).hexdigest()}
    a['capital_decision']['binding']['source_hashes']=deepcopy(pins)
    d=a['capital_decision']
    identifier=sha256(json.dumps(d['binding'],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    d['decision_id']=identifier;d['research_id']=identifier[:24]
    a['target_mandate']['capital_decision_id']=identifier
    for unit in a['unit_continuity'].values():unit['capital_decision_id']=identifier
    d=a['capital_decision'];paths={}
    def put(name,value):
        files[name]=json.dumps(value,sort_keys=True).encode();pins[name]=sha256(files[name]).hexdigest()
        return name
    paths['quote_receipts']={}
    for sid in ('A','X'):
        ticker=a['securities'][sid]['ticker'];name=sid+'.raw'
        files[name]=raw(ticker,9 if sid=='A' else 50);pins[name]=sha256(files[name]).hexdigest()
        path=put(sid+'.receipt',dict(security_id=sid,ticker=ticker,raw_path=name,
            raw_sha256=pins[name],captured_at=NOW.isoformat()))
        paths['quote_receipts'][sid]=path
        a['unit_continuity'][sid]['reference_source_hashes']={path:pins[path],name:pins[name]}
        a['unit_continuity'][sid]['valuation_source_references']=['source']
        a['unit_continuity'][sid]['reviewed_at']=(NOW+timedelta(seconds=1)).isoformat()
    for key,value in [('capital_decision',d),('target_mandate',a['target_mandate']),
                      ('identities',dict(securities=a['securities'],source_references=['source'])),
                      ('unit_continuity',a['unit_continuity'])]:paths[key]=put(key+'.json',value)
    package=dict(files=files,source_hashes=pins,documents=paths)
    account=deepcopy(a['account_state']);clock=[NOW+timedelta(seconds=2)]
    service=CurrentQuantityV2DifferenceService(resolver=lambda _:deepcopy(package),
        account_reader=lambda _:deepcopy(account),clock=lambda:clock[0])
    return service,d['decision_id'],package,account,clock


class ServiceTests(unittest.TestCase):
    def test_real_raw_replay_and_cash_conservation(self):
        s,id,p,a,_=fixture();before=deepcopy((p,a));r=s.preview(id)
        self.assertEqual(r['status'],'READY',r)
        self.assertEqual(r['orders'],[dict(security_id='X',side='SELL',quantity=2,limit_price='50')])
        self.assertEqual(r['reserved_buy_cash'],'0');self.assertTrue(r['source_bytes_verified'])
        self.assertFalse(r['source_authenticated']);self.assertNotIn('causal_inputs',r)
        self.assertEqual((p,a),before)

    def test_raw_tamper_account_omissions_and_staleness_clear_orders(self):
        for mode in ('raw','orders','stale','unit'):
            s,id,p,a,c=fixture()
            if mode=='raw':p['files']['X.raw']+=b' '
            if mode=='orders':a.pop('open_orders')
            if mode=='stale':c[0]+=timedelta(seconds=121)
            if mode=='unit':p['files']['unit_continuity.json']=b'{}'
            r=s.preview(id);self.assertEqual(r['status'],'UNAVAILABLE');self.assertEqual(r['orders'],[])

    def test_repeated_account_and_decision_read_detect_drift(self):
        for mode in ('account','decision'):
            s,id,p,a,c=fixture();calls=[0]
            def read(_):
                calls[0]+=1
                obj=deepcopy(a if mode=='account' else p)
                if calls[0]>1:
                    if mode=='account':obj['revision']='changed'
                    else:obj['source_hashes']['source']='0'*64
                return obj
            if mode=='account':s.account_reader=read
            else:s.resolver=read
            r=s.preview(id);self.assertEqual(r['status'],'UNAVAILABLE');self.assertEqual(r['orders'],[])

    def test_http_only_identifier_and_no_raw_exposure(self):
        s,id,_,_,_=fixture();app=FastAPI();app.include_router(create_router(service=s))
        with TestClient(app) as client:
            r=client.post('/api/current_portfolio_research/difference',json={'decision_id':id})
            self.assertEqual(r.status_code,200,r.text)
            self.assertNotIn('causal_inputs',r.json());self.assertNotIn('files',r.json())
            for extra in ('cash','quotes','paths','account_id'):
                self.assertEqual(client.post('/api/current_portfolio_research/difference',json={'decision_id':id,extra:1}).status_code,400)
            self.assertEqual(client.post('/api/current_portfolio_research/difference?x=1',json={'decision_id':id}).status_code,400)
            self.assertEqual(client.post('/api/current_portfolio_research/difference',content='{"decision_id":"'+id+'","decision_id":"'+id+'"}').status_code,400)

    def test_unavailable_service_cannot_leak_prior_orders(self):
        s,id,_,_,_=fixture()
        previous=s.preview(id);previous['status']='UNAVAILABLE'
        s.preview=lambda _:previous
        app=FastAPI();app.include_router(create_router(service=s))
        with TestClient(app) as client:
            response=client.post('/api/current_portfolio_research/difference',json={'decision_id':id})
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json()['orders'],[])
            self.assertIsNone(response.json()['proposal_id'])

    def test_controlled_reason_only_no_raw_error_or_stale_orders(self):
        s,id,_,_,_=fixture();prior=s.preview(id)
        app=FastAPI();app.include_router(create_router(service=s))
        with TestClient(app) as client:
            for reason in ('OUTSIDE_REGULAR_SESSION','LAST_QUOTE_STALE','NO_COMPLETED_VALID_MINUTE','MONTH_MANDATE_REQUIRED','RESELECT_REQUIRED','EXECUTION_MONTH_NOT_ACTIVE','private/path:secret'):
                for raises in (False,True):
                    def failed(_):
                        if raises:raise ValueError(reason)
                        return dict(prior,status='UNAVAILABLE',reason=reason)
                    s.preview=failed
                    response=client.post('/api/current_portfolio_research/difference',json={'decision_id':id})
                    self.assertEqual(response.status_code,503)
                    self.assertEqual(response.json()['reason'],reason if reason!='private/path:secret' else 'SOURCE_UNAVAILABLE')
                    self.assertEqual(response.json()['orders'],[]);self.assertIsNone(response.json()['proposal_id'])
                    self.assertNotIn('private',response.text)


if __name__=='__main__':unittest.main()
