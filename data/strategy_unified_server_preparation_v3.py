"""Pinned server preparation for the explicit existing-account upgrade.

Returns an unmounted router. Does not select, publish, approve, or schedule.
"""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from core.strategy_account_ledger import require
from data.strategy_account_runtime_archive import _document
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from data.strategy_profiled_server_preparation import build_preparation
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from data.strategy_continuous32_upgrade_handoff import upgrade_handoff_snapshot_provider
from api.strategy_unified_rolling_composition_v3 import (
    SOURCES as ROUTER_SOURCES, create_unified_rolling_strategy_router_v3,
)
from scripts.register_quantity_v2_paper_protocol import safe_path

SOURCES = ROUTER_SOURCES | {"data/strategy_unified_server_preparation_v3.py"}


def build_unified_server_preparation_v3(
        *, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).resolve()

    def read(reference):
        with safe_path(root, reference["path"]).open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024
                and sha256(raw).hexdigest() == reference["sha256"],
                "UNIFIED_SERVER_CONFIGURATION_CHANGED")
        return raw, _document(raw)

    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, configuration = read(reference)
    require(set(configuration) == {
        "schema", "purpose", "preparation", "upgrade", "legacy_ui_configuration",
        "daily_configuration", "source_pins"
    } and configuration["schema"] == "UNIFIED_ROLLING_SERVER_PREPARATION_V3"
        and configuration["purpose"] == "EXPLICIT_EXISTING_ACCOUNT_PROFILE_UPGRADE",
        "UNIFIED_SERVER_CONFIGURATION_FIELDS")
    require(SOURCES <= set(configuration["source_pins"]), "UNIFIED_SERVER_SOURCE_SCOPE")
    code_gate = bind_dynamic_source_gate(
        root=root, source_pins=configuration["source_pins"])
    clock = clock or (lambda: datetime.now(timezone.utc))
    preparation_ref = configuration["preparation"]
    prepared = build_preparation(
        root=root, configuration_path=preparation_ref["path"],
        configuration_sha256=preparation_ref["sha256"], clock=clock)

    def gate():
        require(read(reference)[0] == raw, "UNIFIED_SERVER_CONFIGURATION_CHANGED")
        code_gate()
        prepared["validate_code"]()
        read(configuration["legacy_ui_configuration"])
        read(configuration["upgrade"])
        read(configuration["daily_configuration"])

    gate()
    _, legacy = read(configuration["legacy_ui_configuration"])
    _, daily = read(configuration["daily_configuration"])
    # The saved upgrade package replaces only the legacy migration-generation
    # mechanism; preserve actual identity and chart sources from its UI config.
    snapshot = upgrade_handoff_snapshot_provider(
        root=root, package_path=configuration["upgrade"]["path"],
        package_sha256=configuration["upgrade"]["sha256"],
        base_provider=prepared["activation"].snapshot,
        target_provider=prepared["router"].targets.current,
        validate_code=gate,
    )
    monthly = ProfiledRollingMonthlyRuntimeRouter(
        root=root, initial_snapshot=snapshot(), snapshot_provider=snapshot,
        clock=clock, identity_configuration=legacy.get("identity_configuration"),
    )
    require(monthly.accounts.read() is not None and monthly.current() is not None,
            "UNIFIED_EXISTING_ACCOUNT_AND_TARGET_REQUIRED")
    router = create_unified_rolling_strategy_router_v3(
        monthly=monthly, validate_code=gate,
        source_pins=configuration["source_pins"], clock=clock,
        daily_configuration=daily,
        bootstrap_configuration=legacy.get("bootstrap_configuration"),
        display_sources=legacy.get("display_sources"),
    )
    gate()
    return dict(router=router, monthly=monthly, validate_code=gate,
                activation=prepared["activation"], production_mounted=False)
