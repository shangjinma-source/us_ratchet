"""Independent complete V4 actual-result reconstruction for true V3/V4/V5 parents.

No project imports or IO. Host adapters must pin the injected parent inspector,
CSV checker and frozen independent formula before using this function. The API
name adapter below never changes the original parent envelope or its schema.
"""
from datetime import datetime, timedelta
import json
from types import SimpleNamespace

DEPENDENCY_SHA256 = {
    "parent_view": "32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373",
    "csv_reader": "c9dbb1c15c12d84910842874d1800d09c73d90893b91d54865826bf240ef9787",
    "independent_formula": "6a17d3ad5758ff72feeaa653088b3b94819d5096b5ec005690351a6981917e0f",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def exact(left, right, message):
    require(encode(left) == encode(right), message)


def utc(value):
    require(type(value) is str, "Explicit original capture clock")
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), "Original zero-offset UTC")
    return parsed


def reconstruct_compact_actual(*, parent, observation, blobs, parent_checker, csv_rows, independent_formula):
    """Return the entire unchanged V4 history using independent append arithmetic.

    Shared parent declarations do not authenticate the source or clocks. Every
    original byte, receipt and ancestor namespace still needs IO verification.
    """
    view = parent_checker.inspect_parent_history_v5(parent)
    payload = observation["payload"]
    session = payload["session"]
    suffix = view["pending_source_sessions"] + view["excluded_not_completed_source_sessions"]
    require(not suffix or [item["session"] for item in suffix] == [session],
        "Every original unconsumed session must be this one actual candidate")
    if view["parent_schema"] == "PROSPECTIVE_GAP_EXTENSION_HISTORY_V5":
        for role in ("payload", "receipt", "audit"):
            exact(observation[role].get("actual_parent_schema"), view["parent_schema"], "True V5 parent association")
            exact(observation[role].get("writer_adapter_schema"), "REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5",
                "Actual observation adapter association")
        start = utc(payload["capture_started_at_utc"])
        require(all(start >= utc(item["capture_completed_at_utc"]) for item in suffix),
            "Original suffix capture clock cannot regress")
    for ticker in ("QQQ", "SPY"):
        source = payload["full_original_sources_preserved"][ticker]["sources"]
        raw = blobs[source["reference"]["path"]]
        rows, _ = csv_rows(raw, view["known_typed_rows"][0]["session"])
        exact(payload["selected_original_rows"][ticker], rows[-1], "Independent original selected row")
        exact(payload["source_row_locations"][ticker],
            dict(original_data_row_index=len(rows) - 1, reference=source["reference"]),
            "Independent original source row location")
    inspector = SimpleNamespace(inspect_parent_history_v4=parent_checker.inspect_parent_history_v5)
    return independent_formula.reconstruct_history(parent=parent, observation=observation,
        parent_checker=inspector, csv_rows=csv_rows, blobs=blobs)
