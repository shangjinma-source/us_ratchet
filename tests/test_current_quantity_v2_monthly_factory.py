from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import timedelta
from unittest.mock import patch
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data.current_quantity_v2_monthly_factory import create_services,attach_monthly_services
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from api.current_quantity_v2_paper import create_router,PREFIX
from test_current_quantity_v2_monthly_sources import fixture

class MonthlyFactoryTests(unittest.TestCase):
    def test_constructor_disabled_zero_io(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'missing';store=QuantityV2PaperStore(path/'db')
            def forbidden(*args):self.fail('constructor called dependency')
            disabled=create_services(store=store,storage_root=path/'sources',fetch=forbidden,clock=forbidden)
            self.assertIsNone(disabled['sources']);self.assertFalse(path.exists())
            with self.assertRaisesRegex(ValueError,'MONTHLY_SOURCE_UNAVAILABLE'):
                disabled['paper'].monthly_preview(account_id='a',decision_id='b',expected_revision='r')
            create_services(store=store,storage_root=path/'sources',decision_reader=forbidden,review_reader=forbidden,fetch=forbidden,clock=forbidden)
            self.assertFalse(path.exists())
    def test_attach_preserves_current_cash_subclass_and_callbacks(self):
        from data.current_quantity_v2_current_cash_factory import _CurrentCashGuardedPaperService
        with TemporaryDirectory() as folder:
            seed,old,_,_,clock,_,_=fixture(folder)
            first=lambda *a:None;continuation=lambda *a:None;preview=lambda **a:None
            service=_CurrentCashGuardedPaperService(sources=seed,store=old.store,initial_resolver=first,
                continuation_resolver=continuation,continuation_previewer=preview,clock=lambda:clock[0])
            parts=attach_monthly_services(service,storage_root=Path(folder)/'attach',
                decision_reader=seed.decision_reader,review_reader=seed.review_reader,fetch=seed.fetch)
            self.assertIs(parts['paper'],service);self.assertIs(service.initial_resolver,first)
            self.assertIs(service.continuation_resolver,continuation);self.assertIs(service.continuation_previewer,preview)
            self.assertIs(service.sources,seed);self.assertIsInstance(service,_CurrentCashGuardedPaperService)
            self.assertFalse((Path(folder)/'attach').exists())

    def test_real_capture_http_accept_retry_and_wrong_id_no_fetch(self):
        with TemporaryDirectory() as folder:
            seed,old,state,did,clock,calls,_=fixture(folder)
            parts=create_services(store=old.store,storage_root=Path(folder)/'actual_capture',
                decision_reader=seed.decision_reader,review_reader=seed.review_reader,fetch=seed.fetch,clock=lambda:clock[0])
            paper=parts['paper'];app=FastAPI();app.include_router(create_router(service=paper))
            body=dict(account_id=state['ledger']['account_id'],decision_id=did,expected_revision=state['ledger']['revision'])
            with TestClient(app) as client:
                wrong=client.post(PREFIX+'/monthly/preview',json=dict(body,decision_id='f'*64))
                self.assertEqual(wrong.status_code,503);self.assertEqual(calls,[]);self.assertFalse(parts['sources'].storage_root.exists())
                response=client.post(PREFIX+'/monthly/preview',json=body)
                self.assertEqual(response.status_code,200,response.text);preview=response.json();self.assertEqual(calls,['AAA','BBB'])
                attempt=parts['sources']._attempt
                self.assertEqual(client.post(PREFIX+'/monthly/preview',json=dict(body,decision_id='f'*64)).status_code,503)
                self.assertEqual(parts['sources']._attempt,attempt);self.assertEqual(calls,['AAA','BBB'])
                clock[0]+=timedelta(seconds=1)
                request=dict(account_id=body['account_id'],proposal_id=preview['proposal_id'],operation_id='factory-accept',expected_revision=body['expected_revision'])
                response=client.post(PREFIX+'/monthly/accept',json=request);self.assertEqual(response.status_code,200,response.text)
                accepted=response.json();self.assertEqual(accepted['cash'],state['ledger']['cash']);self.assertEqual(accepted['shares'],state['ledger']['shares'])
                self.assertTrue(accepted['capabilities']['monthly']['configured'])
                parts['bridge']._proposals.clear();parts['sources'].fetch=lambda *_:self.fail('retry fetch')
                parts['sources'].decision_reader=lambda *_:self.fail('retry reader');clock[0]+=timedelta(days=90)
                replay=client.post(PREFIX+'/monthly/accept',json=request)
                self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json(),accepted);self.assertEqual(calls,['AAA','BBB'])

if __name__=='__main__':unittest.main()
