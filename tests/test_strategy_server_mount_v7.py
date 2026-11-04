import unittest
from unittest.mock import patch
from fastapi import APIRouter, FastAPI
from api import strategy_server_mount_v7 as mount
from data import strategy_unified_server_preparation_v28 as preparation


class MountTests(unittest.TestCase):
    def setUp(self):
        self.reference = ('candidate.json', 'a'*64)
        self.active = (self.reference, 'b'*64)
        self.router = APIRouter()
        self.router.add_api_route('/api/fixture', lambda: {}, methods=['GET'])

    def invoke(self, *, schema='VERIFIED_REPLAY_UNIFIED_PREPARATION_V28',
               states=None, app=None, environment=None, error=None):
        app = app or FastAPI()
        with patch.object(mount.previous, '_read_active', side_effect=states or [self.active, self.active]), \
             patch.object(mount, '_read', return_value=(b'{}', {'schema': schema})), \
             patch.object(preparation, 'build_unified_server_preparation_v28',
                 side_effect=error, return_value={'router': self.router, 'validate_code': lambda: None}) as build, \
             patch.object(mount.previous, 'mount_strategy_routes', return_value={'mode': 'OLD'}) as old:
            result = mount.mount_strategy_routes(app=app, root='.', environment=environment or {})
            return result, build.call_count, old.call_count, app

    def test_explicit_candidate_mounts_once(self):
        result, built, old, app = self.invoke()
        self.assertEqual(result['mode'], 'UNIFIED_V28')
        self.assertEqual((built, old), (1, 0))
        self.assertEqual(sum(route.path == '/api/fixture' for route in app.routes), 1)

    def test_old_configuration_keeps_original_mount(self):
        result, built, old, _ = self.invoke(schema='SAVED_FRONTIER_UNIFIED_PREPARATION_V27')
        self.assertEqual((result['mode'], built, old), ('OLD', 0, 1))

    def test_changed_manifest_does_not_mount(self):
        app = FastAPI()
        with self.assertRaisesRegex(ValueError, 'CHANGED_DURING_STARTUP'):
            self.invoke(states=[self.active, (None, None)], app=app)
        self.assertFalse(any(route.path == '/api/fixture' for route in app.routes))

    def test_build_failure_does_not_fallback(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            self.invoke(error=ValueError('SOURCE_CHANGED'))

    def test_duplicate_route_rejected(self):
        app = FastAPI()
        app.include_router(self.router)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_ROUTE'):
            self.invoke(app=app)

    def test_environment_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ENVIRONMENT_CONFLICT'):
            self.invoke(environment={mount.previous.PATH_ENV: 'other.json', mount.previous.SHA_ENV: 'c'*64})
