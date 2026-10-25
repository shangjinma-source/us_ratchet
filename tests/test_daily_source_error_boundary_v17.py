import unittest
from xml.etree.ElementTree import ParseError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_daily_preview_v4 import create_router
class SourceErrorTests(unittest.TestCase):
 def test_xml_unavailable_is_typed_wait_and_never_returns_old_orders(self):
  class Service:
   def preview(self,**kwargs):raise ParseError('upstream returned HTML')
  app=FastAPI();app.include_router(create_router(service=Service()))
  response=TestClient(app).post('/api/strategy-daily-v3/preview',json=dict(expected_revision='a'*64,target_id='b'*64))
  self.assertEqual(response.status_code,409)
  self.assertEqual(response.json()['reason'],'OFFICIAL_ACTION_SOURCE_UNAVAILABLE')
  self.assertEqual(response.json()['new_orders'],[])
  self.assertEqual(response.json()['reference_quotes'],{})
 def test_success_payload_is_unchanged(self):
  payload=dict(status='READY',new_orders=[],reference_quotes={})
  class Service:
   def preview(self,**kwargs):return payload
  app=FastAPI();app.include_router(create_router(service=Service()))
  response=TestClient(app).post('/api/strategy-daily-v3/preview',json=dict(expected_revision='a'*64,target_id='b'*64))
  self.assertEqual(response.status_code,200);self.assertEqual(response.json(),payload)

 def test_same_route_recovers_after_actual_xml_parse_failure(self):
  from xml.etree.ElementTree import fromstring
  calls=[]
  binding=dict(expected_revision='a'*64,target_id='b'*64)
  payload=dict(status='HOLD',account_revision='a'*64,target_id='b'*64,
               new_orders=[],reference_quotes={})
  class Service:
   def preview(self,**kwargs):
    calls.append(kwargs)
    # Match the failure class in the saved server traceback, then recover
    # on the next request. This tests routing, not market-source admission.
    fromstring(b'<rss><channel></rss>' if len(calls)==1 else b'<rss/>')
    return payload
  app=FastAPI();app.include_router(create_router(service=Service()))
  with TestClient(app) as client:
   first=client.post('/api/strategy-daily-v3/preview',json=binding)
   self.assertEqual(first.status_code,409)
   self.assertEqual(first.json()['reason'],'OFFICIAL_ACTION_SOURCE_UNAVAILABLE')
   self.assertEqual(first.json()['new_orders'],[])
   second=client.post('/api/strategy-daily-v3/preview',json=binding)
   self.assertEqual(second.status_code,200)
   self.assertEqual(second.json(),payload)
  self.assertEqual(calls,[binding,binding])
