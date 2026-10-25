"""Pinned server preparation for the explicit existing-account upgrade.

Returns an unmounted router. Does not select, publish, approve, or schedule.
"""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from core.strategy_account_ledger import require
from data.strategy_account_runtime_archive import _document
from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1, _no_links
from data.strategy_profiled_server_preparation import SOURCES as PREPARATION_SOURCES
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from data.strategy_continuous32_upgrade_handoff import upgrade_handoff_snapshot_provider
from api.strategy_unified_domain_composition_v5 import (
    SOURCES as ROUTER_SOURCES, create_unified_domain_strategy_router_v5,
)
from scripts.register_quantity_v2_paper_protocol import safe_path

SOURCES = ROUTER_SOURCES | PREPARATION_SOURCES | {"data/strategy_unified_server_preparation_v3.py", "data/strategy_unified_server_preparation_v4.py", "data/strategy_unified_server_preparation_v5.py"}


def build_unified_server_preparation_v5(
        *, root, configuration_path, configuration_sha256, clock=None):
    _no_links(Path(root).absolute())
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
    } and configuration["schema"] == "UNIFIED_DOMAIN_SERVER_PREPARATION_V5"
        and configuration["purpose"] == "EXPLICIT_EXISTING_ACCOUNT_PROFILE_UPGRADE",
        "UNIFIED_SERVER_CONFIGURATION_FIELDS")
    require(SOURCES <= set(configuration["source_pins"]), "UNIFIED_SERVER_SOURCE_SCOPE")
    clock = clock or (lambda: datetime.now(timezone.utc))
    preparation_raw, preparation = read(configuration["preparation"])
    require(set(preparation) == {"schema", "initial_snapshot", "source_pins", "legacy_anchor"}
            and preparation["schema"] == "PROFILED_SERVER_PREPARATION_V2", "PROFILE_SERVER_FIELDS")
    require(PREPARATION_SOURCES <= set(preparation["source_pins"]), "PROFILE_SERVER_SOURCE_SCOPE")
    # One uncached union replaces repeatedly nested checks of overlapping domains.
    pins = dict(configuration["source_pins"])
    for name, digest in preparation["source_pins"].items():
        require(name not in pins or pins[name] == digest, "UNIFIED_SERVER_SOURCE_CONFLICT")
        pins[name] = digest
    references = [reference] + [configuration[key] for key in
        ("preparation", "legacy_ui_configuration", "upgrade", "daily_configuration")]
    configurations = {}
    for ref in references:
        require(ref["path"] not in configurations or configurations[ref["path"]] == ref["sha256"],
                "UNIFIED_SERVER_REFERENCE_CONFLICT")
        read(ref)
        configurations[ref["path"]] = ref["sha256"]
    gate = BoundedSourceGateV1(root=root, source_pins=pins, configuration_pins=configurations)
    activation = ProfiledMonthlyReleaseActivation(root=root,
        initial_snapshot=preparation["initial_snapshot"], validate_code=gate,
        legacy_anchor=preparation["legacy_anchor"], clock=clock)
    # This store is read lazily; no target initialization or generation occurs.
    from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
    targets = StrategyMonthlyTargetStore(root/"data/strategy_account/monthly_targets.sqlite3")
    _, legacy = read(configuration["legacy_ui_configuration"])
    _, daily = read(configuration["daily_configuration"])
    # The saved upgrade package replaces only the legacy migration-generation
    # mechanism; preserve actual identity and chart sources from its UI config.
    snapshot = upgrade_handoff_snapshot_provider(
        root=root, package_path=configuration["upgrade"]["path"],
        package_sha256=configuration["upgrade"]["sha256"],
        base_provider=activation.snapshot,
        target_provider=targets.current,
        validate_code=gate,
    )
    monthly = ProfiledRollingMonthlyRuntimeRouter(
        root=root, initial_snapshot=snapshot(), snapshot_provider=snapshot,
        clock=clock, identity_configuration=legacy.get("identity_configuration"),
    )
    require(monthly.accounts.read() is not None and monthly.current() is not None,
            "UNIFIED_EXISTING_ACCOUNT_AND_TARGET_REQUIRED")
    router = create_unified_domain_strategy_router_v5(
        monthly=monthly, validate_code=gate,
        source_pins=configuration["source_pins"], clock=clock,
        daily_configuration=daily,
        bootstrap_configuration=legacy.get("bootstrap_configuration"),
        display_sources=legacy.get("display_sources"),
    )
    gate()
    return dict(router=router, monthly=monthly, validate_code=gate,
                activation=activation, production_mounted=False)
