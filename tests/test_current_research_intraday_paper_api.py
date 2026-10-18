import tempfile
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.current_research_intraday_paper as routes
import test_current_research_intraday_paper_service as fixtures
from test_current_research_intraday_execution import NOW

BASE='/api/research_paper/intraday_paper'
RID='a'*24

class RouteTests(unittest.TestCase):
    def client(self):
        app=FastAPI();app.include_router(routes.router);return TestClient(app)
    def test_temp_end_to_end_compact_and_retry(self):
        with tempfile.TemporaryDirectory() as root:
            service,reference,clock=fixtures.ServiceTests().fixture(root)
            with patch.object(routes,'SERVICE',service),self.client() as client:
                r=client.post(BASE+'/preview',json={'research_id':RID});self.assertEqual(r.status_code,200,r.text)
                p=r.json()['proposal'];self.assertFalse((Path(root)/'store').exists())
                request=dict(research_id=RID,proposal_id=p['proposal_id'],operation_id='op')
                r=client.post(BASE+'/accept',json=request);self.assertEqual(r.status_code,200,r.text);state=r.json()['account']
                clock[0]+=timedelta(minutes=5)
                self.assertEqual(client.post(BASE+'/accept',json=request).json()['account'],state)
                event=dict(event_id='f',kind='FILL',expected_revision=state['revision'],order_id=state['order']['order_id'],quantity=1,price='1400',fees='1',executed_at=(NOW+timedelta(minutes=4)).isoformat())
                r=client.post(BASE+'/event',json=dict(research_id=RID,event=event));self.assertEqual(r.status_code,200,r.text)
                account=r.json()['account'];self.assertEqual(account['cash'],'18599')
                self.assertEqual(client.post(BASE+'/event',json=dict(research_id=RID,event=event)).json()['account'],account)
                text=r.text
                for forbidden in ('original_files','causal_inputs','captures','base64','research_binding'):self.assertNotIn(forbidden,text)
                self.assertEqual(client.get(BASE+'/account',params={'research_id':RID}).json()['account'],account)
                reference.fetch=lambda _:self.fail('restore fetched')
                self.assertEqual(client.post(BASE+'/preview',json={'research_id':RID}).json()['status'],'EXISTING_ACCOUNT')
    def test_serializer_bounds_and_removes_internal_paths(self):
        import json
        from copy import deepcopy
        with tempfile.TemporaryDirectory() as root:
            service,_,_=fixtures.ServiceTests().fixture(root)
            proposal=service.preview(RID)['proposal']
            compact=routes.compact_proposal(proposal)
            self.assertEqual(set(compact['market_session']),{'date','timezone','open_at','close_at'})
            state=service.accept(RID,proposal['proposal_id'],'serializer')
            synthetic=deepcopy(state)
            synthetic['events']=[dict(event_id=str(i),kind='FILL',quantity=1,price='1/4',recorded_at=NOW.isoformat(),internal_path='secret/source.json') for i in range(25)]
            account=routes.compact_account(synthetic)
            self.assertEqual(account['initial_cash'],'20000');self.assertEqual(account['recorded_buy_notional'],'25/4')
            self.assertEqual(account['event_count'],25);self.assertTrue(account['has_more_events'])
            self.assertEqual(len(account['events']),20);self.assertEqual(account['events'][0]['event_id'],'5')
            text=json.dumps([compact,account])
            for forbidden in ('causal_inputs','"acceptance"','base64','source_references','internal_path','secret/source.json'):
                self.assertNotIn(forbidden,text)
            self.assertEqual(len(synthetic['events']),25)

    def test_strict_keys_no_client_sources_or_recording_time(self):
        with tempfile.TemporaryDirectory() as root:
            service,_,_=fixtures.ServiceTests().fixture(root)
            with patch.object(routes,'SERVICE',service),self.client() as client:
                for endpoint,body in [('preview',{'research_id':RID,'cash':'1'}),('accept',{'research_id':RID,'proposal_id':'x','operation_id':'o','price':'1'}),('event',{'research_id':RID,'event':{'kind':'EXPIRE','event_id':'x','expected_revision':'x','order_id':'x','recorded_at':NOW.isoformat()}})]:
                    self.assertEqual(client.post(BASE+'/'+endpoint,json=body).status_code,400)
                for query in ('research_id='+RID+'&research_id='+RID,'research_id='+RID+'&path=bad'):
                    self.assertEqual(client.get(BASE+'/account?'+query).status_code,400)
                self.assertFalse((Path(root)/'store').exists())
    def test_corrupt_persisted_state_rejects_without_exposing_evidence(self):
        import sqlite3,json
        with tempfile.TemporaryDirectory() as root:
            service,_,_=fixtures.ServiceTests().fixture(root)
            with patch.object(routes,'SERVICE',service),self.client() as client:
                p=client.post(BASE+'/preview',json={'research_id':RID}).json()['proposal']
                client.post(BASE+'/accept',json=dict(research_id=RID,proposal_id=p['proposal_id'],operation_id='op'))
                with closing(sqlite3.connect(service.store.path)) as db:
                    value=json.loads(db.execute('select state_json from intraday_accounts').fetchone()[0]);value['cash']='1'
                    db.execute('update intraday_accounts set state_json=?',(json.dumps(value),));db.commit()
                response=client.get(BASE+'/account',params={'research_id':RID})
                self.assertEqual(response.status_code,400);self.assertNotIn('account',response.json())

    def test_invalid_fill_arithmetic_is_input_error_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as root:
            service,_,clock=fixtures.ServiceTests().fixture(root)
            with patch.object(routes,'SERVICE',service),self.client() as client:
                proposal=client.post(BASE+'/preview',json={'research_id':RID}).json()['proposal']
                state=client.post(BASE+'/accept',json=dict(research_id=RID,proposal_id=proposal['proposal_id'],operation_id='invalid-fill')).json()['account']
                clock[0]+=timedelta(minutes=5)
                event=dict(event_id='bad-fill',kind='FILL',expected_revision=state['revision'],order_id=state['order']['order_id'],
                           quantity=1,price='1400',fees='0',executed_at=(NOW+timedelta(minutes=4)).isoformat())
                for change in ({'price':'1/0'},{'fees':'1/0'},{'quantity':True},{'fees':'-1'}):
                    response=client.post(BASE+'/event',json=dict(research_id=RID,event=dict(event,**change)))
                    self.assertEqual(response.status_code,400,response.text)
                    self.assertEqual(client.get(BASE+'/account',params={'research_id':RID}).json()['account'],state)

if __name__=='__main__':unittest.main()
