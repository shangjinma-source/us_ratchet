from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import APIRouter
import data.strategy_unified_server_preparation_v27 as module


class BuilderTests(unittest.TestCase):
    def test_route_replacement_preserves_account_routes_and_does_not_create_storage(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            config = dict(schema='SAVED_FRONTIER_UNIFIED_PREPARATION_V27',
                base_v26=dict(path='base.json', sha256='b'), release=dict(path='release.json', sha256='r'),
                source_pins={name:'digest' for name in module.SOURCES},
                proposal_database='data/strategy_account/frontier.sqlite3',
                capture_root='data/strategy_account/captures', archive_root='data/strategy_account/archive',
                display_root='data/strategy_account/display')
            release = dict(authorized=True, authorized_at='2026-01-01T00:00:00+00:00', policy_id=module.POLICY_ID, monthly_cap='1/2',
                           exit_ratio='4/5', sma20_overlay=False)
            def read(root, reference):
                value = config if reference['path']=='config.json' else release if reference['path']=='release.json' else {}
                return repr(value).encode(), deepcopy(value)
            router = APIRouter()
            for path, method in [('/api/strategy-account/target','GET'),
                ('/api/strategy-account/target/generate','POST'),('/api/strategy-account/target/preview','POST'),
                ('/api/strategy-account/target/bars','GET'),('/api/strategy-daily-v3/preview','POST'),
                ('/api/strategy-display/latest-bars','GET'),('/api/strategy-account/cash','POST')]:
                router.add_api_route(path, lambda: {}, methods=[method])
            monthly = SimpleNamespace(accounts=SimpleNamespace(path=root/'account.sqlite3'),
                                      targets=SimpleNamespace(path=root/'target.sqlite3'))
            packet = SimpleNamespace(reference=dict(path='packet.json', sha256='p'),
                                     fetch_daily=None, fetch_official=None)
            reader = SimpleNamespace(source_reader=SimpleNamespace(packet_reader=packet),
                                     risk_store=SimpleNamespace(path=root/'risk.sqlite3'))
            prior = SimpleNamespace(reader=reader)
            old = SimpleNamespace(service=SimpleNamespace(service=prior), journal=object(),
                                  clock=lambda:None, policy_references={})
            prepared = dict(monthly=monthly, observed_daily=old, router=router, validate_code=lambda:None)
            with patch.object(module, '_read', side_effect=read), \
                 patch.object(module, '_read_digest', return_value='digest'), \
                 patch.object(module, 'build_unified_server_preparation_v26', return_value=prepared):
                result = module.build_unified_server_preparation_v27(root=root,
                    configuration_path='config.json', configuration_sha256='c')
            routes=[(r.path,tuple(sorted(r.methods))) for r in result['router'].routes]
            self.assertEqual(len(routes),len(set(routes)))
            self.assertIn(('/api/strategy-account/cash',('POST',)),routes)
            self.assertIs(result['monthly'],monthly)
            self.assertIs(result['frontier_reader'].risk,reader.risk_store)
            self.assertFalse(result['proposal_migration_performed'])
            self.assertEqual(list(root.iterdir()),[])

if __name__=='__main__':unittest.main()
