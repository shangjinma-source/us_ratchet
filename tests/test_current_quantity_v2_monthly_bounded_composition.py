"""Monthly bounded public review through actual raw provider and HTTP acceptance."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_paper import create_router,PREFIX
from data.current_quantity_v2_monthly_factory import attach_monthly_services
from data.current_quantity_v2_monthly_origins import MonthlyOriginReader
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_retarget import active_proposal
from test_current_quantity_v2_monthly_research_service import fixture
from test_current_quantity_v2_bounded_unit_review import feed


class MonthlyBoundedCompositionTests(unittest.TestCase):
    def test_missing_origin_and_review_errors_are_explicit(self):
        class MissingSource:
            reason='MONTHLY_ORIGIN_BYTES_MISSING'
            def monthly_preview(self,**kwargs):raise ValueError(self.reason)
        service=MissingSource();app=FastAPI();app.include_router(create_router(service=service))
        with TestClient(app) as client:
            for reason in ('MONTHLY_ORIGIN_ARCHIVE_REQUIRED','MONTHLY_ORIGIN_BYTES_MISSING','MONTHLY_ORIGIN_BYTES_CHANGED','MONTHLY_BOUNDED_REVIEW_UNAVAILABLE','BOUNDED_UNIT_CHANGE_CANDIDATE'):
                service.reason=reason
                response=client.post(PREFIX+'/monthly/preview',json=dict(account_id='a',decision_id='a'*64,expected_revision='r'))
                self.assertEqual(response.status_code,503)
                self.assertEqual(response.json()['error_code'],reason)
                self.assertEqual(response.json()['orders'],[])

    def test_http_bounded_review_once_accept_and_source_free_retry(self):
        from data.current_quantity_v2_monthly_bounded_review import MonthlyBoundedUnitReview
        with TemporaryDirectory() as folder:
            research,state,supplied,old,paper,clock=fixture(folder)
            aid=state['ledger']['account_id'];revision=state['ledger']['revision']
            # Training does not contain old intraday bytes. Recover only the
            # hashes already recorded in the accepted origin, from an archive.
            archive=Path(folder)/'prior-blobs';archive.mkdir()
            package=supplied['source_package'];files=package['files']
            prior=active_proposal(state['ledger'])
            origin_pins=prior['causal_inputs']['execution_references']['A']['source_hashes']
            manifest=json.loads(files['manifest.json'])
            for path,digest in origin_pins.items():
                (archive/digest).write_bytes(files.pop(path))
                manifest['source_hashes'].pop(path)
            files['manifest.json']=canonical(manifest)
            package['source_hashes']={p:sha256(raw).hexdigest() for p,raw in files.items()}
            selected=research.generate(account_id=aid,expected_revision=revision)
            requests=[]
            def account_review(snapshot):
                package=old.review_reader(snapshot)
                path=package['documents']['account_review']
                return dict(files=deepcopy(package['files']),source_hashes=deepcopy(package['source_hashes']),account_review_path=path)
            reader=MonthlyBoundedUnitReview(account_review_reader=account_review,
                origin_reader=MonthlyOriginReader(monthly_blob_root=archive),
                fetch=lambda:(requests.append(1) or {'status':200,'body':feed()}),clock=lambda:clock[0])
            paper.clock=lambda:clock[0]
            parts=attach_monthly_services(paper,storage_root=Path(folder)/'bounded-captures',
                decision_reader=research.decision_reader,review_reader=reader,fetch=old.fetch)
            self.assertEqual(requests,[])
            app=FastAPI();app.include_router(create_router(service=paper))
            with TestClient(app) as client:
                response=client.post(PREFIX+'/monthly/preview',json=dict(account_id=aid,decision_id=selected['decision_id'],expected_revision=revision))
                self.assertEqual(response.status_code,200,response.text)
                proposal=response.json()
                self.assertFalse(proposal['unit_review']['coverage_complete'])
                self.assertFalse(proposal['unit_review']['source_authenticated'])
                self.assertNotIn('bounded_evidence',str(proposal))
                self.assertEqual(requests,[1])
                self.assertEqual(paper.store.read(aid),state)
                request=dict(account_id=aid,proposal_id=proposal['proposal_id'],operation_id='bounded-monthly',expected_revision=revision)
                clock[0]+=timedelta(seconds=1)
                response=client.post(PREFIX+'/monthly/accept',json=request)
                self.assertEqual(response.status_code,200,response.text)
                accepted=paper.store.read(aid)
                self.assertEqual(accepted['genesis'],state['genesis'])
                for key in ('cash','shares','events','recorded_fees'):
                    self.assertEqual(accepted['ledger'][key],state['ledger'][key])
                self.assertEqual(requests,[1])
                reader.fetch=lambda:self.fail('accepted retry must not fetch feed')
                parts['sources'].fetch=lambda _:self.fail('accepted retry must not fetch quote')
                parts['bridge']._proposals.clear()
                clock[0]+=timedelta(days=90)
                response=client.post(PREFIX+'/monthly/accept',json=request)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(paper.store.read(aid),accepted)
                self.assertEqual(requests,[1])


if __name__=='__main__':unittest.main()
