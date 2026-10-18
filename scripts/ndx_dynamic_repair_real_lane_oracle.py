"""Read-only independent accounting audit of one frozen historical repair lane.

This is not a portfolio optimizer, admission decision, or order generator.
The execution engine is the subject under test; Fraction accounting and the
32-point neighborhood oracle do not call its projection implementation.
"""
from fractions import Fraction
from itertools import product
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import scripts.ndx_dynamic_walkforward as walkforward
from backtest.ndx_dynamic_whole_lot_repair_path import (
    simulate_dynamic_security_id_conditional_repair_path,
)

BASE = ROOT / "data/cache/research/ndx_dynamic_walkforward_v1"
LANE = BASE / "ndx_cardinality_real_runner_p2_exact_v3/technology_plus_adjacent/drawdown"
INDEX_SHA256 = "1111ecf65b5d824c2844e857cac41e04b17ce48f23d553f8203e5d9afdb4d603"
MANIFEST_SHA256 = "b1b86ad649f141c680046b4064973c20064de9e720ec4a37716eb4f2d7716f6c"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fraction(value):
    return Fraction(str(value))


def verify_hash(path, expected):
    require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected,
            f"Source hash mismatch: {path}")


def load_inputs():
    manifest_bytes = (BASE / "manifest.json").read_bytes()
    require(hashlib.sha256(manifest_bytes).hexdigest() == MANIFEST_SHA256,
            "Frozen input authority manifest changed")
    manifest = json.loads(manifest_bytes)
    for name in ("runner_script", "config", "capital_replay_manifest", "execution_price_manifest"):
        record = manifest["inputs"][name]
        verify_hash(record["path"], record["sha256"])
    verify_hash(BASE / "artifact_index.csv", INDEX_SHA256)
    index = pd.read_csv(BASE / "artifact_index.csv")
    require(len(index) == 119, "Frozen artifact count changed")
    for record in index.to_dict("records"):
        verify_hash(record["path"], record["sha256"])
    candidates, _ = walkforward._load_completed_replay_candidates(json.loads(
        Path(manifest["inputs"]["capital_replay_manifest"]["path"]).read_text(encoding="utf-8")))
    candidates["selection_date"] = pd.to_datetime(candidates["selection_date"])
    candidates = candidates[candidates.selection_date <= pd.Timestamp(manifest["valuation_end"])]
    tickers = set(walkforward.ORIGINAL_8) | {
        ticker for values in candidates.tickers for ticker in values.split(";")
    }
    opens, closes = walkforward._load_execution_and_valuation_prices(
        Path(manifest["inputs"]["execution_price_manifest"]["path"]), tickers)
    selected = pd.read_csv(LANE / "selected_candidates.csv")
    require(len(selected) == 14, "Frozen decision count changed")
    risk_chains = {}
    for record in selected.to_dict("records"):
        source = candidates[
            (candidates.source_batch == record["source_batch"])
            & (candidates.universe_track == record["universe_track"])
            & (candidates.portfolio_id == record["portfolio_id"])
            & (candidates.selection_date == pd.Timestamp(record["selection_date"]))]
        require(len(source) == 1, "Selected source must be unique")
        for name in ("security_ids", "issuer_ids", "risk_chains", "tickers", "weights"):
            require(source.iloc[0][name] == record[name], f"Selected provenance mismatch: {name}")
        identities = record["security_ids"].split(";")
        chains = record["risk_chains"].split(";")
        require(len(identities) == len(chains) == len(set(identities)), "Ambiguous risk mapping")
        require(record["decision_data_end"] not in risk_chains, "Duplicate decision")
        risk_chains[record["decision_data_end"]] = dict(zip(identities, chains))
    return manifest, selected, risk_chains, opens, closes


