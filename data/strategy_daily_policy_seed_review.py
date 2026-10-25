"""Explicit first-policy evidence review; never approves or publishes a policy.

An already approved, server-pinned release and independently pinned reviewed
evidence are required. Existing evidence bytes are retained unchanged.
"""
from copy import deepcopy
from hashlib import sha256

from core.strategy_account_ledger import canonical, require
from core.strategy_account_difference import timestamp
from data.strategy_daily_profile_binding import validate_daily_profile_binding
from data.strategy_daily_evidence_rebind import rebind_reviewed_daily_evidence
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle


def review_initial_policy_seed(
        *, state, target, now, event_id, release_bytes, trusted_release_sha256,
        receipt_bytes, trusted_receipt_sha256, files, calendar_bytes):
    require(type(event_id) is str and 0 < len(event_id) <= 128,
            "EXPLICIT_POLICY_REVIEW_EVENT_REQUIRED")
    validate_daily_profile_binding(
        release_bytes=release_bytes, trusted_release_sha256=trusted_release_sha256,
        target=target,
    )
    rebound = rebind_reviewed_daily_evidence(
        receipt_bytes=receipt_bytes, trusted_receipt_sha256=trusted_receipt_sha256,
        files=files, state=state, target=target, now=now,
    )
    if rebound["receipt"] is None:
        return dict(status=rebound["status"], receipt=None, files=None, published=False)
    receipt = deepcopy(rebound["receipt"])
    require(receipt.get("release_sha256") is None, "INITIAL_POLICY_REVIEW_REQUIRES_UNBOUND_SEED")
    current = timestamp(now)
    session = receipt["execution_session"]
    if not timestamp(session["open"]) <= current < timestamp(session["close"]):
        return dict(status="WAIT_POLICY_REVIEW_SESSION", receipt=None, files=None,
                    published=False)
    # Rebinding supplied the actual review time, not a new price capture time.
    receipt["release_sha256"] = trusted_release_sha256
    receipt["policy_binding_review"] = dict(
        schema="INITIAL_POLICY_SEED_REVIEW_V1", event_id=event_id,
        reviewed_at=current.isoformat(), release_sha256=trusted_release_sha256,
        original_receipt_sha256=trusted_receipt_sha256,
        semantics="EXPLICIT_REVIEW_NOT_NEW_MARKET_CAPTURE",
    )
    raw = canonical(receipt)
    verified = verify_daily_signal_bundle(
        state=state, target=target, now=now,
        release_bytes=release_bytes, trusted_release_sha256=trusted_release_sha256,
        receipt_bytes=raw, trusted_receipt_sha256=sha256(raw).hexdigest(),
        files=rebound["files"], calendar_bytes=calendar_bytes,
    )
    require(verified["status"] == "DAILY_SIGNAL_READY", "POLICY_SEED_FULL_VERIFICATION_REQUIRED")
    return dict(
        status="POLICY_BOUND_SEED_REVIEW_READY_NOT_PUBLISHED",
        receipt=receipt, receipt_sha256=sha256(raw).hexdigest(),
        files=rebound["files"], release_sha256=trusted_release_sha256,
        source_received_at=receipt["source_received_at"],
        published=False, policy_approved=False, account_mutated=False,
    )
