import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.current_research_intraday_paper as routes
import test_current_research_intraday_continuation_service as fixtures

class ContinuationRouteTests(unittest.TestCase):
    def test_temp_actual_service_compact_cumulative_and_strict_keys(self):
        with tempfile.TemporaryDirectory() as root:
            helper=fixtures.ContinuationServiceTests();service,reference,clock,state=helper.fixture(root)
            state=helper.close(service,state)
            app=FastAPI();app.include_router(routes.router)
            base='/api/research_paper/intraday_paper/continuation'
            with patch.object(routes,'SERVICE',service),TestClient(app) as client:
                response=client.post(base+'/preview',json={'research_id':fixtures.RID})
                self.assertEqual(response.status_code,200,response.text)
                proposal=response.json()['proposal'];self.assertEqual(proposal['held_quantity'],2)
                self.assertEqual(proposal['available_cash'],'17200');self.assertEqual(proposal['proposal_kind'],'CONTINUATION')
                with patch.object(service,'continuation_preview',return_value=dict(status='PENDING_UNIT_REVIEW',state=state,proposal=None,review_reference=dict(event_sha256='a'*64,checked_at='2026-10-15T12:00:30-04:00',accept_before='2026-10-15T12:01:00-04:00',internal_path='hidden'))):
                    pending=client.post(base+'/preview',json={'research_id':fixtures.RID}).json()
                    self.assertEqual(pending['status'],'PENDING_UNIT_REVIEW');self.assertIsNone(pending['proposal'])
                    self.assertEqual(set(pending['review_reference']),{'event_sha256','checked_at','accept_before'})
                    self.assertEqual(pending['account']['cash'],'17200')

                body=dict(research_id=fixtures.RID,proposal_id=proposal['proposal_id'],operation_id='continuation-api',expected_revision=state['revision'])
                self.assertEqual(client.post(base+'/accept',json=dict(body,price='1')).status_code,400)
                response=client.post(base+'/accept',json=body);self.assertEqual(response.status_code,200,response.text)
                account=response.json()['account'];self.assertEqual(account['shares'],{'sndk':2});self.assertEqual(account['filled_quantity'],0)
                self.assertNotEqual(account['original_acceptance_id'],account['current_order_acceptance_id'])
                self.assertEqual(account['order']['order_id'],account['current_order_acceptance_id']+':BUY')
                self.assertEqual(account['initial_cash'],'20000');self.assertEqual(account['recorded_buy_notional'],'2800')
                self.assertEqual(client.post(base+'/accept',json=body).json()['account'],account)
                self.assertEqual(client.post(base+'/preview',json={'research_id':fixtures.RID,'cash':'20000'}).status_code,400)
                self.assertEqual(client.post(base+'/preview',json={'research_id':fixtures.RID}).status_code,400)

if __name__=='__main__':unittest.main()
