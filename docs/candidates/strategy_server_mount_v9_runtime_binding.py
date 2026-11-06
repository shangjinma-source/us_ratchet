"""V34 opt-in; prior releases retain the unchanged V8 mount."""
from pathlib import Path
from fastapi.routing import APIRoute
from api import strategy_server_mount_v8 as legacy
from api import strategy_server_mount_v6 as active_reader
from data.strategy_unified_server_preparation_v7 import _read

def mount_strategy_routes(*,app,root,environment):
 root=Path(root);active,active_digest=active_reader._read_active(root)
 if active_reader.PATH_ENV in environment or active_reader.SHA_ENV in environment:
  reference=active_reader._reference(environment.get(active_reader.PATH_ENV),environment.get(active_reader.SHA_ENV))
  if active is not None and active!=reference:raise ValueError('STRATEGY_ACTIVE_ENVIRONMENT_CONFLICT')
 else:reference=active
 if reference is None:return legacy.mount_strategy_routes(app=app,root=root,environment=environment)
 path,digest=reference;_,configuration=_read(root,dict(path=path,sha256=digest))
 if configuration.get('schema')!='ROA_UNIFIED_PREPARATION_V34':return legacy.mount_strategy_routes(app=app,root=root,environment=environment)
 from data.strategy_unified_server_preparation_v34 import build_unified_server_preparation_v34
 prepared=build_unified_server_preparation_v34(root=root,configuration_path=path,configuration_sha256=digest)
 keys={(r.path,m) for r in app.routes if hasattr(r,'methods') for m in r.methods}
 for route in prepared['router'].routes:
  if not isinstance(route,APIRoute):raise ValueError('STRATEGY_MOUNT_HTTP_ROUTE_REQUIRED')
  incoming={(route.path,m) for m in route.methods}
  if keys.intersection(incoming):raise ValueError('STRATEGY_MOUNT_DUPLICATE_ROUTE')
  keys.update(incoming)
 if active_reader._read_active(root)!=(active,active_digest):raise ValueError('STRATEGY_ACTIVE_MANIFEST_CHANGED_DURING_STARTUP')
 prepared['validate_code']();app.include_router(prepared['router'])
 from api.roa_runtime_binding import build_runtime_binding_router
 app.include_router(build_runtime_binding_router(active_sha256=active_digest,configuration_path=path,configuration_sha256=digest,configuration=configuration))
 return dict(mode='UNIFIED_V34',policy_approved_by_mount=False,roa_enabled=True)
