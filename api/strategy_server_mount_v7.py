"""Opt-in V28 startup; unchanged configurations retain the V6 mount path."""
from pathlib import Path
from fastapi.routing import APIRoute

from api import strategy_server_mount_v6 as previous
from data.strategy_unified_server_preparation_v7 import _read


def mount_strategy_routes(*, app, root, environment):
    root = Path(root)
    active, active_digest = previous._read_active(root)
    if previous.PATH_ENV in environment or previous.SHA_ENV in environment:
        reference = previous._reference(environment.get(previous.PATH_ENV),
                                        environment.get(previous.SHA_ENV))
        if active is not None and active != reference:
            raise ValueError('STRATEGY_ACTIVE_ENVIRONMENT_CONFLICT')
    else:
        reference = active
    if reference is None:
        return previous.mount_strategy_routes(app=app, root=root, environment=environment)
    path, digest = reference
    _, configuration = _read(root, dict(path=path, sha256=digest))
    if configuration.get('schema') != 'VERIFIED_REPLAY_UNIFIED_PREPARATION_V28':
        return previous.mount_strategy_routes(app=app, root=root, environment=environment)
    from data.strategy_unified_server_preparation_v28 import build_unified_server_preparation_v28
    prepared = build_unified_server_preparation_v28(root=root, configuration_path=path,
        configuration_sha256=digest)
    router = prepared['router']
    keys = {(route.path, method) for route in app.routes
            if hasattr(route, 'methods') for method in route.methods}
    for route in router.routes:
        if not isinstance(route, APIRoute):
            raise ValueError('STRATEGY_MOUNT_HTTP_ROUTE_REQUIRED')
        incoming = {(route.path, method) for method in route.methods}
        if keys.intersection(incoming):
            raise ValueError('STRATEGY_MOUNT_DUPLICATE_ROUTE')
        keys.update(incoming)
    if previous._read_active(root) != (active, active_digest):
        raise ValueError('STRATEGY_ACTIVE_MANIFEST_CHANGED_DURING_STARTUP')
    prepared['validate_code']()
    app.include_router(router)
    return {'mode': 'UNIFIED_V28', 'policy_approved_by_mount': False}
