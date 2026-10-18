import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_difference_service import fixture
from data.current_quantity_v2_difference_factory import create_service, SCHEMA, ACCOUNT_SCHEMA
from api.current_quantity_v2_difference import create_router


def saved_fixture(root):
    _,identifier,package,account,clock=fixture()
    for name,raw in package['files'].items():(root/name).write_bytes(raw)
    account_doc=dict(schema=ACCOUNT_SCHEMA,state=account)
    (root/'account.json').write_text(json.dumps(account_doc))
    descriptor=dict(schema=SCHEMA,accounts={account['account_id']:'account.json'},decisions={identifier:dict(
        account_id=account['account_id'],documents=package['documents'],source_hashes=package['source_hashes'])})
    raw=json.dumps(descriptor).encode();(root/'descriptor.json').write_bytes(raw)
    service=create_service(root=root,descriptor_path='descriptor.json',descriptor_sha256=sha256(raw).hexdigest(),clock=lambda:clock[0])
    return service,identifier,descriptor,account_doc


class FactoryTests(unittest.TestCase):
    def test_file_backed_cash_genesis_and_tamper(self):
        from test_current_quantity_v2_difference_cash_service import fixture as cash_fixture
        with TemporaryDirectory() as folder:
            root=Path(folder);_,identifier,package,account,clock=cash_fixture()
            for name,raw in package['files'].items():(root/name).write_bytes(raw)
            (root/'account.json').write_text(json.dumps(dict(schema=ACCOUNT_SCHEMA,state=account)))
            descriptor=dict(schema=SCHEMA,accounts={account['account_id']:'account.json'},
                decisions={identifier:dict(account_id=account['account_id'],
                    documents=package['documents'],source_hashes=package['source_hashes'])})
            raw=json.dumps(descriptor).encode();(root/'descriptor.json').write_bytes(raw)
            service=create_service(root=root,descriptor_path='descriptor.json',descriptor_sha256=sha256(raw).hexdigest(),clock=lambda:clock[0])
            proposal=service._proposal(identifier)
            self.assertEqual(proposal['causal_inputs']['target_scope'],'NEW_CASH_STRATEGY_INITIAL_TARGET')
            self.assertTrue(proposal['orders'])
            self.assertTrue(all(o['side']=='BUY' for o in proposal['orders']))
            before={p.name:p.read_bytes() for p in root.iterdir()}
            app=FastAPI();app.include_router(create_router(service=service))
            with TestClient(app) as client:
                response=client.post('/api/current_portfolio_research/difference',json={'decision_id':identifier})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['proposal_id'],proposal['proposal_id'])
                self.assertNotIn('causal_inputs',response.json())
                self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
                name=package['documents']['genesis_declaration'];(root/name).write_bytes(before[name]+b' ')
                response=client.post('/api/current_portfolio_research/difference',json={'decision_id':identifier})
                self.assertEqual(response.status_code,503,response.text)
                self.assertEqual(response.json()['orders'],[])

    def test_optional_genesis_must_be_registered_and_pinned(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);_,identifier,descriptor,_=saved_fixture(root)
            entry=descriptor['decisions'][identifier]
            raw=b'{"purpose":"PAPER_INITIALIZATION_NOT_BROKER_BALANCE"}'
            (root/'genesis.json').write_bytes(raw)
            entry['documents']['genesis_declaration']='genesis.json'
            entry['source_hashes']['genesis.json']=sha256(raw).hexdigest()
            def construct(value):
                encoded=json.dumps(value).encode();(root/'descriptor.json').write_bytes(encoded)
                return create_service(root=root,descriptor_path='descriptor.json',descriptor_sha256=sha256(encoded).hexdigest())
            construct(descriptor)  # Registration only; incomplete declaration is not an accepted proposal.
            for mode in ('unpinned','unknown_document','duplicate_decision'):
                changed=deepcopy(descriptor)
                registration=changed['decisions'][identifier]
                if mode=='unpinned':registration['source_hashes'].pop('genesis.json')
                elif mode=='unknown_document':registration['documents']['client_scope']='genesis.json'
                else:
                    encoded=json.dumps(changed).replace('"decisions": {','"decisions": {"'+identifier+'": {},',1).encode()
                    (root/'descriptor.json').write_bytes(encoded)
                    with self.assertRaisesRegex(ValueError,'DUPLICATE_SOURCE_KEY'):
                        create_service(root=root,descriptor_path='descriptor.json',descriptor_sha256=sha256(encoded).hexdigest())
                    continue
                with self.assertRaises(ValueError):construct(changed)

    def test_http_file_chain_and_drift_leave_no_orders(self):
        for mode in ('raw','descriptor','account','missing_order_fields'):
            with TemporaryDirectory() as folder:
                root=Path(folder);service,identifier,_,account=saved_fixture(root)
                app=FastAPI();app.include_router(create_router(service=service))
                with TestClient(app) as client:
                    before={p.name:p.read_bytes() for p in root.iterdir()}
                    response=client.post('/api/current_portfolio_research/difference',json={'decision_id':identifier})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
                    if mode=='raw':(root/'X.raw').write_bytes(before['X.raw']+b' ')
                    elif mode=='descriptor':(root/'descriptor.json').write_bytes(before['descriptor.json']+b' ')
                    else:
                        if mode=='account':account['state']['revision']='changed'
                        else:account['state'].pop('open_orders')
                        (root/'account.json').write_text(json.dumps(account))
                    response=client.post('/api/current_portfolio_research/difference',json={'decision_id':identifier})
                    self.assertEqual(response.status_code,503,response.text)
                    self.assertEqual(response.json()['orders'],[])

    def test_unsafe_paths_duplicate_json_and_hash_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);_,_,descriptor,_=saved_fixture(root)
            for mode in ('traversal','absolute','duplicate','hash'):
                obj=deepcopy(descriptor)
                if mode=='traversal':obj['accounts']['synthetic-account']='../outside.json'
                if mode=='absolute':obj['accounts']['synthetic-account']='C:/outside.json'
                raw=json.dumps(obj).encode()
                if mode=='duplicate':raw=b'{"schema":"a","schema":"b"}'
                (root/'descriptor.json').write_bytes(raw)
                with self.assertRaises(ValueError):
                    create_service(root=root,descriptor_path='descriptor.json',
                        descriptor_sha256='0'*64 if mode=='hash' else sha256(raw).hexdigest())

    def test_actual_file_mutation_between_account_reads_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);service,identifier,_,account=saved_fixture(root)
            original=service.account_reader;calls=[0]
            def reader(account_id):
                result=original(account_id);calls[0]+=1
                if calls[0]==1:
                    account['state']['revision']='new'
                    (root/'account.json').write_text(json.dumps(account))
                return result
            service.account_reader=reader
            result=service.preview(identifier)
            self.assertEqual(result['status'],'UNAVAILABLE');self.assertEqual(result['orders'],[])
            self.assertIn('ACCOUNT_CHANGED',result['reason'])

    def test_symlink_escape_and_account_size_rejected(self):
        with TemporaryDirectory() as folder, TemporaryDirectory() as outside:
            root=Path(folder);service,identifier,_,_=saved_fixture(root)
            original=(root/'account.json').read_bytes()
            target=Path(outside)/'account.json';target.write_bytes(original)
            (root/'account.json').unlink()
            try:(root/'account.json').symlink_to(target)
            except OSError as error:self.skipTest(str(error))
            result=service.preview(identifier)
            self.assertEqual(result['orders'],[]);self.assertIn('OUTSIDE_ROOT',result['reason'])
            (root/'account.json').unlink();(root/'account.json').write_bytes(b' '*(1024*1024+1))
            result=service.preview(identifier)
            self.assertEqual(result['orders'],[]);self.assertIn('TOO_LARGE',result['reason'])


if __name__=='__main__':unittest.main()
