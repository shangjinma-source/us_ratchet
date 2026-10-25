"""Typed daily source failure boundary over unchanged V16 strategy."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v16 import build_unified_server_preparation_v16
from api.strategy_daily_preview_v4 import create_router

V17_SOURCES={'data/strategy_unified_server_preparation_v17.py','api/strategy_daily_preview_v4.py'}
def build_unified_server_preparation_v17(*,root,configuration_path,configuration_sha256,clock=None):
 root=Path(root).absolute();reference=dict(path=configuration_path,sha256=configuration_sha256)
 raw,config=_read(root,reference)
 require(set(config)=={'schema','base_v16','source_pins'} and config['schema']=='DAILY_SOURCE_ERROR_UNIFIED_PREPARATION_V17','V17_CONFIGURATION_FIELDS')
 require(set(config['source_pins'])==V17_SOURCES,'V17_SOURCE_SCOPE')
 executing=Path(__file__).resolve().parents[1]
 def check():
  require(_read(root,reference)[0]==raw,'V17_CONFIGURATION_CHANGED')
  for name,digest in config['source_pins'].items():
   require(_read_digest(root/name,32*1024*1024)==digest and _read_digest(executing/name,32*1024*1024)==digest,'V17_SOURCE_CHANGED')
 check()
 base=config['base_v16']
 prepared=build_unified_server_preparation_v16(root=root,configuration_path=base['path'],configuration_sha256=base['sha256'],clock=clock)
 oldgate=prepared['validate_code']
 def gate():oldgate();check()
 service=prepared['observed_daily']
 class Boundary:
  def preview(self,**kwargs):
   gate()
   result=service.preview(**kwargs)
   gate()
   return result
 matches=[r for r in prepared['router'].routes if isinstance(r,APIRoute) and r.path=='/api/strategy-daily-v3/preview' and r.methods=={'POST'}]
 require(len(matches)==1,'V17_DAILY_ROUTE_REQUIRED')
 router=APIRouter();router.routes.extend(r for r in prepared['router'].routes if r is not matches[0]);router.include_router(create_router(service=Boundary()))
 return dict(prepared,router=router,validate_code=gate)
