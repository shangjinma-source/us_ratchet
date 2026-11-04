import unittest
from unittest.mock import patch
from fastapi import APIRouter, FastAPI
from api import strategy_server_mount_v8 as mount
from data import strategy_unified_server_preparation_v30 as preparation


class BoundSnapshotMountTests(unittest.TestCase):
    def invoke(self, *, error=None, changed=False, duplicate=False):
        app = FastAPI()
        router = APIRouter()
        router.add_api_route('/snapshot-fixture', lambda: {}, methods=['GET'])
        if duplicate:
            app.include_router(router)
        active = (('candidate.json', 'a'*64), 'b'*64)
        with patch.object(mount.previous, '_read_active', side_effect=[active, (None, None) if changed else active]), \
             patch.object(mount, '_read', return_value=(b'{}', {'schema': 'BOUND_UI_SNAPSHOT_UNIFIED_PREPARATION_V30'})), \
             patch.object(preparation, 'build_unified_server_preparation_v30', side_effect=error,
                 return_value={'router': router, 'validate_code': lambda: None}) as build, \
             patch.object(mount.previous_mount, 'mount_strategy_routes', side_effect=AssertionError('NO_FALLBACK')):
            result = mount.mount_strategy_routes(app=app, root='.', environment={})
        self.assertEqual(build.call_count, 1)
        return result, app

    def test_explicit_version_mounts_once(self):
        result, app = self.invoke()
        self.assertEqual(result['mode'], 'UNIFIED_V30')
        self.assertFalse(result['policy_approved_by_mount'])
        self.assertEqual(sum(route.path == '/snapshot-fixture' for route in app.routes), 1)

    def test_build_error_never_falls_back(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            self.invoke(error=ValueError('SOURCE_CHANGED'))

    def test_changed_manifest_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CHANGED_DURING_STARTUP'):
            self.invoke(changed=True)

    def test_duplicate_route_rejected(self):
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_ROUTE'):
            self.invoke(duplicate=True)
