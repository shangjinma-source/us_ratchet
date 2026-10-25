"""Explicit V11 capital-arrival and quote-clock composition over unchanged V10.
Construction never imports capital records, credits cash, selects or publishes.
"""
from pathlib import Path
from contextlib import closing
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from core.strategy_profiled_capital_journal_v2 import ProfiledCapitalJournalV2
from data.strategy_capital_arrival_service_v2 import CapitalArrivalServiceV2
from data.strategy_unified_server_preparation_v10 import build_unified_server_preparation_v10
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_bounded_source_gate_v1 import _read_digest,_no_links
from scripts.register_quantity_v2_paper_protocol import safe_path
from api.strategy_capital_arrival_v2 import create_router

V11_SOURCES={
 'data/strategy_unified_server_preparation_v11.py',
 'data/strategy_account_market_capture_v2.py',
 'core/strategy_profiled_capital_journal_v2.py',
 'data/strategy_capital_arrival_service_v2.py',
 'api/strategy_capital_arrival_v2.py',
 'data/strategy_capital_capture_provider_v2.py',
 'data/strategy_account_action_capture_v4.py',
 'data/strategy_account_action_capture_v3.py',
 'data/strategy_rss_verified_transport_v1.py',
 'data/strategy_upgrade_blob_store_v1.py',
}
JOURNAL_PATH='data/strategy_account/profiled_capital_arrivals_v2.sqlite3'
OLD_ROUTES={('/api/strategy-capital-v1/'+name,'POST') for name in ('intents','configure','recover-publication','status')}

def attach_capital_arrival_v11(*,prepared,root,journal_path,validate_v11_sources):
 def gate():
  prepared['validate_code']();validate_v11_sources()
 gate();monthly=prepared['monthly']
 journal=ProfiledCapitalJournalV2(journal_path)
 # Import is an explicit deployment operation. Missing/corrupt V2 journal fails closed.
 with closing(journal._connect()) as connection:
  connection.execute('SELECT 1').fetchone()
 service=CapitalArrivalServiceV2(monthly=monthly,journal=journal,validate_code=gate)
 removed=set();router=APIRouter()
 for route in prepared['router'].routes:
  require(isinstance(route,APIRoute),'V11_HTTP_ROUTE_REQUIRED')
  keys={(route.path,method) for method in route.methods}
  if keys & OLD_ROUTES:
   require(keys <= OLD_ROUTES and not (removed & keys),'V11_OLD_CAPITAL_ROUTE_CONFLICT')
   removed.update(keys)
  else:router.routes.append(route)
 require(removed==OLD_ROUTES,'V11_OLD_CAPITAL_ROUTES_REQUIRED')
 router.include_router(create_router(service=service))
 keys=set()
 for route in router.routes:
  current={(route.path,method) for method in route.methods}
  require(not keys.intersection(current),'V11_DUPLICATE_ROUTE');keys.update(current)
 gate()
 return dict(prepared,router=router,capital_arrival=service,validate_code=gate)

def build_unified_server_preparation_v11(*,root,configuration_path,configuration_sha256,clock=None):
 root=Path(root).absolute();reference=dict(path=configuration_path,sha256=configuration_sha256)
 raw,config=_read(root,reference)
 require(set(config)=={'schema','base_v10','source_pins','capital_journal_path'}
  and config['schema']=='CAPITAL_ARRIVAL_UNIFIED_PREPARATION_V11','V11_CONFIGURATION_FIELDS')
 require(type(config['source_pins']) is dict and set(config['source_pins'])==V11_SOURCES,'V11_SOURCE_SCOPE')
 require(config['capital_journal_path']==JOURNAL_PATH,'V11_CAPITAL_STORAGE_REQUIRED')
 journal_path=safe_path(root,JOURNAL_PATH);_no_links(journal_path)
 executing=Path(__file__).resolve().parents[1]
 def gate():
  require(_read(root,reference)[0]==raw,'V11_CONFIGURATION_CHANGED')
  _read(root,config['base_v10'])
  for name,digest in config['source_pins'].items():
   require(_read_digest(root/name,32*1024*1024)==digest and _read_digest(executing/name,32*1024*1024)==digest,'V11_SOURCE_CHANGED')
 gate()
 prepared=build_unified_server_preparation_v10(root=root,configuration_path=config['base_v10']['path'],configuration_sha256=config['base_v10']['sha256'],clock=clock)
 return attach_capital_arrival_v11(prepared=prepared,root=root,journal_path=journal_path,validate_v11_sources=gate)
