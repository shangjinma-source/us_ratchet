from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_portfolio_research_v2 import fixture
from test_current_quantity_v2_intraday_reference import raw,NOW
from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2
from data.current_quantity_v2_cash_package import assemble_cash_package
from data.current_quantity_v2_difference_service import CurrentQuantityV2DifferenceService
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from api.current_quantity_v2_difference import create_router as difference_router
from api.current_quantity_v2_paper import create_router as paper_router,PREFIX


class PackageTests(unittest.TestCase):
    def test_real_tiny_single_search_assembly_delayed_http_and_rejections(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);_,_,descriptor=fixture(root)
            service=CurrentQuantityPortfolioResearchV2(root=root,source_loader=lambda:deepcopy(descriptor))
            with patch('data.current_quantity_portfolio_research_v2.subprocess.run',wraps=subprocess.run) as worker:
                snapshot=service.calculate('100');decision=service.decision(snapshot['research_id']);original=deepcopy(decision)
                sources={name:(root/name).read_bytes() for name in decision['binding']['source_hashes']}
                files={'execution/review.json':b'{"synthetic_explicit_review":true}'}
                pins={name:sha256(value).hexdigest() for name,value in files.items()};receipts={};units={}
                securities=deepcopy(decision['binding']['search_arguments']['metadata'])
                for sid,security in securities.items():
                    name='execution/'+sid+'.raw';files[name]=raw(security['ticker'],9);pins[name]=sha256(files[name]).hexdigest()
                    path='execution/'+sid+'.receipt'
                    files[path]=json.dumps(dict(security_id=sid,ticker=security['ticker'],raw_path=name,raw_sha256=pins[name],captured_at=NOW.isoformat())).encode()
                    pins[path]=sha256(files[path]).hexdigest();receipts[sid]=path
                    units[sid]=dict(security_id=sid,ticker=security['ticker'],capital_decision_id=decision['decision_id'],
                        status='NO_UNPROCESSED_ACTIONS',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                        reference_source_hashes={name:pins[name],path:pins[path]},source_references=['execution/review.json'],
                        covered_from_date='2026-10-13',covered_through=NOW.isoformat(),reviewed_at=(NOW+timedelta(seconds=1)).isoformat(),
                        valuation_source_references=decision['binding']['valuation_quotes'][sid]['source_references'])
                execution=dict(files=files,source_hashes=pins,securities=securities,unit_continuity=units,quote_receipts=receipts,
                               identity_source_references=['execution/review.json'])
                arguments=dict(account_id='stable-strategy-pool',capital_decision=decision,original_source_files=sources,
                    genesis_at=(NOW-timedelta(hours=1)).isoformat(),active_date='2026-10-14',execution_package=execution)
                assembled=assemble_cash_package(**arguments);self.assertEqual(decision,original)
                account=assembled['account_document']['state'];clock=[NOW+timedelta(seconds=2)]
                difference=CurrentQuantityV2DifferenceService(resolver=lambda _:deepcopy(assembled['package']),
                    account_reader=lambda _:deepcopy(account),clock=lambda:clock[0])
                paper=QuantityV2PaperService(store=QuantityV2PaperStore(root/'test-paper.sqlite3'),
                    initial_resolver=difference.initial_resolver,clock=lambda:clock[0])
                app=FastAPI();app.include_router(difference_router(service=difference));app.include_router(paper_router(service=paper))
                with TestClient(app) as client:
                    preview=client.post('/api/current_portfolio_research/difference',json={'decision_id':decision['decision_id']})
                    self.assertEqual(preview.status_code,200,preview.text)
                    clock[0]+=timedelta(seconds=1)
                    accepted=client.post(PREFIX+'/accept',json=dict(account_id=account['account_id'],proposal_id=preview.json()['proposal_id'],operation_id='one'))
                    self.assertEqual(accepted.status_code,200,accepted.text)
                    self.assertEqual(accepted.json()['cash'],'100');self.assertEqual(accepted.json()['reserved_cash'],'16')
                generated=assembled['package']['documents']['capital_decision']
                def collision(a):
                    a['execution_package']['files'][generated]=b'collision'
                    a['execution_package']['source_hashes'][generated]=sha256(b'collision').hexdigest()
                for mutate in (lambda a:a['original_source_files'].pop('input.json'),
                        lambda a:a['execution_package']['unit_continuity'].pop('A'),
                        lambda a:a['execution_package']['unit_continuity']['A'].update(status='UNKNOWN'),
                        lambda a:a['capital_decision']['binding']['shares'].update(OLD=1),collision,
                        lambda a:a['execution_package']['files'].update({'../outside':b'x'})):
                    bad=deepcopy(arguments);mutate(bad)
                    with self.assertRaises((ValueError,KeyError)):assemble_cash_package(**bad)
                self.assertEqual(worker.call_count,1);self.assertEqual(decision,original)


if __name__=='__main__':unittest.main()
