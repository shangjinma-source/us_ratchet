"""Isolated candidate diagnostics; no production service or network."""
import importlib.util
import os
from pathlib import Path
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
PATH=Path(os.environ.get('FRONTIER_PREVIEW_ROUTE_SOURCE',str(ROOT/'api/strategy_frontier_daily_preview_v1.py')))
spec=importlib.util.spec_from_file_location('candidate_route',PATH);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class MappingTests(unittest.TestCase):
 def test_allowlist_and_fail_closed(self):
  errors=[(ValueError('SUPPLEMENT_REVIEW_FAILED:WAIT_KNOWN_ACTION_REVIEW'),'WAIT_KNOWN_ACTION_REVIEW'),(ValueError('SUPPLEMENT_REVIEW_FAILED:WAIT_KNOWN_ACTION_REVIEW:/secret'),'DAILY_PREVIEW_UNAVAILABLE'),(ValueError('SUPPLEMENT_REVIEW_FAILED:WAIT_OTHER'),'DAILY_PREVIEW_UNAVAILABLE'),(ValueError('prefix SUPPLEMENT_REVIEW_FAILED:WAIT_KNOWN_ACTION_REVIEW'),'DAILY_PREVIEW_UNAVAILABLE'),(KeyError('SUPPLEMENT_REVIEW_FAILED:WAIT_KNOWN_ACTION_REVIEW'),'DAILY_PREVIEW_UNAVAILABLE'),(OSError('C:/private/account.json'),'DAILY_PREVIEW_UNAVAILABLE'),(ValueError('STALE_SNAPSHOT'),'STALE_SNAPSHOT')]
  for error,reason in errors:
   with self.subTest(error=repr(error)):
    class Service:
     def preview(self,**unused):raise error
    app=FastAPI();app.include_router(module.create_router(service=Service()))
    with TestClient(app) as client:
     response=client.post('/api/strategy-daily-v3/preview',json={'expected_revision':'a'*64,'target_id':'b'*64,'expected_proposal_id':'c'*64});body=response.json()
    self.assertEqual(response.status_code,409);self.assertEqual(body['reason'],reason);self.assertEqual(body['status'],'WAIT');self.assertEqual(body['new_orders'],[]);self.assertEqual(body['reference_quotes'],{});self.assertFalse(body['orders_created']);self.assertEqual(response.headers['cache-control'],'no-store')
if __name__=='__main__':unittest.main()
