"""Session-guarded publication around the frozen shared v6 composition."""
from hashlib import sha256
from pathlib import Path

from core.strategy_account_ledger import require
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from core.strategy_session_target_store_v1 import SessionGuardedTargetStoreV1
from data.strategy_account_runtime_archive import _document
from data.strategy_bounded_source_gate_v1 import _no_links
from data.strategy_unified_server_preparation_v6 import build_unified_server_preparation_v6
from scripts.register_quantity_v2_paper_protocol import safe_path

PUBLICATION_SOURCES = {
    "core/strategy_session_target_store_v1.py",
    "data/strategy_unified_server_preparation_v7.py",
}


def _read(root, reference):
    require(type(reference) is dict and set(reference) == {"path", "sha256"},
            "GUARDED_PREPARATION_REFERENCE")
    path = safe_path(root, reference["path"])
    _no_links(path)
    with path.open("rb") as stream:
        raw = stream.read(1024*1024+1)
    require(len(raw) <= 1024*1024 and sha256(raw).hexdigest() == reference["sha256"],
            "GUARDED_PREPARATION_CHANGED")
    return raw, _document(raw)


def bind_publication_guard(*, prepared, root, calendar):
    """Bind before any runtime enters the cache; never replace an active store."""
    root = Path(root).resolve()
    gate = prepared["validate_code"]
    expected = {name: sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()
                for name in PUBLICATION_SOURCES}
    gate.require_scope(expected)
    gate()
    _, document = _read(root, calendar)
    require(document.get("schema") == "FIXED_EXCHANGE_SESSIONS_V1"
            and document.get("exchange") == "NASDAQ"
            and type(document.get("sessions")) is list
            and bool(document["sessions"]), "GUARDED_PREPARATION_CALENDAR")
    monthly = prepared["monthly"]
    with monthly.lock:
        require(not monthly._runtimes, "PUBLICATION_GUARD_REQUIRES_COLD_RUNTIME")
        require(type(monthly.targets) is StrategyMonthlyTargetStore,
                "PUBLICATION_GUARD_STORE_ALREADY_CHANGED")
        guard = SessionGuardedTargetStoreV1(monthly.targets.path, root=root,
            calendar_path=calendar["path"], calendar_sha256=calendar["sha256"],
            clock=monthly.clock)
        monthly.targets = guard
    gate()
    return dict(prepared, publication_guard=guard, publication_calendar=dict(calendar))


def build_unified_server_preparation_v7(
        *, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).absolute()
    _no_links(root)
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, configuration = _read(root, reference)
    require(set(configuration) == {"schema", "base_v6", "publication_calendar"}
            and configuration["schema"] == "SESSION_GUARDED_UNIFIED_PREPARATION_V7",
            "GUARDED_PREPARATION_FIELDS")
    prepared = build_unified_server_preparation_v6(root=root,
        configuration_path=configuration["base_v6"]["path"],
        configuration_sha256=configuration["base_v6"]["sha256"], clock=clock)
    prepared = bind_publication_guard(
        prepared=prepared, root=root, calendar=configuration["publication_calendar"])
    require(_read(root, reference)[0] == raw, "GUARDED_PREPARATION_CHANGED")
    return prepared
