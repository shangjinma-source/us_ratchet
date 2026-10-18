"""Bounded buy-only cash forks. No prices, identities or dates are certified here.

Risk semantics follow ndx_dynamic_whole_lot_repair_path._risk_snapshot:
positive holdings, invested-stock denominator, top THREE securities, effective
N >= ratio * positive holding count and risk-chain TOP ONE; tolerance 1e-9.
Fraction comparisons deliberately avoid inheriting caller Decimal/float error.
This is not bitwise reproduction of the frozen float engine or an optimizer.
"""
from datetime import date
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from math import prod


SCHEMA = "CONDITIONAL_NEW_CASH_BOUNDED_FORK_V1"
RISK_KEYS = ("max_single_weight", "min_single_weight", "top_weight_cap",
             "minimum_effective_n_ratio", "risk_chain_top1_cap")
CHECKS = ("MAX_SINGLE_WEIGHT", "MIN_SINGLE_WEIGHT", "SECURITY_TOP3_WEIGHT",
          "MINIMUM_EFFECTIVE_N", "RISK_CHAIN_TOP1_WEIGHT")
MAX_EVALUATIONS = 10000
# Engineering memory/output guard, never an eligible-universe or portfolio-k cap.
MAX_SECURITIES = 256
MAX_BRANCHES = 32
MAX_SHARES = 10**12
TOLERANCE = Fraction(1, 10**9)


def _identifier(value):
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError("Nonblank canonical string identifier required")
    return value


def _integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("Bounded nonnegative integer required; bool is invalid")
    return value


def _number(value):
    if type(value) not in (str, int, Decimal):
        raise ValueError("Use exact Decimal, decimal string or int, never float/bool")
    if type(value) is str and (not value or len(value) > 80 or value.strip() != value):
        raise ValueError("Bounded decimal literal required")
    if type(value) is int and abs(value) > 10**40:
        raise ValueError("Integer magnitude exceeds decimal resource limit")
    try:
        with localcontext(Context(prec=160)):
            result = Decimal(value)
    except Exception as error:
        raise ValueError("Invalid decimal") from error
    if (not result.is_finite() or len(result.as_tuple().digits) > 40
            or abs(result.as_tuple().exponent) > 40 or abs(result) > Decimal("1e40")):
        raise ValueError("Decimal outside finite bounded precision/exponent contract")
    return result


def _day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Canonical YYYY-MM-DD required")
    return value


def _risk(shares, prices, securities, parameters):
    amounts = {sid: Fraction(prices[sid]) * count for sid, count in sorted(shares.items()) if count}
    total = sum(amounts.values(), Fraction(0))
    if not total:
        return {"checks": dict.fromkeys(CHECKS, False), "all_passed": False,
                "reason": "ALL_CASH", "positive_holding_count": 0,
                "weights": {}, "effective_n": None}
    weights = {sid: amount / total for sid, amount in amounts.items()}
    ordered = sorted(weights.values(), reverse=True)
    effective_n = 1 / sum((weight * weight for weight in weights.values()), Fraction(0))
    chains = {}
    for sid, weight in weights.items():
        chain = securities[sid]["risk_chain"]
        chains[chain] = chains.get(chain, Fraction(0)) + weight
    passed = (ordered[0] <= parameters["max_single_weight"] + TOLERANCE,
              ordered[-1] >= parameters["min_single_weight"] - TOLERANCE,
              sum(ordered[:3]) <= parameters["top_weight_cap"] + TOLERANCE,
              effective_n >= parameters["minimum_effective_n_ratio"] * len(weights) - TOLERANCE,
              max(chains.values()) <= parameters["risk_chain_top1_cap"] + TOLERANCE)
    # Fractions are exact evidence strings, not rounded classification inputs.
    return {"checks": dict(zip(CHECKS, passed)), "all_passed": all(passed),
            "reason": None, "positive_holding_count": len(weights),
            "weights": {sid: str(weight) for sid, weight in weights.items()},
            "effective_n": str(effective_n)}


def _issuer_conflicts(shares, securities):
    groups = {}
    for sid, count in sorted(shares.items()):
        if count:
            groups.setdefault(securities[sid]["issuer_id"], []).append(sid)
    return {issuer: sids for issuer, sids in sorted(groups.items()) if len(sids) > 1}


