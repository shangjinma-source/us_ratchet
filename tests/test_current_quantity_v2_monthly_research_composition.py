"""Actual temporary raw compiler -> HTTP research -> monthly preview/accept."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_factory import attach_monthly_services
from data.current_quantity_v2_monthly_research_service import QuantityV2MonthlyResearchService
from api.current_quantity_v2_monthly_research import create_router as research_router
from api.current_quantity_v2_paper import create_router as paper_router, PREFIX
from test_current_quantity_v2_monthly_training import fixture as training_fixture
from test_current_quantity_v2_monthly_sources import fixture as source_fixture


class ResearchCompositionTests(unittest.TestCase):
    def test_raw_training_http_registration_preview_accept_and_retry(self):
        with TemporaryDirectory() as folder:
            source,paper,state,_,clock,calls,base=source_fixture(folder)
            paper.clock=lambda:clock[0]
            registry,_,package,_=training_fixture(folder)
            registry.clock=lambda:clock[0]
            files=package['files']
            files.update({p:b for p,b in base['files'].items() if p not in files})
            identities=json.loads(base['files'][base['documents']['identities']])
            files['identities.json']=canonical(identities)
            manifest=json.loads(files['manifest.json'])
            manifest['candidates'][0]['issuer_id']=identities['securities']['B']['issuer_id']
            # Synthetic held mark provides enough equity to select whole shares.
            raw=json.loads(files['A.held'])
            for field in ('open','high','low','close'):
                raw['chart']['result'][0]['indicators']['quote'][0][field]=[500]
            files['A.held']=canonical(raw)
            review=json.loads(files['account_review.json'])
            review.update(account_id=state['ledger']['account_id'],state_revision=state['ledger']['revision'],reviewed_at=clock[0].isoformat())
            files['account_review.json']=canonical(review)
            manifest['source_hashes']={p:sha256(b).hexdigest() for p,b in files.items() if p!='manifest.json'}
            files['manifest.json']=canonical(manifest)
            package['source_hashes']={p:sha256(b).hexdigest() for p,b in files.items()}
            supplied=dict(source_package=package,manifest_path='manifest.json',calendar_path='calendar.json',account_review_path='account_review.json',identities_path='identities.json',held_bar_sources={'A':'A.held'})
            service=QuantityV2MonthlyResearchService(store=paper.store,registry=registry,selection_root=Path(folder)/'selection',training_reader=lambda _:deepcopy(supplied),clock=lambda:clock[0])
            current_id=[None]
            def unit_review(snapshot):
                reviewed=source.review_reader(snapshot)
                path=reviewed['documents']['unit_continuity']
                units=json.loads(reviewed['files'][path])
                for sid,unit in units.items():
                    unit['capital_decision_id']=current_id[0]
                    unit['valuation_source_references']=['A.held' if sid=='A' else 'B.daily']
                reviewed['files'][path]=canonical(units)
                reviewed['source_hashes'][path]=sha256(reviewed['files'][path]).hexdigest()
                return reviewed
            attach_monthly_services(paper,storage_root=Path(folder)/'capture',decision_reader=service.decision_reader,review_reader=unit_review,fetch=source.fetch)
            app=FastAPI();app.include_router(research_router(service=service));app.include_router(paper_router(service=paper))
            aid=state['ledger']['account_id'];revision=state['ledger']['revision']
            with TestClient(app) as client:
                response=client.post(PREFIX+'/monthly/research/generate',json=dict(account_id=aid,expected_revision=revision,retry_failed=False))
                self.assertEqual(response.status_code,200,response.text)
                result=response.json();self.assertEqual(result['status'],'READY')
                self.assertEqual(result['portfolio']['as_of'],'2026-10-30')
                self.assertEqual([row['ticker'] for row in result['portfolio']['stocks']],['BBB'])
                self.assertIsNone(result['portfolio']['executable_buy_quantities'])
                self.assertNotIn('source_hashes',json.dumps(result))
                current_id[0]=result['decision_id'];self.assertEqual(calls,[])
                self.assertEqual(paper.store.read(aid),state)
                service.training_reader=lambda _:self.fail('GET must not read training')
                with patch('subprocess.run',side_effect=AssertionError('GET must not run worker')):
                    recovered=client.get(PREFIX+'/monthly/research',params=dict(account_id=aid))
                    self.assertEqual(recovered.status_code,200,recovered.text)
                    self.assertEqual(recovered.json()['registration_id'],result['registration_id'])
                    response=client.get(PREFIX+'/monthly/research',params=dict(account_id=aid,registration_id=result['registration_id']))
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['decision_id'],current_id[0])
                response=client.post(PREFIX+'/monthly/preview',json=dict(account_id=aid,expected_revision=revision,decision_id=current_id[0]))
                self.assertEqual(response.status_code,200,response.text)
                proposal=response.json();self.assertEqual(calls,['AAA','BBB'])
                clock[0]+=timedelta(seconds=1)
                request=dict(account_id=aid,expected_revision=revision,proposal_id=proposal['proposal_id'],operation_id='research-composition-accept')
                response=client.post(PREFIX+'/monthly/accept',json=request)
                self.assertEqual(response.status_code,200,response.text)
                accepted=paper.store.read(aid)
                self.assertEqual(accepted['genesis'],state['genesis'])
                for key in ('cash','shares','events','recorded_fees'):
                    self.assertEqual(accepted['ledger'][key],state['ledger'][key])
                with self.assertRaises(ValueError):service.decision_reader(accepted)
                clock[0]+=timedelta(days=90)
                response=client.post(PREFIX+'/monthly/accept',json=request)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(paper.store.read(aid),accepted)
                self.assertEqual(calls,['AAA','BBB'])


if __name__=='__main__':unittest.main()
