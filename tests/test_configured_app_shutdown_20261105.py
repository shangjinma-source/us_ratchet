"""Actual FastAPI lifespan and middleware wiring, without market fixtures."""
from contextlib import asynccontextmanager
from tempfile import TemporaryDirectory
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from data.news_investment_service_v1 import NewsInvestmentService
from docs.candidates.news_review_worker_owner_20261105 import ReviewWorkerOwner
from docs.candidates.runtime_request_drain_20261105 import RequestDrain
from docs.candidates.runtime_service_quiesce_20261105 import ServiceQuiescer
from docs.candidates.split_configured_runtime_routes_20261105 import build_configured_app


class Tests(unittest.TestCase):
    def test_shutdown_runs_with_included_router_lifespan(self):
        with TemporaryDirectory() as folder:
            events = []
            @asynccontextmanager
            async def lifespan(app):
                events.append('start')
                yield
                events.append('stop')
            router = APIRouter(lifespan=lifespan)
            @router.get('/probe')
            def probe():
                return {'ok': True}
            service = NewsInvestmentService(cache=Path(folder), context=lambda: None, preview=lambda: None)
            reviews = ReviewWorkerOwner(service)
            gate = RequestDrain()
            quiescer = ServiceQuiescer(gate=gate, worker_owner=SimpleNamespace(worker=None, stop_event=Event()), review_owner=reviews)
            prepared = dict(router=router, request_drain=gate, quiescer=quiescer)
            with patch('docs.candidates.split_configured_runtime_routes_20261105.build_configured_routes', return_value=prepared):
                app = build_configured_app()['app']
            with TestClient(app) as client:
                self.assertEqual(client.get('/probe').status_code, 200)
            self.assertEqual(events, ['start', 'stop'])
            self.assertTrue(reviews.closed.is_set())
            self.assertFalse(gate.enter())


if __name__ == '__main__':
    unittest.main()
