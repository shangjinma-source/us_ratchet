import unittest
import subprocess
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_research_v2 import create_router
from data.current_cash_portfolio_research import ResearchExpiredError


class Service:
    def __init__(self):self.calls=[];self.status='AVAILABLE'
    def calculate(self,cash):
        self.calls.append(('cash',cash))
        return dict(status=self.status,research_only=True,execution_blocked=True,cash=cash)
    def snapshot(self,rid):raise ResearchExpiredError('private internal detail')
    def bars(self,*args):
        self.calls.append(('bars',args))
        return dict(status='AVAILABLE',research_only=True,execution_blocked=True,research_id=args[0],bars=[])


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.service=Service();app=FastAPI();app.include_router(create_router(service=self.service))
        self.client=TestClient(app);self.base='/api/current_portfolio_research'

    def test_cash_and_no_hidden_holdings_or_method_override(self):
        response=self.client.post(self.base,json={'entered_cash':'20000'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(self.service.calls),1)
        for body in [{'entered_cash':20000,'holdings':{'A':1}}, {'entered_cash':True}, {'entered_cash':'-1'}]:
            self.assertEqual(self.client.post(self.base,json=body).status_code,400)
        self.assertEqual(len(self.service.calls),1)

    def test_duplicate_cash_and_query_rejected_before_service(self):
        self.assertEqual(self.client.post(self.base,content='{"entered_cash":1,"entered_cash":2}').status_code,400)
        self.assertEqual(self.client.post(self.base+'?method=other',json={'entered_cash':100}).status_code,400)
        self.assertEqual(self.service.calls,[])

    def test_unknown_snapshot_does_not_calculate(self):
        response=self.client.get(self.base+'/snapshot',params={'research_id':'a'*24})
        self.assertEqual(response.status_code,410)
        self.assertNotIn('private',response.text)
        self.assertEqual(self.service.calls,[])

    def test_bars_bind_exact_snapshot_and_arguments(self):
        query={'research_id':'a'*24,'ticker':'SNDK','interval':'day','bars':'90'}
        self.assertEqual(self.client.get(self.base+'/bars',params=query).status_code,200)
        self.assertEqual(self.service.calls,[('bars',('a'*24,'SNDK','day',90))])
        self.assertEqual(self.client.get(self.base+'/bars',params=dict(query,bars='261')).status_code,400)
        self.assertEqual(len(self.service.calls),1)

    def test_incomplete_not_successful_recommendation(self):
        self.service.status='INCOMPLETE'
        response=self.client.post(self.base,json={'entered_cash':'100'})
        self.assertEqual(response.status_code,503)
        self.assertTrue(response.json()['execution_blocked'])

    def test_invalid_service_result_and_worker_timeout_fail_closed(self):
        for result in (None, [], 'not a snapshot'):
            self.service.calculate=Mock(return_value=result)
            response=self.client.post(self.base,json={'entered_cash':'100'})
            self.assertEqual(response.status_code,503)
            self.assertNotIn('target_quantities',response.json())
        self.service.calculate=Mock(side_effect=subprocess.TimeoutExpired('synthetic-worker',300))
        response=self.client.post(self.base,json={'entered_cash':'100'})
        self.assertEqual(response.status_code,503)
        self.assertNotIn('target_quantities',response.json())

    def test_oversized_body_and_get_body_never_call_service(self):
        response=self.client.post(self.base,content=b' '*4097)
        self.assertEqual(response.status_code,400)
        response=self.client.request('GET',self.base+'/snapshot?research_id='+'a'*24,content=b'x')
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.service.calls,[])

    def test_withdrawn_source_is_explicit_but_other_details_stay_private(self):
        for reason, code in [('RESEARCH_SOURCE_WITHDRAWN', 'RESEARCH_SOURCE_WITHDRAWN'),
                             ('private/path:secret', 'SOURCE_OR_RESULT_NOT_AVAILABLE')]:
            self.service.calculate = Mock(side_effect=ValueError(reason))
            response = self.client.post(self.base, json={'entered_cash': '20000'})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['error_code'], code)
            self.assertTrue(response.json()['execution_blocked'])
            self.assertNotIn('secret', response.text)


if __name__=='__main__':unittest.main()