def audit_accounting(result, opens, closes):
    expected_dates = closes.loc["2023-04-03":"2024-05-31"].index
    require(pd.DatetimeIndex(pd.to_datetime(result["path"]["date"])).equals(expected_dates),
            "Audit must cover the complete frozen daily calendar")
    cash, fees = Fraction(25000), Fraction(0)
    shares, values = {}, [cash]
    cash_error = nav_error = 0.0
    trade_count = 0
    snapshots = {}
    for row in result["path"].to_dict("records"):
        day = row["date"]
        for trade in result["trades"][result["trades"].execution_date == day].to_dict("records"):
            security = trade["security_id"]
            delta = int(trade["share_delta"])
            require(delta == trade["share_delta"], "Fractional trade")
            require(shares.get(security, 0) == trade["shares_before"], "Pretrade shares mismatch")
            require(trade["event_type"] == "ECONOMIC_TRADE", "Frozen lane event type changed")
            price = fraction(opens.at[pd.Timestamp(day), trade["trade_ticker"]])
            notional = abs(delta) * price
            fee = notional / 1000
            for expected, actual in ((price, trade["price_usd"]),
                                     (notional, trade["notional_usd"]),
                                     (fee, trade["transaction_cost_usd"])):
                require(abs(float(expected) - actual) < 1e-8, "Trade price/notional/fee mismatch")
            cash -= delta * price + fee
            fees += fee
            trade_count += 1
            shares[security] = shares.get(security, 0) + delta
            require(shares[security] >= 0 and shares[security] == trade["shares_after"],
                    "Posttrade shares mismatch")
        holdings = json.loads(row["holdings"])
        require({key: value for key, value in shares.items() if value}
                == {key: value["shares"] for key, value in holdings.items()}, "Daily holdings mismatch")
        nav = cash + sum(fraction(closes.at[pd.Timestamp(day), holding["ticker"]]) * shares[key]
                         for key, holding in holdings.items())
        values.append(nav)
        cash_error = max(cash_error, abs(float(cash) - row["cash_usd"]))
        nav_error = max(nav_error, abs(float(nav) - row["total_value_usd"]))
        require(cash >= 100, "Cash buffer breached")
        snapshots[day] = (cash, holdings)
    peak, drawdown = values[0], Fraction(0)
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    require(cash_error < 1e-7 and nav_error < 1e-7, "Daily accounting mismatch")
    require(abs(float(fees) - result["summary"]["total_transaction_cost_usd"]) < 1e-7,
            "Total fee mismatch")
    require(abs(float(drawdown) - result["summary"]["path_max_drawdown"]) < 1e-12,
            "Drawdown mismatch")
    require(abs(float(values[-1] / 25000 - 1) - result["summary"]["path_return_net"]) < 1e-12,
            "Return mismatch")
    require(len(values) - 1 == 293 and trade_count == 81, "Frozen path coverage changed")
    require(trade_count == len(result["trades"]), "Unconsumed trades outside the daily path")
    return dict(days=293, economic_trades=trade_count, terminal_value_usd=float(values[-1]),
                transaction_cost_usd=float(fees), path_return_net=float(values[-1] / 25000 - 1),
                max_drawdown=float(drawdown), max_cash_error_usd=cash_error,
                max_nav_error_usd=nav_error), snapshots


