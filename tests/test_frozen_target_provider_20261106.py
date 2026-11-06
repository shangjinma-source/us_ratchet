import json
from hashlib import sha256
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_frontier_daily_preview_v1 import create_router
from core.strategy_account_store import StrategyAccountStore
from docs.candidates.frozen_target_provider_20261106 import FrozenTargetProvider, digest


class FrozenProviderTests(unittest.TestCase):
    def test_formal_http_digest_contract_expiry_and_valid_path(self):
        with TemporaryDirectory() as directory:
            now = datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            root = Path(directory)
            store = StrategyAccountStore(root/'test.sqlite3',clock=lambda:now)
            state = store.initialize('test',operation_id='init')
            state,_ = store.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=state['revision'])
            payload = dict(schema='FROZEN_WEIGHT_TARGET_RESEARCH_V1',strategy_contract_sha256='a'*64,
                strategy_epoch='synthetic-one',account_id='test',account_revision=state['revision'],
                weights={'NEW':'1'},signal_at='2026-11-05T21:00:00Z',valid_from='2026-11-06T14:30:00Z',
                valid_until='2026-11-06T14:32:00Z',
                marks={'NEW':dict(security_id='NEW',currency='USD',price_basis='current',observed_at=now.isoformat(),price='100')},
                limits={'NEW':dict(security_id='NEW',price_basis='current',observed_at=now.isoformat(),buy='100',sell='100')})
            document = dict(payload=payload,target_id=digest(payload))
            document['proposal_id'] = digest(dict(target_id=document['target_id'],schema='FROZEN_WEIGHT_PROPOSAL_RESEARCH_V1'))
            path = root/'target.json'
            raw = json.dumps(document).encode()
            path.write_bytes(raw)
            service = FrozenTargetProvider(path=path,file_sha256=sha256(raw).hexdigest(),contract_sha256='a'*64,
                expected_epoch='synthetic-one',account_id='test',store=store,clock=lambda:now)
            app = FastAPI();app.include_router(create_router(service=service))
            with TestClient(app) as client:
                body = dict(expected_revision=state['revision'],target_id=document['target_id'],expected_proposal_id=document['proposal_id'])
                def request():
                    return client.post('/api/strategy-daily-v3/preview',json=body)
                result=request()
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()['target_id'],document['target_id'])
                self.assertEqual(result.json()['difference']['new_orders'][0]['quantity'],10)
                self.assertFalse(result.json()['executable'])
                payload['weights']['NEW']='1/2'
                changed=json.dumps(document).encode();path.write_bytes(changed)
                self.assertEqual(request().json()['reason'],'TARGET_FILE_HASH_MISMATCH')
                service.file_sha256=sha256(changed).hexdigest()
                self.assertEqual(request().json()['reason'],'TARGET_HASH_MISMATCH')
                path.write_bytes(raw);service.file_sha256=sha256(raw).hexdigest()
                service.contract='b'*64
                self.assertEqual(request().json()['reason'],'STRATEGY_CONTRACT_MISMATCH')
                service.contract='a'*64
                service.clock=lambda:now+timedelta(seconds=61)
                self.assertEqual(request().status_code,409)
                service.clock=lambda:now+timedelta(seconds=121)
                self.assertEqual(request().json()['reason'],'QUOTE_EXPIRED')
                service.clock=lambda:now
                body['expected_proposal_id']='e'*64
                self.assertEqual(request().json()['reason'],'STALE_TARGET')
                # Even a server-pinned malformed snapshot must reject before
                # target division, rather than raising HTTP 500.
                for field, value, reason in [('price','0','POSITIVE_QUOTE_REQUIRED'),
                        ('price','-1','INVALID_EXACT_QUOTE'),('price','1/0','INVALID_EXACT_QUOTE'),
                        ('price','NaN','INVALID_EXACT_QUOTE'),('currency','HKD','QUOTE_CURRENCY_MISMATCH')]:
                    malformed=json.loads(raw)
                    malformed['payload']['marks']['NEW'][field]=value
                    malformed['target_id']=digest(malformed['payload'])
                    malformed['proposal_id']=digest(dict(target_id=malformed['target_id'],schema='FROZEN_WEIGHT_PROPOSAL_RESEARCH_V1'))
                    data=json.dumps(malformed).encode();path.write_bytes(data)
                    service.file_sha256=sha256(data).hexdigest()
                    body.update(target_id=malformed['target_id'],expected_proposal_id=malformed['proposal_id'])
                    response=request()
                    self.assertEqual(response.status_code,409,response.text)
                    self.assertEqual(response.json()['reason'],reason)
                path.write_bytes(raw);service.file_sha256=sha256(raw).hexdigest()
                body.update(target_id=document['target_id'],expected_proposal_id=document['proposal_id'])
                service.expected_epoch='wrong'
                self.assertEqual(request().json()['reason'],'STRATEGY_EPOCH_MISMATCH')
                self.assertEqual(store.read(),state)


if __name__ == '__main__':
    unittest.main()
