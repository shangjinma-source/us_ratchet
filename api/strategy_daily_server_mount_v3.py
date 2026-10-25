"""Explicit default-off v3 mounting factory; importing this module mounts nothing."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from core.strategy_account_ledger import require
from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
from data.strategy_account_release_activation import MonthlyReleaseActivation
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
from data.strategy_daily_rolling_admission_v3 import RollingDailyAdmissionV3
from api.strategy_daily_preview_v3 import create_router
from scripts.register_quantity_v2_paper_protocol import safe_path


DAILY_SOURCES = {
    "api/strategy_daily_server_mount_v3.py","api/strategy_daily_preview_v3.py",
    "data/strategy_daily_rolling_admission_v3.py","data/strategy_daily_composition_v3.py",
    "data/strategy_daily_rebinding_reader.py","data/strategy_daily_rebound_archive.py",
    "data/strategy_daily_evidence_rebind.py","data/strategy_daily_evidence_adapter.py",
    "data/strategy_daily_signal_verifier.py","data/strategy_daily_preview_service.py",
    "data/strategy_daily_target_gate.py","data/strategy_daily_execution_bridge.py",
    "data/strategy_daily_mixed_preview.py","data/strategy_daily_mixed_execution_bridge.py",
}


def create_disabled_daily_v3_router(*, root, configuration_path, configuration_sha256):
    root = Path(root).resolve()
    path = safe_path(root, configuration_path)
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == configuration_sha256, "DAILY_CONFIGURATION_CHANGED")
    config = json.loads(raw)
    require(config["schema"] == "DAILY_V3_SERVER_ADMISSION_V1"
            and config["policy_execution_enabled"] is False
            and config["evidence"]["release_path"] is None
            and config["evidence"]["trusted_release_sha256"] is None,
            "DAILY_POLICY_DISABLED_REQUIRED")
    require(set(config["source_hashes"]) == DAILY_SOURCES, "DAILY_SOURCE_DOMAIN_REQUIRED")

    def code_gate():
        require(path.read_bytes() == raw, "DAILY_CONFIGURATION_CHANGED")
        for name, expected in config["source_hashes"].items():
            require(sha256(safe_path(root,name).read_bytes()).hexdigest() == expected, "DAILY_SOURCE_CHANGED")

    code_gate()
    rolling = config["rolling_configuration"]
    rolling_raw = safe_path(root,rolling["path"]).read_bytes()
    require(sha256(rolling_raw).hexdigest() == rolling["sha256"], "DAILY_ROLLING_CONFIG_CHANGED")
    saved = json.loads(rolling_raw)
    underlying_gate = bind_dynamic_source_gate(root=root,source_pins=saved["source_pins"])
    def gate():
        code_gate()
        require(safe_path(root,rolling["path"]).read_bytes() == rolling_raw, "DAILY_ROLLING_CONFIG_CHANGED")
        underlying_gate()
    initial={k:saved[k] for k in ("registry_path","registry_sha256","archive_path","archive_sha256")}
    clock=lambda:datetime.now(timezone.utc)
    activation=MonthlyReleaseActivation(root=root,initial_snapshot=initial,validate_code=gate,clock=clock)
    monthly=RollingMonthlyRuntimeRouter(root=root,initial_snapshot=dict(initial,revision=0),
        snapshot_provider=activation.snapshot,clock=clock,identity_configuration=saved.get("identity_configuration"),
        migration_control=saved.get("migration_control"))
    evidence=dict(config["evidence"])
    evidence["archive_root"]=safe_path(root,evidence["archive_root"])
    reader=ArchivedRebindingDailyEvidenceReader(root=root,**evidence)
    service=RollingDailyAdmissionV3(monthly=monthly,reader=reader,clock=clock,validate_code=gate,
                                  policy_execution_enabled=False)
    return create_router(service=service)
