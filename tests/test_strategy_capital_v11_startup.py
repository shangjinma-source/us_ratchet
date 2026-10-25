"""Create-only configuration and explicit startup dispatch, no live account writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from unittest.mock import patch
import unittest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.strategy_capital_v11_materializer import materialize_capital_v11
from data.strategy_unified_server_preparation_v11 import V11_SOURCES
from api.strategy_server_mount_v6 import mount_strategy_routes,PATH_ENV,SHA_ENV

class V11StartupTests(unittest.TestCase):
 def test_create_only_and_explicit_dispatch(self):
  with TemporaryDirectory() as temp:
   root=Path(temp);source=Path(__file__).resolve().parents[1];pins={}
   for name in V11_SOURCES:
    raw=(source/name).read_bytes();dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
   raw=canonical({'schema':'LATEST_DISPLAY_UNIFIED_PREPARATION_V10'});(root/'base.json').write_bytes(raw)
   kwargs=dict(root=root,base_v10={'path':'base.json','sha256':sha256(raw).hexdigest()},source_pins=pins,output_path='candidate/server.json',validate_sources=lambda:None)
   result=materialize_capital_v11(**kwargs)
   with self.assertRaisesRegex(ValueError,'V11_OUTPUT_EXISTS'):materialize_capital_v11(**kwargs)
   router=APIRouter()
   router.add_api_route('/api/strategy-account/target/preview',lambda:{},methods=['POST'])
   router.add_api_route('/api/strategy-capital-v2/status',lambda:{'status':'NOT_FOUND'},methods=['POST'])
   app=FastAPI();ref=result['server_reference']
   with patch('data.strategy_unified_server_preparation_v11.build_unified_server_preparation_v11',return_value={'router':router}) as builder:
    mounted=mount_strategy_routes(app=app,root=root,environment={PATH_ENV:ref['path'],SHA_ENV:ref['sha256']})
   self.assertEqual(mounted['mode'],'UNIFIED_V11');builder.assert_called_once()
   client=TestClient(app)
   self.assertEqual(client.post('/api/strategy-capital-v2/status').status_code,200)
   self.assertEqual(client.post('/api/strategy-account/target/preview').status_code,404)
   self.assertFalse((root/'config/strategy_server_active.json').exists())
   self.assertFalse((root/'data/strategy_account').exists())
 def test_changed_source_cannot_materialize(self):
  with TemporaryDirectory() as temp:
   root=Path(temp);raw=canonical({'schema':'LATEST_DISPLAY_UNIFIED_PREPARATION_V10'});(root/'base.json').write_bytes(raw)
   with self.assertRaises((ValueError,FileNotFoundError)):
    materialize_capital_v11(root=root,base_v10={'path':'base.json','sha256':sha256(raw).hexdigest()},source_pins={name:'0'*64 for name in V11_SOURCES},output_path='candidate.json',validate_sources=lambda:None)
   self.assertFalse((root/'candidate.json').exists())
if __name__=='__main__':unittest.main()
