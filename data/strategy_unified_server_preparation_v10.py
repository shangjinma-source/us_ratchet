"""Optional display-only latest candles over the unchanged V9 advice runtime."""
from pathlib import Path
from fastapi import APIRouter
from core.strategy_account_ledger import require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v9 import build_unified_server_preparation_v9
from data.strategy_latest_display_charts_v1 import LatestDisplayChartsV1, monthly_display_context
from api.strategy_latest_display_charts_v1 import create_router

DISPLAY_SOURCES = {
    "data/strategy_latest_display_charts_v1.py",
    "api/strategy_latest_display_charts_v1.py",
    "data/strategy_unified_server_preparation_v10.py",
}


def attach_latest_display(*, prepared, root, validate_display_sources, fetch=None):
    def gate():
        prepared["validate_code"]()
        validate_display_sources()
    gate()
    monthly = prepared["monthly"]
    service = LatestDisplayChartsV1(
        context_reader=lambda sid: monthly_display_context(monthly, sid),
        validate_sources=gate, output_root=Path(root)/"data/strategy_display/latest_candles_v1",
        clock=monthly.clock, **({"fetch": fetch} if fetch is not None else {}))
    require(not any(r.path == "/api/strategy-display/latest-bars"
                    for r in prepared["router"].routes), "DISPLAY_ROUTE_DUPLICATE")
    router = APIRouter()
    router.routes.extend(prepared["router"].routes)
    router.include_router(create_router(service=service))
    gate()
    return dict(prepared, router=router, latest_display=service)


def build_unified_server_preparation_v10(*, root, configuration_path,
                                       configuration_sha256, clock=None):
    root = Path(root).absolute()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, config = _read(root, reference)
    require(set(config) == {"schema", "base_v9", "source_pins"}
            and config["schema"] == "LATEST_DISPLAY_UNIFIED_PREPARATION_V10",
            "DISPLAY_CONFIGURATION_FIELDS")
    require(type(config["source_pins"]) is dict
            and set(config["source_pins"]) == DISPLAY_SOURCES, "DISPLAY_SOURCE_SCOPE")
    executing = Path(__file__).resolve().parents[1]
    def gate():
        require(_read(root, reference)[0] == raw, "DISPLAY_CONFIGURATION_CHANGED")
        _read(root, config["base_v9"])
        for name, digest in config["source_pins"].items():
            require(_read_digest(root/name, 32*1024*1024) == digest
                    and _read_digest(executing/name, 32*1024*1024) == digest,
                    "DISPLAY_SOURCE_CHANGED")
    gate()
    prepared = build_unified_server_preparation_v9(root=root,
        configuration_path=config["base_v9"]["path"],
        configuration_sha256=config["base_v9"]["sha256"], clock=clock)
    return attach_latest_display(prepared=prepared, root=root,
                                 validate_display_sources=gate)
