import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_account import create_router as account_router
from api.strategy_frontier_daily_preview_v1 import create_router as advice_router
from core.strategy_account_store import StrategyAccountStore
from docs.candidates.frozen_target_provider_20261106 import digest
from docs.candidates.frozen_target_builder_20261106 import FrozenTargetBuilder


class CashRefreshTests(unittest.TestCase):
    def test_http_cash_changes_rebuild_same_signal(self):
        with TemporaryDirectory() as directory:
            now = datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            path = Path(directory)/'account.sqlite3'
            store = StrategyAccountStore(path,clock=lambda:now)
            policy = dict(strategy_epoch='synthetic-fixed',weights={'NEW':'1'},
                signal_at='2026-11-05T21:00:00Z',valid_from='2026-11-06T14:30:00Z',
                valid_until='2026-11-06T14:32:00Z')
            quotes = dict(marks={'NEW':dict(security_id='NEW',currency='USD',price_basis='current',price='100',observed_at=now.isoformat())},
                limits={'NEW':dict(security_id='NEW',price_basis='current',buy='100',sell='100',observed_at=now.isoformat())})
            builder = FrozenTargetBuilder(directory=Path(directory)/'targets',policy=policy,
                contract_sha256=digest(policy),expected_epoch='synthetic-fixed',account_id='test',
                store=store,quote_provider=lambda account:quotes,clock=lambda:now)
            app=FastAPI()
            app.include_router(account_router(database_path=path,account_id='test',resolver=lambda t:None,clock=lambda:now))
            app.include_router(advice_router(service=builder))
            with TestClient(app) as client:
                state=client.post('/api/strategy-account/initialize',json={'event_id':'init'}).json()['account']
                prior=None
                for index,(cash,quantity) in enumerate([('1000',10),('3000',30),('500',5)]):
                    response=client.post('/api/strategy-account/events',json=dict(expected_revision=state['revision'],
                        event=dict(event_id=f'cash-{index}',kind='CASH_CONFIRM',amount=cash,cash_basis='TOTAL_UNINVESTED')))
                    self.assertEqual(response.status_code,200,response.text)
                    state=response.json()['account']
                    if index == 0:
                        with patch('docs.candidates.frozen_target_builder_20261106.FrozenTargetProvider.preview',
                                   side_effect=ValueError('TEMPORARY_VALIDATION_FAILURE')):
                            with self.assertRaisesRegex(ValueError,'TEMPORARY_VALIDATION_FAILURE'):
                                builder.rebuild()
                        self.assertIsNone(builder.current)
                        self.assertEqual(builder.versions,[])
                        pending=list((Path(directory)/'targets').glob('*.json'))
                        self.assertEqual(len(pending),1)
                        original=pending[0].read_bytes()
                        pending[0].write_bytes(original+b' ')
                        with self.assertRaisesRegex(ValueError,'TARGET_FILE_CONFLICT'):
                            builder.rebuild()
                        self.assertIsNone(builder.current)
                        self.assertEqual(builder.versions,[])
                        self.assertEqual(pending[0].read_bytes(),original+b' ')
                        pending[0].write_bytes(original)
                    version=builder.rebuild()  # trusted server operation, no client weights
                    self.assertEqual(builder.rebuild(),version)
                    self.assertEqual(len(builder.versions),index+1)
                    response=client.post('/api/strategy-daily-v3/preview',json=dict(expected_revision=state['revision'],
                        target_id=version['target_id'],expected_proposal_id=version['proposal_id']))
                    self.assertEqual(response.status_code,200,response.text)
                    result=response.json()
                    self.assertEqual(result['difference']['new_orders'][0]['quantity'],quantity)
                    self.assertFalse(result['executable'])
                    saved=json.loads(Path(version['path']).read_text())['payload']
                    self.assertEqual(saved['previous_target_id'],prior)
                    self.assertEqual(saved['strategy_contract_sha256'],digest(policy))
                    self.assertEqual(saved['strategy_epoch'],'synthetic-fixed')
                    prior=version['target_id']
                self.assertEqual(len({v['target_id'] for v in builder.versions}),3)
                self.assertTrue(all(Path(v['path']).is_file() for v in builder.versions))
                self.assertEqual(store.read()['available_cash'],'500')
                self.assertFalse(store.read()['orders'])


if __name__ == '__main__':
    unittest.main()
