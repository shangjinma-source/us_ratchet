import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_difference import create_router
from data.current_cash_portfolio_research import ResearchExpiredError
from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_current_cash_service import CurrentQuantityV2CurrentCashService
from data.current_quantity_v2_preview_observations import ObservedCurrentCashPreview


class DifferenceExpiryTests(unittest.TestCase):
    def request(self,error):
        class Service:
            def preview(self,decision_id):
                raise error
        app=FastAPI(); app.include_router(create_router(service=Service()))
        with TestClient(app) as client:
            return client.post('/api/current_portfolio_research/difference',json={'decision_id':'a'*64})

    def test_expired_snapshot_is_specific_and_does_not_leak_details(self):
        response=self.request(ResearchExpiredError('private/path and internal snapshot details'))
        self.assertEqual(response.status_code,410)
        payload=response.json()
        self.assertEqual(payload['reason'],'RESEARCH_SNAPSHOT_EXPIRED')
        self.assertEqual(payload['orders'],[])
        self.assertIsNone(payload['proposal_id'])
        self.assertNotIn('private',response.text)

    def test_other_value_error_stays_generic_unavailable(self):
        response=self.request(ValueError('private/path'))
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['reason'],'SOURCE_UNAVAILABLE')

    def test_actual_empty_cache_source_service_observer_router(self):
        with TemporaryDirectory() as temp:
            root=Path(temp); calls=[]
            def forbidden(*args,**kwargs):
                calls.append('unexpected'); raise AssertionError('no source loading, fetch or search')
            clock=lambda:datetime(2026,10,15,16,tzinfo=timezone.utc)
            snapshots=CurrentQuantityPortfolioResearchV2(root=root,source_loader=forbidden)
            sources=CurrentQuantityV2CurrentCashSources(root=root,snapshot_service=snapshots,
                server_account_id='synthetic',fetch=forbidden,clock=clock)
            service=CurrentQuantityV2CurrentCashService(resolver=sources.resolve,
                account_reader=sources.account_reader,clock=clock,prepare=sources.capture)
            observed=ObservedCurrentCashPreview(service=service,directory=root/'observations',clock=clock)
            app=FastAPI(); app.include_router(create_router(service=observed))
            with TestClient(app) as client:
                response=client.post('/api/current_portfolio_research/difference',json={'decision_id':'a'*64})
            self.assertEqual(response.status_code,410)
            self.assertEqual(response.json()['reason'],'RESEARCH_SNAPSHOT_EXPIRED')
            self.assertEqual(response.json()['orders'],[])
            self.assertIsNone(response.json()['proposal_id'])
            self.assertEqual(observed.history()['observations'][0]['reason'],'RESEARCH_SNAPSHOT_EXPIRED')
            self.assertEqual(calls,[])
            self.assertEqual(snapshots.snapshots,{})
            service.prepare=None
            service.resolver=lambda did:snapshots.decision(did[:24])
            with TestClient(app) as client:
                self.assertEqual(client.post('/api/current_portfolio_research/difference',json={'decision_id':'a'*64}).status_code,410)

    def test_snapshot_expires_during_observation_write(self):
        import test_current_quantity_v2_current_cash_plan as base
        from test_current_quantity_v2_current_cash_service import fixture
        base.CurrentCashTests.setUpClass()
        try:
            with TemporaryDirectory() as temp:
                source,_,supplied,_,clock=fixture(temp,base.CurrentCashTests.args)
                empty=CurrentQuantityPortfolioResearchV2(root=temp)
                observed=ObservedCurrentCashPreview(service=source,directory=Path(temp)/'journal',clock=lambda:clock[0])
                record=observed.journal.record
                def invalidate_after_record(*args):
                    receipt=record(*args)
                    source.resolver=lambda did:empty.decision(did[:24])
                    return receipt
                observed.journal.record=invalidate_after_record
                app=FastAPI();app.include_router(create_router(service=observed))
                with TestClient(app) as client:
                    response=client.post('/api/current_portfolio_research/difference',json={'decision_id':supplied['capital_decision']['decision_id']})
                self.assertEqual(response.status_code,410)
                self.assertEqual(response.json()['reason'],'RESEARCH_SNAPSHOT_EXPIRED')
                self.assertEqual(response.json()['orders'],[])
                # History is the generated preview before invalidation, never a delivery claim.
                self.assertTrue(observed.history()['observations'][0]['generated_not_confirmed_displayed'])
        finally:
            base.CurrentCashTests.tearDownClass()


if __name__=='__main__': unittest.main()
