from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.news_investment_review_v1 import create_router

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);(root/'web').mkdir();(root/'web/news_investment_review.js').write_text('// static fixture')
        self.service=Mock();self.service.start.return_value=(202,{'status':'RUNNING'});self.service.status.return_value={'status':'RUNNING'}
        app=FastAPI();app.include_router(create_router(service=self.service,root=root))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.url='/api/news/investment-review'
        self.body={k:'a'*64 for k in ('expected_revision','target_id','expected_proposal_id')}

    def test_same_origin_and_three_ids(self):
        self.assertEqual(self.client.post(self.url,json=self.body,headers={'origin':'http://testserver'}).status_code,202)
        self.service.start.assert_called_once_with(self.body)
        self.assertEqual(self.client.post(self.url,json=self.body,headers={'origin':'https://other.test'}).status_code,403)
        self.assertEqual(self.service.start.call_count,1)

    def test_size_duplicates_query_and_binding(self):
        for url,content in [(self.url,' '*1025),(self.url,'{"expected_revision":"a","expected_revision":"b"}'),
                            (self.url+'?extra=1','{}'),(self.url,'{}'),(self.url,'[]')]:
            self.assertEqual(self.client.post(url,content=content,headers={'content-type':'application/json'}).status_code,409)
        for key in self.body:
            body=dict(self.body);body[key]='wrong'
            self.assertEqual(self.client.post(self.url,json=body).status_code,409)
        body=dict(self.body,action='EXIT')
        self.assertEqual(self.client.post(self.url,json=body).status_code,409)
        self.service.start.assert_not_called()

    def test_get_job_does_not_start_model_and_queries_strict(self):
        self.assertEqual(self.client.get(self.url+'/job',params={'job_id':'a'*32}).status_code,200)
        self.service.status.assert_called_once_with('a'*32)
        for query in ('','?job_id=bad','?job_id='+('a'*32)+'&job_id='+('a'*32),'?job_id='+('a'*32)+'&extra=1'):
            self.assertEqual(self.client.get(self.url+'/job'+query).status_code,400)
        self.service.start.assert_not_called();self.service.model.assert_not_called()

    def test_static_route_read_only(self):
        response=self.client.get('/static/news_investment_review.js')
        self.assertEqual(response.status_code,200);self.assertIn('// static fixture',response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.service.start.assert_not_called();self.service.status.assert_not_called()

if __name__=='__main__':unittest.main()
