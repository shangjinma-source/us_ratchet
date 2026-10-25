"""Explicit complete-domain policy binding in memory; no approval or publication."""
from copy import deepcopy
from hashlib import sha256
import json

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_profile_binding import validate_daily_profile_binding
from data.strategy_daily_security_domain_v1 import aggregate_security_packets
from data.strategy_daily_session_capture import stamp
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle


def review_domain_policy(*, state, target, now, event_id, domain, packets,
                         release_bytes, trusted_release_sha256, calendar_bytes):
    """Bind an already approved policy only after reviewing the whole source domain.

    Individual packets remain available for future continuity. The caller must
    separately publish this result in a create-only transaction and pin it.
    """
    require(type(event_id) is str and 0 < len(event_id) <= 128,
            "EXPLICIT_DOMAIN_POLICY_EVENT_REQUIRED")
    validate_daily_profile_binding(release_bytes=release_bytes,
        trusted_release_sha256=trusted_release_sha256, target=target)
    current = stamp(now)
    original = aggregate_security_packets(domain=domain, packets=packets,
                                          state=state, target=target, now=current.isoformat())
    if original.get("receipt") is None:
        return dict(status=original["status"], receipt=None, packets=None, published=False)
    session = original["receipt"]["execution_session"]
    if not stamp(session["open"]) <= current < stamp(session["close"]):
        return dict(status="WAIT_POLICY_REVIEW_SESSION", receipt=None, packets=None,
                    published=False)
    bound = {}
    for sid, packet in packets.items():
        receipt = json.loads(packet["receipt_bytes"])
        require(receipt.get("release_sha256") is None,
                "INITIAL_DOMAIN_POLICY_REQUIRES_UNBOUND_PACKETS")
        files = deepcopy(packet["files"])
        original_hash = packet["trusted_receipt_sha256"]
        name = "policy-originals/"+original_hash+".json"
        require(name not in files or files[name] == packet["receipt_bytes"],
                "DOMAIN_POLICY_ORIGINAL_CONFLICT")
        files[name] = packet["receipt_bytes"]
        receipt.update(
            release_sha256=trusted_release_sha256,
            available_at=current.isoformat(),
            valid_from=max(current, stamp(session["open"])).isoformat(),
            source_sha256={path: sha256(raw).hexdigest() for path, raw in files.items()},
            policy_binding_review=dict(
                schema="INITIAL_DOMAIN_POLICY_REVIEW_V1", event_id=event_id,
                security_id=sid, reviewed_at=current.isoformat(),
                release_sha256=trusted_release_sha256,
                original_receipt_sha256=original_hash,
                semantics="EXPLICIT_REVIEW_NOT_NEW_MARKET_CAPTURE"))
        raw = canonical(receipt)
        bound[sid] = dict(receipt_bytes=raw, trusted_receipt_sha256=sha256(raw).hexdigest(),
                          files=files)
    combined = aggregate_security_packets(domain=domain, packets=bound, state=state,
                                          target=target, now=current.isoformat())
    require(combined.get("receipt") is not None, "DOMAIN_POLICY_AGGREGATE_REQUIRED")
    raw = canonical(combined["receipt"])
    verified = verify_daily_signal_bundle(
        state=state, target=target, now=current.isoformat(),
        release_bytes=release_bytes, trusted_release_sha256=trusted_release_sha256,
        receipt_bytes=raw, trusted_receipt_sha256=sha256(raw).hexdigest(),
        files=combined["files"], calendar_bytes=calendar_bytes)
    require(verified["status"] == "DAILY_SIGNAL_READY", "DOMAIN_POLICY_FULL_VERIFICATION_REQUIRED")
    return dict(status="DOMAIN_POLICY_REVIEW_READY_NOT_PUBLISHED",
                receipt=combined["receipt"], files=combined["files"], packets=bound,
                receipt_sha256=sha256(raw).hexdigest(),
                original_aggregate_sha256=sha256(canonical(original["receipt"])).hexdigest(),
                release_sha256=trusted_release_sha256, published=False,
                policy_approved=False, account_mutated=False)
