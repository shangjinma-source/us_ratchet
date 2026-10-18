from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_difference_service import fixture as original_fixture
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from api.current_quantity_v2_difference import create_router


def fixture():
    service,_,package,account,clock=original_fixture()
    files=package['files'];pins=package['source_hashes'];paths=package['documents']
    def get(key):return json.loads(files[paths[key]])
    def put(key,value):
        name=paths.setdefault(key,key+'.json');files[name]=json.dumps(value,sort_keys=True).encode()
        pins[name]=sha256(files[name]).hexdigest()
    decision=get('capital_decision');b=decision['binding']
    b.update(available_cash='100',shares={},valuation_quotes={})
    decision.update(available_cash='100',holding_market_values={})
    identifier=sha256(json.dumps(b,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    decision.update(decision_id=identifier,research_id=identifier[:24]);put('capital_decision',decision)
    account.update(cash='100',shares={})
    mandate=get('target_mandate');mandate['capital_decision_id']=identifier;put('target_mandate',mandate)
    identity=get('identities');identity['securities'].pop('X');put('identities',identity)
    units=get('unit_continuity');units.pop('X');units['A']['capital_decision_id']=identifier;put('unit_continuity',units)
    paths['quote_receipts'].pop('X')
    put('genesis_declaration',dict(purpose='PAPER_INITIALIZATION_NOT_BROKER_BALANCE',account_id=account['account_id'],
        research_id=decision['research_id'],decision_id=identifier,capital_origin_revision=account['revision'],
        initial_cash_exact='100',target_month=mandate['target_month'],declared_at=account['observed_at'],source_references=['source']))
    return service,identifier,package,account,clock


class CashServiceTests(unittest.TestCase):
    def test_private_pure_proposal_to_store_and_http_compact(self):
        service,identifier,package,account,clock=fixture()
        proposal=service._proposal(identifier)
        self.assertEqual(proposal['status'],'READY');self.assertIn('causal_inputs',proposal)
        self.assertNotIn('source_authenticated',proposal)
        self.assertEqual(proposal['causal_inputs']['target_scope'],'NEW_CASH_STRATEGY_INITIAL_TARGET')
        with TemporaryDirectory() as folder:
            store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3')
            def factory(now):return dict(proposal=service._proposal(identifier),account_state=deepcopy(account))
            state=store.accept(account_id=account['account_id'],proposal_id=proposal['proposal_id'],operation_id='first',factory=factory,clock=lambda:clock[0])
            self.assertEqual(state['ledger']['cash'],'100');self.assertEqual(state['ledger']['shares'],{})
        app=FastAPI();app.include_router(create_router(service=service))
        with TestClient(app) as client:
            response=client.post('/api/current_portfolio_research/difference',json={'decision_id':identifier})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['target_scope'],'NEW_CASH_STRATEGY_INITIAL_TARGET')
            self.assertEqual(response.json()['research_id'],identifier[:24])
            self.assertNotIn('causal_inputs',response.json());self.assertNotIn('files',response.json())
            self.assertNotIn('genesis_declaration',response.json())

    def test_genesis_byte_tamper_wrong_binding_and_account_drift(self):
        for mode in ('bytes','binding','account'):
            service,identifier,p,account,_=fixture();name=p['documents']['genesis_declaration']
            if mode=='bytes':p['files'][name]+=b' '
            elif mode=='binding':
                doc=json.loads(p['files'][name]);doc['initial_cash_exact']='999'
                p['files'][name]=json.dumps(doc).encode();p['source_hashes'][name]=sha256(p['files'][name]).hexdigest()
            else:account['cash']='99'
            with self.assertRaises(ValueError):service._proposal(identifier)
            result=service.preview(identifier);self.assertEqual(result['status'],'UNAVAILABLE');self.assertEqual(result['orders'],[])


if __name__=='__main__':unittest.main()
