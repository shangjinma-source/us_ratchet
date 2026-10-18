"""Explicit configuration and real server statements without importing production."""
import ast
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_composition import create_services,MonthlyFileConfiguration
from api.current_quantity_v2_monthly_research import create_router,PREFIX
from test_current_quantity_v2_monthly_research_service import fixture
from test_current_quantity_v2_bounded_unit_review import feed


def config_fixture(folder):
    _,state,supplied,source,paper,clock=fixture(folder);root=Path(folder)/'inputs';root.mkdir()
    for name,raw in supplied['source_package']['files'].items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    ledger=state['ledger'];entry=dict(account_id=ledger['account_id'],state_revision=ledger['revision'],target_month='2026-11',source_hashes=supplied['source_package']['source_hashes'],**{k:v for k,v in supplied.items() if k!='source_package'})
    review=dict(account_id=ledger['account_id'],state_revision=ledger['revision'],source_hashes=entry['source_hashes'],account_review_path=entry['account_review_path'])
    raw=canonical(dict(schema='QUANTITY_V2_MONTHLY_SERVER_INPUTS_V1',training_entries=[entry],account_reviews=[review]));(root/'config.json').write_bytes(raw)
    paper.clock=lambda:clock[0]
    return root,sha256(raw).hexdigest(),paper,state,clock,source


