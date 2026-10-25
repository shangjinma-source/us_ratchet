"""Bind a future daily policy release to its actual monthly selector.

This check neither approves a policy nor replaces the daily evidence verifier.
Call it before collecting execution quotes or writing execution cap records.
"""
from hashlib import sha256
import json

from core.strategy_account_ledger import canonical, require
from data.strategy_continuous32_target_decision import PROFILE_ID, VERSION, validate_result


def validate_daily_profile_binding(*, release_bytes, trusted_release_sha256, target):
    require(type(release_bytes) is bytes and len(release_bytes) <= 1024 * 1024,
            "PROFILE_RELEASE_BYTES_REQUIRED")
    require(sha256(release_bytes).hexdigest() == trusted_release_sha256,
            "PROFILE_RELEASE_HASH_MISMATCH")

    def unique_fields(items):
        result = {}
        for key, value in items:
            require(key not in result, "PROFILE_RELEASE_DUPLICATE_FIELD")
            result[key] = value
        return result

    release = json.loads(release_bytes, object_pairs_hook=unique_fields,
                         parse_constant=lambda value: (_ for _ in ()).throw(
                             ValueError("PROFILE_RELEASE_INVALID_NUMBER")))
    require(type(release) is dict and release.get("schema") == "SERVER_DAILY_POLICY_RELEASE_V1"
            and release.get("approved") is True, "PROFILE_RELEASE_NOT_APPROVED")
    require(release.get("selector_profile") == PROFILE_ID
            and release.get("selection_method") == VERSION
            and type(release.get("continuous_iterations")) is int
            and release["continuous_iterations"] == 32,
            "DAILY_RELEASE_SELECTOR_PROFILE_REQUIRED")
    require(type(target) is dict and type(target.get("payload")) is dict,
            "DAILY_PROFILE_TARGET_REQUIRED")
    payload = target["payload"]
    require(payload.get("schema") == "REAL_STRATEGY_MONTHLY_TARGET_V1",
            "DAILY_PROFILE_TARGET_SCHEMA")
    require(sha256(canonical(payload)).hexdigest() == target.get("target_id"),
            "DAILY_PROFILE_TARGET_HASH_MISMATCH")
    decision = payload["decision"]
    require(decision.get("status") == "TARGET_READY"
            and sha256(canonical(decision["payload"])).hexdigest() == decision.get("decision_id"),
            "DAILY_PROFILE_DECISION_MISMATCH")
    binding = decision["payload"]["input_binding"]
    require(sha256(canonical(binding)).hexdigest() == decision["payload"].get("input_id"),
            "DAILY_PROFILE_INPUT_MISMATCH")
    require(payload.get("account_id") == binding.get("account_id")
            and type(payload.get("account_id")) is str and bool(payload["account_id"]),
            "DAILY_PROFILE_ACCOUNT_MISMATCH")
    require(payload.get("target_quantities") == decision["payload"]["target_quantities"],
            "DAILY_PROFILE_PUBLISHED_QUANTITIES_MISMATCH")
    require(binding.get("selector_profile") == PROFILE_ID
            and binding.get("selection_method") == VERSION
            and type(binding.get("continuous_iterations")) is int
            and binding["continuous_iterations"] == 32,
            "DAILY_TARGET_SELECTOR_PROFILE_MISMATCH")
    require(validate_result(decision["payload"]["search_result"], binding["search_arguments"])
            == decision["payload"]["target_quantities"],
            "DAILY_PROFILE_TARGET_QUANTITIES_MISMATCH")
    return {"selector_profile": PROFILE_ID, "target_id": target["target_id"],
            "policy_release_sha256": trusted_release_sha256}
