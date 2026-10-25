"""Separate read-only production mount; execution policy is explicitly disabled."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from core.strategy_account_ledger import require
from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
from data.strategy_account_release_activation import MonthlyReleaseActivation
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from data.strategy_daily_evidence_adapter import SavedDailyEvidenceAdapter
from data.strategy_daily_live_adapter import StrategyDailyLiveAdapter
from api.strategy_daily_preview import create_router
from scripts.register_quantity_v2_paper_protocol import safe_path


def create_disabled_daily_router(*, root, configuration_path, configuration_sha256):
    root = Path(root).resolve()
    path = safe_path(root, configuration_path)
    require(path.resolve().is_relative_to(root), "DAILY_CONFIGURATION_OUTSIDE_ROOT")
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == configuration_sha256, "DAILY_CONFIGURATION_CHANGED")
    config = json.loads(raw)
    require(config["schema"] == "DAILY_PREVIEW_PRESENTATION_CONFIG_V1"
            and config["policy_execution_enabled"] is False
            and config["release_path"] is None, "DAILY_POLICY_DISABLED_REQUIRED")
    def code_gate():
        for name, expected in config["source_hashes"].items():
            require(sha256(safe_path(root, name).read_bytes()).hexdigest() == expected, "DAILY_SOURCE_CHANGED")
    code_gate()
    rolling = config["rolling_configuration"]
    rolling_raw = safe_path(root, rolling["path"]).read_bytes()
    require(sha256(rolling_raw).hexdigest() == rolling["sha256"], "DAILY_ROLLING_CONFIG_CHANGED")
    saved = json.loads(rolling_raw)
    gate = bind_dynamic_source_gate(root=root, source_pins=saved["source_pins"])
    initial = {key:saved[key] for key in ("registry_path", "registry_sha256", "archive_path", "archive_sha256")}
    clock = lambda: datetime.now(timezone.utc)
    activation = MonthlyReleaseActivation(root=root, initial_snapshot=initial, validate_code=gate, clock=clock)
    monthly = RollingMonthlyRuntimeRouter(root=root, initial_snapshot=dict(initial, revision=0),
        snapshot_provider=activation.snapshot, clock=clock,
        identity_configuration=saved.get("identity_configuration"), migration_control=saved.get("migration_control"))
    original_gate = monthly.validate_current_target_pins
    def validated():
        code_gate()
        gate()
        original_gate()
    monthly.validate_current_target_pins = validated
    reader = SavedDailyEvidenceAdapter(root=root)
    service = StrategyDailyLiveAdapter(monthly_service=monthly, evidence_reader=reader.verify,
                                      clock=clock, enabled=True)
    return create_router(service=service)