class MonthlyCompositionTests(unittest.TestCase):
    def test_pullback_store_is_shared_without_construction_io(self):
        from data.current_quantity_v2_pullback_runtime import EXPERIMENTAL_POLICY
        class UnusedCaps:
            def candidate(self, **kwargs):
                raise AssertionError('construction must not quote')
        with TemporaryDirectory() as folder:
            root,h,paper,state,clock,source=config_fixture(folder)
            caps=UnusedCaps(); destination=Path(folder)/'monthly-pullback'
            services=create_services(root=root,paper_service=paper,storage_root=destination,
                config_path='config.json',config_sha256=h,fetch=source.fetch,
                pullback_policy=EXPERIMENTAL_POLICY,pullback_cap_store=caps)
            self.assertIs(services['monthly']['sources'].pullback_cap_store,caps)
            self.assertIs(services['continuation']['sources'].pullback_cap_store,caps)
            self.assertEqual(services['monthly']['sources'].pullback_policy,EXPERIMENTAL_POLICY)
            self.assertEqual(services['continuation']['sources'].pullback_policy,EXPERIMENTAL_POLICY)
            self.assertFalse(destination.exists())

    def test_actual_server_missing_config_is_readable_and_zero_io(self):
        from data.current_quantity_v2_paper_service import QuantityV2PaperService
        from data.current_quantity_v2_paper_store import QuantityV2PaperStore
        def forbidden(*a,**k):raise AssertionError('unexpected IO')
        with TemporaryDirectory() as folder:
            root=Path(folder);paper=QuantityV2PaperService(store=QuantityV2PaperStore(root/'missing'/'paper.sqlite3'),clock=forbidden)
            tree=ast.parse((Path(__file__).resolve().parents[1]/'api/server.py').read_text(encoding='utf-8'))
            nodes=[n for n in tree.body if (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_current_quantity_monthly' for t in n.targets)) or (isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and n.value.args and isinstance(n.value.args[0],ast.Call) and isinstance(n.value.args[0].func,ast.Name) and n.value.args[0].func.id=='create_quantity_monthly_research_router')]
            self.assertEqual(len(nodes),2);app=FastAPI()
            env=dict(Path=Path,__file__=str(root/'api/server.py'),app=app,EXPERIMENTAL_POLICY=None,_current_quantity_pullback_caps=None,_current_quantity_cash={'paper':paper},server_environment={},create_quantity_monthly_services=create_services,create_quantity_monthly_research_router=create_router)
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'server-monthly','exec'),env)
            self.assertIs(env['_current_quantity_monthly']['paper'],paper)
            with TestClient(app) as client:
                value=client.get(PREFIX,params={'account_id':'fixed'}).json();self.assertEqual(value['reason'],'MONTHLY_CONFIGURATION_REQUIRED')
                response=client.post(PREFIX+'/generate',json=dict(account_id='fixed',expected_revision='r',retry_failed=False));self.assertEqual(response.status_code,503);self.assertEqual(response.json()['error_code'],'MONTHLY_CONFIGURATION_REQUIRED')
            self.assertEqual(list(root.iterdir()),[])
            configured=create_services(root=root,paper_service=paper,storage_root=root/'new',config_path='absent.json',config_sha256='0'*64,fetch=forbidden,rss_fetch=forbidden)
            self.assertIs(configured['paper'].original,paper);self.assertEqual(list(root.iterdir()),[])
            for settings in ({'config_path':'only.json'},{'config_sha256':'0'*64},{'config_path':'valid.json','config_sha256':'invalid'}):
                broken=create_services(root=root,paper_service=paper,storage_root=root/'new',**settings)
                self.assertIs(broken['paper'],paper);self.assertFalse(broken['configured'])
                self.assertEqual(broken['research'].current(account_id='fixed')['reason'],'INVALID_MONTHLY_CONFIGURATION')
            self.assertEqual(list(root.iterdir()),[])

    def test_saved_training_generate_read_without_fetch_or_paper_mutation(self):
        with TemporaryDirectory() as folder:
            root,h,paper,state,clock,source=config_fixture(folder)
            def forbidden(*a):raise AssertionError('network forbidden')
            services=create_services(root=root,paper_service=paper,storage_root=Path(folder)/'monthly',config_path='config.json',config_sha256=h,fetch=source.fetch,rss_fetch=lambda:dict(status=200,body=feed()))
            self.assertFalse((Path(folder)/'monthly').exists())
            app=FastAPI();app.include_router(create_router(service=services['research']))
            aid=state['ledger']['account_id'];rev=state['ledger']['revision']
            with TestClient(app) as client:
                result=client.post(PREFIX+'/generate',json=dict(account_id=aid,expected_revision=rev,retry_failed=False))
                self.assertEqual(result.status_code,200,result.text);value=result.json();self.assertEqual(value['status'],'READY')
                self.assertTrue(value['portfolio']['frozen_dollar_allocations_exact']);self.assertNotIn('source_hashes',json.dumps(value))
                with patch('subprocess.run',side_effect=forbidden):
                    self.assertEqual(client.get(PREFIX,params={'account_id':aid}).json()['decision_id'],value['decision_id'])
            self.assertEqual(paper.store.read(aid),state)
            # Explicit fixture archive only: initial legacy paper origin has no
            # embedded bytes. Production current-cash origins use their frozen evidence.
            blobs=Path(folder)/'monthly'/'captures'/'blobs';blobs.mkdir(parents=True)
            for name,digest in state['ledger']['acceptance']['proposal']['causal_inputs']['execution_references']['A']['source_hashes'].items():
                raw=(root/name).read_bytes();self.assertEqual(sha256(raw).hexdigest(),digest);(blobs/digest).write_bytes(raw)
            proposal=services['paper'].monthly_preview(account_id=aid,decision_id=value['decision_id'],expected_revision=rev)
            self.assertIn('execution_references',proposal);self.assertIn('created_at',proposal)
            def inspect(value):
                if isinstance(value,dict):
                    self.assertFalse(set(value)&{'source_hashes','causal_inputs','binding','raw','files','bounded_evidence'})
                    for item in value.values():inspect(item)
                elif isinstance(value,list):
                    for item in value:inspect(item)
            inspect(proposal)
            private=services['monthly']['bridge']._proposals[proposal['proposal_id']]['proposal']
            self.assertTrue(next(iter(private['causal_inputs']['execution_references'].values()))['source_hashes'])
            accepted=services['paper'].accept_monthly_retarget(account_id=aid,proposal_id=proposal['proposal_id'],operation_id='configured-month',expected_revision=rev)
            current=paper.store.read(aid)
            for key in ('cash','shares','recorded_fees'):self.assertEqual(current['ledger'][key],state['ledger'][key])
            with self.assertRaisesRegex(ValueError,'EXPLICIT_ACCOUNT_REVIEW_REQUIRED'):services['configuration'].account_review_reader({'state':current})
            configuration=services['configuration'];changed=deepcopy(state);changed['ledger']['revision']='new'
            with self.assertRaisesRegex(ValueError,'EXPLICIT_ACCOUNT_REVIEW_REQUIRED'):configuration.account_review_reader({'state':changed})
            (root/'config.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'REGISTRY_SOURCE_CHANGED'):configuration.training_reader(state)

    def test_wrong_month_paths_missing_files_duplicate_json(self):
        with TemporaryDirectory() as folder:
            root,h,paper,state,clock,source=config_fixture(folder)
            configuration=MonthlyFileConfiguration(root=root,path='config.json',sha256_value=h,clock=lambda:clock[0])
            configuration.training_reader(state)
            clock[0]=clock[0].replace(month=12)
            with self.assertRaisesRegex(ValueError,'MONTHLY_SOURCE_UNAVAILABLE'):configuration.training_reader(state)
            with self.assertRaises(ValueError):MonthlyFileConfiguration(root=root,path='../escape',sha256_value=h,clock=lambda:clock[0])
            raw=b'{"schema":1,"schema":2}';(root/'duplicate.json').write_bytes(raw)
            duplicate=MonthlyFileConfiguration(root=root,path='duplicate.json',sha256_value=sha256(raw).hexdigest(),clock=lambda:clock[0])
            with self.assertRaisesRegex(ValueError,'DUPLICATE_SOURCE_KEY'):duplicate._config()


if __name__=='__main__':unittest.main()
