"""Read-only startup binding. Mount only after formal builder and active recheck."""
from copy import deepcopy
from fastapi import APIRouter


def build_runtime_binding_router(*, active_sha256, configuration_path,
                                 configuration_sha256, configuration):
    payload=dict(schema='ROA_LOADED_RUNTIME_BINDING_V1',
                 loaded_active_sha256=active_sha256,
                 loaded_configuration=dict(path=configuration_path,sha256=configuration_sha256),
                 loaded_monthly_selections=deepcopy(configuration['roa'].get('monthly_selections',{})))
    router=APIRouter()
    @router.get('/api/strategy-roa/runtime-binding')
    def binding():
        from fastapi.responses import JSONResponse
        return JSONResponse(deepcopy(payload),headers={'Cache-Control':'no-store'})
    return router
