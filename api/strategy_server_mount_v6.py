"""Explicit startup choice; never silently fall back after an opt-in failure."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re

from fastapi import APIRouter
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

PATH_ENV = "US_RATCHET_UNIFIED_V6_CONFIG_PATH"
SHA_ENV = "US_RATCHET_UNIFIED_V6_CONFIG_SHA256"
ACTIVE_MANIFEST = "config/strategy_server_active.json"
LEGACY_CONFIGURATIONS = (
    "config/strategy_account_rolling_20261019.json",
    "config/strategy_daily_preview_20261020_v2.json",
    "config/strategy_daily_v3_defaultoff_20261020.json",
    "config/strategy_capital_20261020_v2.json",
)


def _legacy_configuration_absent(root):
    """Only a wholly unconfigured checkout may use the read-only placeholder."""
    from data.strategy_bounded_source_gate_v1 import _no_links
    for name in LEGACY_CONFIGURATIONS:
        _no_links(root/name)
    return not any((root/name).exists() for name in LEGACY_CONFIGURATIONS)


def _unconfigured_router():
    router = APIRouter()

    async def unavailable():
        return JSONResponse(status_code=503, content={
            "status": "UNCONFIGURED",
            "detail": "策略账户尚未配置，请先完成本地部署。",
            "account": None,
            "orders_created": False,
            "account_mutated": False,
        })

    for prefix in ("/api/strategy-account", "/api/strategy-daily",
                   "/api/strategy-daily-v3", "/api/strategy-capital-v1",
                   "/api/strategy-capital-arrival-v2"):
        for path in (prefix, prefix+"/{unconfigured_path:path}"):
            for method in ("GET", "POST"):
                router.add_api_route(path, unavailable, methods=[method])
    return router


def _reference(path, digest):
    if (type(path) is not str or not path or path != path.strip()
            or "\\" in path or ":" in path or PurePosixPath(path).is_absolute()
            or any(part in ("", ".", "..") for part in path.split("/"))
            or not path.endswith(".json")
            or type(digest) is not str or not re.fullmatch("[0-9a-f]{64}", digest)):
        raise ValueError("UNIFIED_V6_EXPLICIT_CONFIGURATION_REQUIRED")
    return path, digest


def _read_active(root):
    """Read a fixed bounded local manifest; even dangling links are failures."""
    from data.strategy_bounded_source_gate_v1 import _no_links, _read_digest
    path = root/ACTIVE_MANIFEST
    _no_links(path)
    if not path.exists():
        return None, None
    digest = _read_digest(path, 4096)
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096 or sha256(raw).hexdigest() != digest:
        raise ValueError("STRATEGY_ACTIVE_MANIFEST_READ_RACE")
    if _read_digest(path, 4096) != digest:
        raise ValueError("STRATEGY_ACTIVE_MANIFEST_READ_RACE")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("STRATEGY_ACTIVE_MANIFEST_DUPLICATE_FIELD")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    if (type(value) is not dict or set(value) != {
            "schema", "configuration_path", "configuration_sha256"}
            or value["schema"] != "STRATEGY_SERVER_ACTIVE_V6"):
        raise ValueError("STRATEGY_ACTIVE_MANIFEST_FIELDS")
    return _reference(value["configuration_path"], value["configuration_sha256"]), digest


def mount_strategy_routes(*, app, root, environment):
    root = Path(root)
    active, active_digest = _read_active(root)
    configured = PATH_ENV in environment or SHA_ENV in environment
    if configured:
        reference = _reference(environment.get(PATH_ENV), environment.get(SHA_ENV))
        if active is not None and active != reference:
            raise ValueError("STRATEGY_ACTIVE_ENVIRONMENT_CONFLICT")
    else:
        reference = active
    if reference is not None:
        path, digest = reference
        from data.strategy_unified_server_preparation_v7 import _read
        _, configuration = _read(root, {"path": path, "sha256": digest})
        schema = configuration.get("schema")
        if schema == "UNIFIED_REVIEWED_DOMAIN_SERVER_PREPARATION_V6":
            from data.strategy_unified_server_preparation_v6 import build_unified_server_preparation_v6
            builder = build_unified_server_preparation_v6
        elif schema == "SESSION_GUARDED_UNIFIED_PREPARATION_V7":
            from data.strategy_unified_server_preparation_v7 import build_unified_server_preparation_v7
            builder = build_unified_server_preparation_v7
        elif schema == "OBSERVED_UNIFIED_PREPARATION_V8":
            from data.strategy_unified_server_preparation_v8 import build_unified_server_preparation_v8
            builder = build_unified_server_preparation_v8
        elif schema == "SNAPSHOT_VALUATION_UNIFIED_PREPARATION_V9":
            from data.strategy_unified_server_preparation_v9 import build_unified_server_preparation_v9
            builder = build_unified_server_preparation_v9
        elif schema == "LATEST_DISPLAY_UNIFIED_PREPARATION_V10":
            from data.strategy_unified_server_preparation_v10 import build_unified_server_preparation_v10
            builder = build_unified_server_preparation_v10
        elif schema == "CAPITAL_ARRIVAL_UNIFIED_PREPARATION_V11":
            from data.strategy_unified_server_preparation_v11 import build_unified_server_preparation_v11
            builder = build_unified_server_preparation_v11
        elif schema == "DAILY_RSS_UNIFIED_PREPARATION_V12":
            from data.strategy_unified_server_preparation_v12 import build_unified_server_preparation_v12
            builder = build_unified_server_preparation_v12
        elif schema == "DAILY_RSS_RECOVERY_UNIFIED_PREPARATION_V13":
            from data.strategy_unified_server_preparation_v13 import build_unified_server_preparation_v13
            builder = build_unified_server_preparation_v13
        elif schema == "DAILY_MARK_CLOCK_UNIFIED_PREPARATION_V14":
            from data.strategy_unified_server_preparation_v14 import build_unified_server_preparation_v14
            builder = build_unified_server_preparation_v14
        elif schema == "DAILY_RSS_ITEM_SCOPE_UNIFIED_PREPARATION_V15":
            from data.strategy_unified_server_preparation_v15 import build_unified_server_preparation_v15
            builder = build_unified_server_preparation_v15
        elif schema == "DAILY_BUY_DATA_WAIT_UNIFIED_PREPARATION_V16":
            from data.strategy_unified_server_preparation_v16 import build_unified_server_preparation_v16
            builder = build_unified_server_preparation_v16
        elif schema == "DAILY_SOURCE_ERROR_UNIFIED_PREPARATION_V17":
            from data.strategy_unified_server_preparation_v17 import build_unified_server_preparation_v17
            builder = build_unified_server_preparation_v17
        elif schema == "FOLLOWUP_COMPATIBLE_EPOCH_PREPARATION_V26":
            from data.strategy_unified_server_preparation_v26 import build_unified_server_preparation_v26
            builder = build_unified_server_preparation_v26
        elif schema == "COMPLETED_SELECTION_CLOSE_PREPARATION_V25":
            from data.strategy_unified_server_preparation_v25 import build_unified_server_preparation_v25
            builder = build_unified_server_preparation_v25
        elif schema == "RISK_HISTORY_CONTINUATION_PREPARATION_V24":
            from data.strategy_unified_server_preparation_v24 import build_unified_server_preparation_v24
            builder = build_unified_server_preparation_v24
        elif schema == "MONTHLY_SUPPLEMENT_UNIFIED_PREPARATION_V23":
            from data.strategy_unified_server_preparation_v23 import build_unified_server_preparation_v23
            builder = build_unified_server_preparation_v23
        elif schema == "CAP50_EXIT20_UNIFIED_PREPARATION_V22":
            from data.strategy_unified_server_preparation_v22 import build_unified_server_preparation_v22
            builder = build_unified_server_preparation_v22
        elif schema == "DAILY_EXPLANATIONS_UNIFIED_PREPARATION_V21":
            from data.strategy_unified_server_preparation_v21 import build_unified_server_preparation_v21
            builder = build_unified_server_preparation_v21
        elif schema == "HALT_AWARE_UNIFIED_PREPARATION_V20":
            from data.strategy_unified_server_preparation_v20 import build_unified_server_preparation_v20
            builder = build_unified_server_preparation_v20
        elif schema == "HALT_AWARE_UNIFIED_PREPARATION_V19":
            from data.strategy_unified_server_preparation_v19 import build_unified_server_preparation_v19
            builder = build_unified_server_preparation_v19
        else:
            raise ValueError("STRATEGY_ACTIVE_CONFIGURATION_SCHEMA")
        prepared = builder(
            root=root, configuration_path=path, configuration_sha256=digest)
        # The historical target-preview endpoint evaluates monthly difference
        # limits directly. V6 advice must pass the daily policy admission.
        # Keep the frozen shared factory intact; remove only this obsolete
        # executable-advice route from this explicitly selected startup branch.
        router = APIRouter()
        excluded = 0
        for route in prepared["router"].routes:
            if route.path == "/api/strategy-account/target/preview":
                if route.methods != {"POST"}:
                    raise ValueError("UNIFIED_V6_LEGACY_PREVIEW_ROUTE_CHANGED")
                excluded += 1
                continue
            router.routes.append(route)
        if excluded != 1:
            raise ValueError("UNIFIED_V6_LEGACY_PREVIEW_ROUTE_REQUIRED")
        mode = {
            "UNIFIED_REVIEWED_DOMAIN_SERVER_PREPARATION_V6": "UNIFIED_V6",
            "SESSION_GUARDED_UNIFIED_PREPARATION_V7": "UNIFIED_V7",
            "OBSERVED_UNIFIED_PREPARATION_V8": "UNIFIED_V8",
            "SNAPSHOT_VALUATION_UNIFIED_PREPARATION_V9": "UNIFIED_V9",
            "LATEST_DISPLAY_UNIFIED_PREPARATION_V10": "UNIFIED_V10",
            "CAPITAL_ARRIVAL_UNIFIED_PREPARATION_V11": "UNIFIED_V11",
            "DAILY_RSS_UNIFIED_PREPARATION_V12": "UNIFIED_V12",
            "DAILY_RSS_RECOVERY_UNIFIED_PREPARATION_V13": "UNIFIED_V13",
            "DAILY_MARK_CLOCK_UNIFIED_PREPARATION_V14": "UNIFIED_V14",
            "DAILY_RSS_ITEM_SCOPE_UNIFIED_PREPARATION_V15": "UNIFIED_V15",
            "DAILY_BUY_DATA_WAIT_UNIFIED_PREPARATION_V16": "UNIFIED_V16",
            "DAILY_SOURCE_ERROR_UNIFIED_PREPARATION_V17": "UNIFIED_V17",
            "HALT_AWARE_UNIFIED_PREPARATION_V19": "UNIFIED_V19",
            "HALT_AWARE_UNIFIED_PREPARATION_V20": "UNIFIED_V20",
            "DAILY_EXPLANATIONS_UNIFIED_PREPARATION_V21": "UNIFIED_V21",
            "CAP50_EXIT20_UNIFIED_PREPARATION_V22": "UNIFIED_V22",
            "MONTHLY_SUPPLEMENT_UNIFIED_PREPARATION_V23": "UNIFIED_V23",
            "RISK_HISTORY_CONTINUATION_PREPARATION_V24": "UNIFIED_V24",
            "COMPLETED_SELECTION_CLOSE_PREPARATION_V25": "UNIFIED_V25",
            "FOLLOWUP_COMPATIBLE_EPOCH_PREPARATION_V26": "UNIFIED_V26",
        }[schema]
    elif _legacy_configuration_absent(root):
        router = _unconfigured_router()
        mode = "UNCONFIGURED"
    else:
        # Exact prior startup compositions and pins. Build everything before
        # registering any route so a failed startup cannot mount a partial set.
        from api.strategy_rolling_composition import create_rolling_strategy_router
        from api.strategy_daily_composition import create_disabled_daily_router
        from api.strategy_daily_server_mount_v3 import create_disabled_daily_v3_router
        from api.strategy_capital_server_v1 import create_capital_router
        raw = (root/"config/strategy_account_rolling_20261019.json").read_bytes()
        if sha256(raw).hexdigest() != "b77880b641696380aa6c18edb0abcfd1dd700d2498b80b9b579a290cc2fd1061":
            raise ValueError("STRATEGY_DYNAMIC_CONFIGURATION_CHANGED")
        router = APIRouter()
        for child in (
            create_rolling_strategy_router(root=root, **json.loads(raw)),
            create_disabled_daily_router(root=root,
                configuration_path="config/strategy_daily_preview_20261020_v2.json",
                configuration_sha256="c93efb85691e1ec0a2078e3f093493c222176ead24159fcbf2742d455888f0f8"),
            create_disabled_daily_v3_router(root=root,
                configuration_path="config/strategy_daily_v3_defaultoff_20261020.json",
                configuration_sha256="701d770e100a6b27b6b6ee7adf5d11579cf78b97bb8fb714b456d5984b162d2a"),
            create_capital_router(root=root,
                configuration_path="config/strategy_capital_20261020_v2.json",
                configuration_sha256="8e0f2a25e61a240c93c0de3d3e1967dfcd948927a98730b9c81b948fc67f165e"),
        ):
            router.include_router(child)
        mode = "LEGACY"
    keys = {(route.path, method) for route in app.routes
            if hasattr(route, "methods") for method in route.methods}
    for route in router.routes:
        if not isinstance(route, APIRoute):
            raise ValueError("STRATEGY_MOUNT_HTTP_ROUTE_REQUIRED")
        incoming = {(route.path, method) for method in route.methods}
        if keys.intersection(incoming):
            raise ValueError("STRATEGY_MOUNT_DUPLICATE_ROUTE")
        keys.update(incoming)
    # Detect removal, creation or replacement while the actual builders ran.
    if _read_active(root) != (active, active_digest):
        raise ValueError("STRATEGY_ACTIVE_MANIFEST_CHANGED_DURING_STARTUP")
    app.include_router(router)
    return {"mode": mode, "policy_approved_by_mount": False}
