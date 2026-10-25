"""Buy-data waiting projection; preserve verified sells and original signal."""
from copy import deepcopy

from core.strategy_account_difference import number, require, timestamp
from data.strategy_account_preview import preview_scoped_account
from data.strategy_daily_target_gate import resolve_daily_target
from data.strategy_daily_buy_data_wait_bridge_v1 import DailyBuyDataWaitExecutionBridge


def preview_buy_data_wait_mixed(*, account_store, target_store, signal_verifier,
                           execution_provider, validate_sources, policy_id,
                           clock, fee_bps, monthly_quantities, maximum_mark_age_seconds=120):
    """Keep the full authenticated target; execute only its sell subset.

    No cash inference or sale-proceeds financing. Open orders and unconfirmed
    cash retain the original gates; available cash is never changed.
    """
    validate_sources()
    state, target = deepcopy(account_store.read()), deepcopy(target_store.current())
    require(state is not None and target is not None, "ACCOUNT_AND_TARGET_REQUIRED")
    require(target["payload"]["account_id"] == state["account_id"], "TARGET_ACCOUNT_MISMATCH")
    # Called only after the buy minute-data adapter refused the current capture.
    require(state["cash_confirmation_valid"], "CASH_RECONFIRMATION_REQUIRED")
    now = clock()
    signal = signal_verifier(deepcopy(state), deepcopy(target), now)
    original_signal = deepcopy(signal)
    gate = resolve_daily_target(
        account_id=state["account_id"], account_revision=state["revision"],
        target_id=target["target_id"], target_month=target["payload"]["target_month"],
        monthly_quantities=deepcopy(monthly_quantities),
        strategy_shares=state["shares"], available_cash=state["available_cash"],
        pending_orders=[order for order in state["orders"].values() if order["status"] == "OPEN"],
        now=now.isoformat(), expected_policy_id=policy_id, signal=signal)

    def unchanged():
        validate_sources()
        require(account_store.read() == state, "ACCOUNT_CHANGED_DURING_PREVIEW")
        require(target_store.current() == target, "TARGET_CHANGED_DURING_PREVIEW")
        require(signal == original_signal, "DAILY_SIGNAL_MUTATED")

    unchanged()
    if gate["status"] != "DAILY_TARGET_READY" or any(
            row["reason"] == "PENDING_RECONCILIATION_REQUIRED" for row in gate["rows"]):
        return dict(status=gate["status"] if gate["status"] != "DAILY_TARGET_READY"
                    else "WAIT_PENDING_RECONCILIATION", daily_gate=gate,
                    new_orders=[], orders_created=False, account_mutated=False)
    effective = deepcopy(gate["effective_target_quantities"])
    held = state["shares"]
    waiting = [dict(security_id=sid, quantity=q-held.get(sid, 0),
                    reason="WAIT_BUY_MINUTE_DATA")
               for sid, q in sorted(effective.items()) if q > held.get(sid, 0)]
    projection = {sid: min(held.get(sid, 0), q) for sid, q in effective.items()}
    if not any(q < held.get(sid, 0) for sid, q in effective.items()):
        return dict(status="WAIT_EXECUTION_ELIGIBILITY" if waiting else "HOLD",
                    daily_gate=gate, effective_target_quantities=effective,
                    new_orders=[], waiting_data=waiting, orders_created=False, account_mutated=False)
    bridge = DailyBuyDataWaitExecutionBridge(base_target=target, execution_provider=execution_provider,
                                      validate_sources=validate_sources, signal=signal)
    evidence = bridge(deepcopy(state), effective, now, execution_quantities=projection)
    finished = clock()
    require(finished >= now, "SERVER_CLOCK_MOVED_BACKWARDS")
    require(timestamp(signal["valid_from"]) <= finished < timestamp(signal["valid_until"]),
            "DAILY_SIGNAL_EXPIRED_DURING_PREVIEW")
    for limit in evidence["limits"].values():
        require(finished < timestamp(limit["reference_valid_until"]), "REQUOTE_REQUIRED")
    result = preview_scoped_account(
        state=state, legacy_shares={}, target_quantities=projection,
        marks=evidence["marks"], limits=evidence["limits"], now=finished.isoformat(),
        maximum_mark_age_seconds=maximum_mark_age_seconds, fee_bps=fee_bps)
    require(all(order["side"] == "SELL" for order in result["new_orders"]),
            "DAILY_SELL_ONLY_VIOLATION")
    unchanged()
    return dict(status="CONDITIONAL_SELL_PREVIEW_BUYS_WAIT" if waiting else "CONDITIONAL_SELL_PREVIEW",
                daily_gate=gate, effective_target_quantities=effective,
                execution_quantities=projection, projection_semantics="EXECUTION_SUBSET_NOT_STRATEGY_TARGET",
                difference=result, new_orders=result["new_orders"], waiting_data=waiting,
                reference_quotes=evidence["limits"], execution_binding=bridge.last_binding,
                orders_created=False, account_mutated=False)
