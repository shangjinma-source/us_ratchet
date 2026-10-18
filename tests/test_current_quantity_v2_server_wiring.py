"""Execute the actual server composition statements without importing its runtime."""
import ast
import json
from datetime import timezone
from fractions import Fraction
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_difference import create_router as difference_router
from api.current_quantity_v2_paper import create_router as paper_router, PREFIX
from data.current_quantity_v2_current_cash_factory import create_services
from data.current_quantity_v2_bounded_unit_review import BoundedPublicUnitReview
from data.current_quantity_v2_monthly_composition import create_services as create_monthly_services
from data.current_quantity_v2_pullback_runtime import EXPERIMENTAL_POLICY,LazyPullbackCapStore
from test_current_quantity_v2_current_cash_sources import snapshot_fixture, month_config
from test_current_quantity_v2_intraday_reference import NOW, raw


class ServerCashWiringTests(unittest.TestCase):
    def test_real_mount_statements_preview_accept_restore(self):
        source = Path(__file__).resolve().parents[1] / 'api/server.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        selected = []
        for node in tree.body:
            if isinstance(node,ast.ImportFrom) and node.module=='data.current_quantity_v2_pullback_runtime':
                selected.append(node)
            elif isinstance(node,ast.Assign) and any(
                (isinstance(target,ast.Name) and target.id in
                 {'_current_quantity_pullback_caps','_current_quantity_cash','_current_quantity_monthly'}) or
                (isinstance(target,ast.Subscript) and isinstance(target.value,ast.Name)
                 and target.value.id=='_current_quantity_cash') for target in node.targets):
                selected.append(node)
            elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
                call=node.value
                if (isinstance(call.func,ast.Attribute) and call.func.attr=='include_router'
                    and call.args and isinstance(call.args[0],ast.Call)
                    and isinstance(call.args[0].func,ast.Name) and call.args[0].func.id in
                    {'create_quantity_difference_router','create_quantity_paper_router'}):
                    selected.append(node)
        self.assertEqual(len(selected),7)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshots, view = snapshot_fixture(root)
            calls = []
            constructed = []

            def factory(**kwargs):
                self.assertIsInstance(kwargs['unit_review_reader'], BoundedPublicUnitReview)
                self.assertEqual(kwargs['unit_review_reader'].policy, 'BOUNDED_PUBLIC_KNOWN_ACTIONS_V1')
                self.assertEqual(kwargs['root'], root)
                self.assertEqual(kwargs['pullback_policy'],EXPERIMENTAL_POLICY)
                self.assertIsInstance(kwargs['pullback_cap_store'],LazyPullbackCapStore)
                self.assertEqual(kwargs['pullback_cap_store'].path,root/'data/quantity_v2_pullback/entry_caps.sqlite3')
                self.assertEqual(kwargs['server_account_id'], 'current-quantity-v2-paper-pool')
                self.assertEqual(kwargs['database_path'], root / 'data/quantity_v2_paper/paper.sqlite3')
                expected_mandate = dict(
                    path='research_contracts/current_quantity_v2_initial_execution_month_20261015_v2.json',
                    sha256='448f62e53ee381864cf1a2b0084da9f97dd0ea7349140bf566a2a1152fb25a29')
                self.assertEqual(kwargs['execution_month_mandate'], expected_mandate)
                from hashlib import sha256
                declaration = source.parents[1] / expected_mandate['path']
                self.assertEqual(sha256(declaration.read_bytes()).hexdigest(), expected_mandate['sha256'])
                kwargs['execution_month_mandate'] = month_config(root)
                def fetch(ticker):
                    calls.append(ticker)
                    # The production pullback rule needs every completed minute
                    # since open. The old one-bar quote fixture is insufficient.
                    payload=json.loads(raw(ticker,10));quote=payload['chart']['result'][0]
                    start=quote['meta']['currentTradingPeriod']['regular']['start']
                    end=int(NOW.timestamp())//60*60
                    minutes=list(range(start,end,60));quote['timestamp']=minutes
                    quote['indicators']['quote']=[dict(open=[10]*len(minutes),high=[11]*len(minutes),
                        low=[9]*len(minutes),close=[10]*len(minutes),volume=[10]*len(minutes))]
                    return json.dumps(payload).encode()
                result = create_services(**kwargs, fetch=fetch, clock=lambda: NOW)
                constructed.append(result)
                return result

            app = FastAPI()
            namespace = dict(Path=Path,datetime=SimpleNamespace(now=lambda zone:NOW),timezone=timezone,server_environment={},
                create_quantity_monthly_services=create_monthly_services, __file__=str(root / 'api/server.py'), app=app,
                _current_quantity_research=snapshots, create_current_cash_services=factory,
                BoundedPublicUnitReview=BoundedPublicUnitReview,
                create_quantity_difference_router=difference_router,
                create_quantity_paper_router=paper_router)
            exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), namespace)
            self.assertEqual(calls, [])
            self.assertFalse(constructed[0]['store'].path.exists())
            self.assertFalse((root/'data/quantity_v2_pullback').exists())
            self.assertFalse((root/'data/quantity_v2_observations').exists())
            services=constructed[0]
            self.assertEqual(services['sources'].audit_storage_root,root/'data/quantity_v2_observations/current_cash_captures')
            self.assertEqual(services['continuation_sources'].audit_storage_root,root/'data/quantity_v2_observations/current_cash_continuation_captures')
            self.assertIs(services['sources'].pullback_cap_store,services['continuation_sources'].pullback_cap_store)
            self.assertFalse(namespace['_current_quantity_monthly']['configured'])
            with patch.object(snapshots, 'calculate', side_effect=AssertionError('no new search')):
                with TestClient(app) as client:
                    preview = client.post('/api/current_portfolio_research/difference',
                                          json={'decision_id': view['decision_id']})
                    self.assertEqual(preview.status_code, 200, preview.text)
                    self.assertEqual(calls, ['AAA', 'BBB'])
                    proposal = preview.json()
                    self.assertTrue(proposal['orders'])
                    self.assertTrue(all(order['side']=='BUY' and Fraction(order['limit_price'])==Fraction(19,2)
                                        for order in proposal['orders']))
                    self.assertTrue((root/'data/quantity_v2_pullback/entry_caps.sqlite3').exists())
                    captures=list((services['sources'].audit_storage_root/'captures/audit').iterdir())
                    self.assertEqual(len(captures),1)
                    audited=services['sources'].audit(captures[0].name,'current-quantity-v2-paper-pool')
                    self.assertEqual(audited['status'],'CAPTURED')
                    self.assertEqual(audited['binding_scope']['binding_kind'],'DECLARED_EMPTY_GENESIS')
                    self.assertIsNone(audited['binding_scope']['chain_sha256'])
                    self.assertFalse(services['continuation_sources'].audit_storage_root.exists())
                    request = dict(account_id=proposal['account_id'],
                                   proposal_id=proposal['proposal_id'], operation_id='wiring-accept')
                    accepted = client.post(PREFIX + '/accept', json=request)
                    self.assertEqual(accepted.status_code, 200, accepted.text)
                    self.assertTrue(accepted.json()['capabilities']['continuation']['configured'])
                    self.assertEqual(accepted.json()['capabilities']['continuation']['policy'],
                                     'BOUNDED_PUBLIC_KNOWN_ACTIONS_V1')
                    self.assertEqual(accepted.json()['target_quantities'], {'A': 6, 'B': 4})
                    restored = client.get(PREFIX + '/account', params={'account_id': proposal['account_id']})
                    self.assertEqual(restored.status_code, 200, restored.text)
                    self.assertEqual(restored.json(), accepted.json())
                    self.assertEqual(calls, ['AAA', 'BBB'])


if __name__ == '__main__':
    unittest.main()
