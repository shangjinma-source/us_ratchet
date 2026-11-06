import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest
from fastapi import FastAPI, APIRouter

class RuntimeBindingMountTests(unittest.TestCase):
    def test_existing_runtime_route_rejected(self):
        candidate=Path(__file__).resolve().parents[1]/'docs/candidates/strategy_server_mount_v9_runtime_binding.py'
        spec=importlib.util.spec_from_file_location('runtime_binding_mount_candidate',candidate)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        app=FastAPI()
        @app.get('/api/strategy-roa/runtime-binding')
        def conflicting():return {'old':True}
        config={'schema':'ROA_UNIFIED_PREPARATION_V34','roa':{'monthly_selections':{}}}
        with patch.object(module.active_reader,'_read_active',return_value=(('candidate.json','a'*64),'b'*64)),patch.object(module,'_read',return_value=(b'{}',config)),patch('data.strategy_unified_server_preparation_v34.build_unified_server_preparation_v34',return_value={'router':APIRouter(),'validate_code':lambda:None}):
            with self.assertRaisesRegex(ValueError,'DUPLICATE_ROUTE'):
                module.mount_strategy_routes(app=app,root=Path('.'),environment={})
        self.assertEqual(len([r for r in app.routes if r.path=='/api/strategy-roa/runtime-binding']),1)

if __name__=='__main__':unittest.main()