def evaluate_branches(*, cash_event, starting_cash_usd, holdings, securities,
                      execution_prices, branches, risk_parameters,
                      transaction_cost_bps, minimum_cash_buffer_usd,
                      max_evaluations):
    """Evaluate a prefix of each explicitly bounded buy-quantity Cartesian domain.

    max_evaluations is one GLOBAL budget, allocated in supplied branch order.
    Within each branch sorted SID quantities run lexicographically, zero first.
    An exhausted domain says nothing about quantities outside its supplied caps.
    Execution prices are explicit scenario marks; no calendar/gap model implied.
    """
    with localcontext(Context(prec=160)):
        return _evaluate(cash_event=cash_event, starting_cash_usd=starting_cash_usd,
                         holdings=holdings, securities=securities,
                         execution_prices=execution_prices, branches=branches,
                         risk_parameters=risk_parameters, transaction_cost_bps=transaction_cost_bps,
                         minimum_cash_buffer_usd=minimum_cash_buffer_usd,
                         max_evaluations=max_evaluations)


def _evaluate(**inputs):
    event = inputs["cash_event"]
    if type(event) is not dict or set(event) != {"decision_date", "execution_date", "amount_usd"}:
        raise ValueError("Explicit cash event required")
    decision, execution = _day(event["decision_date"]), _day(event["execution_date"])
    if execution <= decision:
        raise ValueError("Execution must follow decision; exchange adjacency is not certified")
    amount, cash = _number(event["amount_usd"]), _number(inputs["starting_cash_usd"])
    buffer, fee_bps = _number(inputs["minimum_cash_buffer_usd"]), _number(inputs["transaction_cost_bps"])
    if min(amount, cash, buffer, fee_bps) < 0 or fee_bps > 10000:
        raise ValueError("Nonnegative cash/buffer/fee required; fee <= 10000bps")
    budget = _integer(inputs["max_evaluations"], MAX_EVALUATIONS)
    holdings, securities, prices = inputs["holdings"], inputs["securities"], inputs["execution_prices"]
    if any(type(value) is not dict for value in (holdings, securities, prices)):
        raise ValueError("Explicit SID mappings required")
    if len(holdings) > MAX_SECURITIES:
        raise ValueError("Too many holdings")
    base = {_identifier(sid): _integer(count, MAX_SHARES) for sid, count in holdings.items()}
    branches = inputs["branches"]
    if type(branches) is not list or not 1 <= len(branches) <= MAX_BRANCHES:
        raise ValueError("Bounded nonempty branches list required")
    prepared, seen, union = [], set(), set(base)
    for branch in branches:
        if type(branch) is not dict or set(branch) != {"branch_id", "buy_limits"}:
            raise ValueError("Branch requires ID and explicit buy limits")
        name = _identifier(branch["branch_id"])
        if name in seen or type(branch["buy_limits"]) is not dict or len(branch["buy_limits"]) > MAX_SECURITIES:
            raise ValueError("Duplicate branch or invalid limits")
        seen.add(name)
        limits = {_identifier(sid): _integer(limit, MAX_SHARES) for sid, limit in branch["buy_limits"].items()}
        if any(base.get(sid, 0) + limit > MAX_SHARES for sid, limit in limits.items()):
            raise ValueError("Final share cap exceeds resource limit")
        union.update(limits)
        prepared.append((name, dict(sorted(limits.items()))))
    if len(union) > MAX_SECURITIES or set(securities) != union or set(prices) != union:
        raise ValueError("Exact complete old-holdings/buy-union metadata and prices required")
    marks = {sid: _number(prices[sid]) for sid in sorted(union)}
    if any(value <= 0 for value in marks.values()):
        raise ValueError("Positive union prices required")
    for row in securities.values():
        if type(row) is not dict or set(row) != {"issuer_id", "risk_chain"}:
            raise ValueError("Explicit issuer and risk chain required")
        _identifier(row["issuer_id"])
        _identifier(row["risk_chain"])
    params = inputs["risk_parameters"]
    if type(params) is not dict or set(params) != set(RISK_KEYS):
        raise ValueError("Exact five risk parameters required")
    parameters = {key: Fraction(_number(params[key])) for key in RISK_KEYS}
    if any(not 0 < value <= 1 for value in parameters.values()) or parameters["min_single_weight"] > parameters["max_single_weight"]:
        raise ValueError("Risk parameters outside (0,1] or inverted min/max")
    initial = cash + sum((marks[sid] * count for sid, count in base.items()), Decimal(0))
    results, evaluated = [], 0
    for name, limits in prepared:
        sids = list(limits)
        denominator = prod(limit + 1 for limit in limits.values())
        count = min(denominator, budget - evaluated)
        rows = []
        for rank in range(count):
            remainder, buys = rank, {}
            for sid in reversed(sids):
                remainder, buys[sid] = divmod(remainder, limits[sid] + 1)
            buys = dict(sorted(buys.items()))
            after = dict(base)
            for sid, quantity in buys.items():
                after[sid] = after.get(sid, 0) + quantity
            gross = sum((marks[sid] * quantity for sid, quantity in buys.items()), Decimal(0))
            fees = gross * fee_bps / Decimal(10000)
            remaining = cash + amount - gross - fees
            risk = _risk(after, marks, securities, parameters)
            conflicts = _issuer_conflicts(after, securities)
            financial = {"NONNEGATIVE_CASH": remaining >= 0, "CASH_BUFFER": remaining >= buffer}
            ending = remaining + sum((marks[sid] * quantity for sid, quantity in after.items()), Decimal(0))
            rows.append({"rank": rank, "buy_shares": buys, "proposed_holdings": dict(sorted(after.items())),
                         "gross_buy_usd": str(gross), "fees_usd": str(fees), "cash_after_usd": str(remaining),
                         "equity_after_usd": str(ending), "cash_flow_adjusted_pnl_usd": str(ending - initial - amount),
                         "financial_checks": financial, "risk": risk,
                         "issuer_conflicts": conflicts, "issuer_unique": not conflicts,
                         "feasible": all(financial.values()) and risk["all_passed"] and not conflicts})
        evaluated += count
        results.append({"branch_id": name, "buy_limits": limits, "candidate_count": denominator,
                        "evaluated_count": count, "unevaluated_count": denominator - count,
                        "status": "EXHAUSTED_SUPPLIED_DOMAIN" if count == denominator else "BUDGET_LIMITED",
                        "feasible_evaluated_count": sum(row["feasible"] for row in rows), "candidates": rows})
    return {"schema": SCHEMA, "cash_event": {"decision_date": decision, "execution_date": execution, "amount_usd": str(amount)},
            "starting_cash_usd": str(cash), "starting_holdings": dict(sorted(base.items())),
            "initial_equity_usd": str(initial), "risk_parameters": {key: str(value) for key, value in parameters.items()},
            "transaction_cost_bps": str(fee_bps), "minimum_cash_buffer_usd": str(buffer),
            "baseline_risk": _risk(base, marks, securities, parameters),
            "baseline_issuer_conflicts": _issuer_conflicts(base, securities),
            "candidate_count": sum(row["candidate_count"] for row in results), "evaluated_count": evaluated,
            "branches": results, "order_version": "INPUT_BRANCH_ORDER_SORTED_SID_QUANTITY_LEX_V1",
            "risk_denominator": "POSITIVE_INVESTED_STOCK_ONLY_CASH_CHECKED_SEPARATELY",
            "risk_arithmetic": "EXACT_RATIONAL_ORIGINAL_1E_MINUS_9_TOLERANCE_NOT_FLOAT_BITWISE",
            "risk_tolerance": "1e-9", "global_optimality_claimed": False,
            "parameter_authority": "SYNTHETIC_CALLER_SUPPLIED_NOT_SOURCE_BOUND",
            "security_resource_cap": MAX_SECURITIES,
            "security_resource_cap_is_eligibility_or_k_limit": False,
            "cash_event_timing": "BEFORE_EXECUTION_MARK_BUYS_NO_INTERVENING_MARK_MODEL",
            "full_integer_space_infeasibility_claimed": False, "orders_executed": False,
            "point_in_time_verified": False, "promotion_allowed": False,
            "historical_experiment_executed": False, "return_series_calculated": False,
            "time_series_return_evaluated": False}