def audit_neighborhood(selected, opens, snapshots):
    cash, prior = snapshots["2024-04-30"]
    row = selected.iloc[-1]
    require(row.decision_data_end == "2024-04-30", "Repair decision changed")
    identities, tickers = row.security_ids.split(";"), row.tickers.split(";")
    chains = dict(zip(identities, row.risk_chains.split(";")))
    ticker_weights = {name: fraction(value) for name, value in
                      (item.split(":") for item in row.weights.split(";"))}
    weights = {key: ticker_weights[ticker] for key, ticker in zip(identities, tickers)}
    weight_sum = sum(weights.values())
    weights = {key: value / weight_sum for key, value in weights.items()}
    symbols = {key: value["ticker"] for key, value in prior.items()}
    symbols.update(dict(zip(identities, tickers)))
    marks = {key: fraction(opens.at[pd.Timestamp("2024-05-01"), ticker])
             for key, ticker in symbols.items()}
    removed = sum(prior[key]["shares"] * marks[key] for key in prior if key not in identities)
    cash += removed * Fraction(999, 1000)
    equity = cash + sum(prior.get(key, {}).get("shares", 0) * marks[key] for key in identities)
    identities = sorted(identities)
    options = [tuple(sorted({math.floor((equity - 100) * weights[key] / marks[key]),
                             math.ceil((equity - 100) * weights[key] / marks[key])}))
               for key in identities]
    feasible = []
    for quantities in product(*options):
        holdings = dict(zip(identities, quantities))
        invested = sum(holdings[key] * marks[key] for key in identities)
        actual = {key: holdings[key] * marks[key] / invested for key in identities}
        ordered = sorted(actual.values(), reverse=True)
        turnover = sum(abs(holdings[key] - prior.get(key, {}).get("shares", 0)) * marks[key]
                       for key in identities)
        postcash = cash - sum((holdings[key] - prior.get(key, {}).get("shares", 0)) * marks[key]
                              for key in identities) - turnover / 1000
        chain_weights = {}
        for key, weight in actual.items():
            chain_weights[chains[key]] = chain_weights.get(chains[key], Fraction(0)) + weight
        if (min(quantities) < 1 or postcash < 100 or min(ordered) < Fraction(5, 100)
                or max(ordered) > Fraction(45, 100) or sum(ordered[:3]) > Fraction(80, 100)
                or 1 / sum(value * value for value in ordered) < Fraction(35, 10)
                or max(chain_weights.values()) > Fraction(55, 100)):
            continue
        score = (sum(abs(actual[key] - weights[key]) for key in identities),
                 max(abs(actual[key] - weights[key]) for key in identities), turnover, quantities)
        feasible.append((score, holdings, postcash, sum(ordered[:3])))
    feasible.sort()
    require(math.prod(map(len, options)) == 32 and len(feasible) == 6, "Neighborhood changed")
    best = feasible[0]
    actual_cash, actual_holdings = snapshots["2024-05-01"]
    require(best[1] == {key: value["shares"] for key, value in actual_holdings.items()},
            "Engine shares differ from independent best neighbor")
    require(abs(float(best[2] - actual_cash)) < 1e-8, "Repair cash mismatch")
    require(len(prior) == 9 and len(actual_holdings) == 5, "Composition transition changed")
    return dict(independent_search_space=32, feasible_neighbors=6,
                best_shares={symbols[key]: value for key, value in best[1].items()},
                posttrade_cash_usd=float(best[2]), top3_weight=float(best[3]),
                forced_exit_notional_usd=float(removed), forced_exit_fee_usd=float(removed / 1000))


def main():
    manifest, selected, risk_chains, opens, closes = load_inputs()
    result = simulate_dynamic_security_id_conditional_repair_path(
        closes, walkforward.build_dynamic_policy_schedule(selected), execution_prices=opens,
        require_separate_execution_prices=True, require_next_session_execution=True,
        require_issuer_trace=True, risk_chains_by_decision=risk_chains,
        initial_cash_usd=25000., minimum_cash_buffer_usd=100., transaction_cost_bps=10.,
        valuation_end_date=manifest["valuation_end"])
    require(result["status"] == "COMPLETE_WITH_CONDITIONAL_REPAIR", "Expected repaired path")
    require(len(result["repair_events"]) == 1, "Repair event count changed")
    event = result["repair_events"].iloc[0]
    require(event["execution_date"] == "2024-05-01"
            and json.loads(event["trigger_reasons"]) == ["SECURITY_TOP3_WEIGHT"], "Repair event changed")
    accounting, snapshots = audit_accounting(result, opens, closes)
    print(json.dumps(dict(status="INDEPENDENT_FROZEN_LANE_ORACLE_PASS", research_only=True,
                          portfolio_optimizer=False, admission_allowed=False,
                          source_artifacts_verified=119, selected_decisions_verified=14,
                          accounting=accounting,
                          neighborhood=audit_neighborhood(selected, opens, snapshots)), sort_keys=True))


if __name__ == "__main__":
    main()
