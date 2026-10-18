"""Research-only dynamic identities: freeze lots at Close, attempt next Open.

No fill-time resizing, retry, dividends, implicit ticker/split inference, or live
integration. Ticker changes fail closed: this version has no independently
validated price-identity interval bridge, even for caller-declared rename events.
Risk labels are last-known decision observations, not verified validity intervals.
"""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import numpy as np

from backtest import ndx_dynamic_whole_lot_path as identity
from backtest import ndx_dynamic_whole_lot_repair_path as repair
from backtest import ndx_whole_lot_repair_diagnostic as projector
from backtest import ndx_split_accounting_research as split

_SOURCE_PATHS = [Path(__file__), *(Path(module.__file__) for module in
    (identity, repair, projector, split))]
_LOADED_SOURCES = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in _SOURCE_PATHS}
_RISK_KEYS = ('max_single_weight', 'min_single_weight', 'top_weight_cap',
              'minimum_effective_n_ratio', 'risk_chain_top1_cap')


def _check_sources():
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
           for path, digest in _LOADED_SOURCES.items()):
        raise ValueError('Loaded execution source drift')


def _mark(frame, date, ticker):
    raw = frame.at[date, ticker]
    if isinstance(raw, (bool, np.bool_)):
        raise ValueError('Boolean price')
    return identity._price_at(frame, date, ticker)


def _cash_projection(cash, before, after, marks, fee_rate):
    delta = {key: after.get(key, 0) - before.get(key, 0)
             for key in sorted(set(before) | set(after))}
    buy = sum(value * marks[key] for key, value in delta.items() if value > 0)
    sell = sum(-value * marks[key] for key, value in delta.items() if value < 0)
    fees = (buy + sell) * fee_rate
    result = cash + sell - buy - fees
    if not all(math.isfinite(value) for value in (buy, sell, fees, result)):
        raise ValueError('Nonfinite account arithmetic')
    return result, buy, sell, fees, delta


def simulate_dynamic_frozen_execution_research(*, closes, opens, schedule,
        risk_chains_by_decision, corporate_actions, initial_cash_usd,
        minimum_cash_buffer_usd, valuation_end_date, transaction_cost_bps=10.,
        max_single_weight=.45, min_single_weight=.05, top_weight_cap=.80,
        minimum_effective_n_ratio=.70, risk_chain_top1_cap=.55,
        max_repair_evaluations=262144, identity_events=()):
    """Return JSON-compatible account traces from an initially all-cash account.

    corporate_actions is a list of exact split event dicts keyed security_id
    (session/new_shares/old_shares/source_url/evidence_sha256). Events cancel
    pending baskets before Open; fractional reverse splits raise, never round.
    Risk checks at Open reject the entire frozen basket; they do not resize it.
    identity_events is reserved for a future price-identity interval contract;
    only an explicit empty list/tuple is accepted. A source URL/digest alone
    cannot prove that two ticker price channels represent the same security.
    """
    _check_sources()
    repair._strict_price_index(closes, 'closes')
    repair._strict_price_index(opens, 'opens')
    if not closes.index.equals(opens.index):
        raise ValueError('Open and Close must share the exact session calendar')
    rows = deepcopy(list(schedule))
    for row in rows:
        repair._strict_session_date(row['decision_date'], 'decision_date')
        repair._strict_session_date(row['execution_date'], 'execution_date')
        for security, target in row['targets'].items():
            for value in (security, target['issuer_id'], target['ticker']):
                if type(value) is not str or not value or value != value.strip():
                    raise ValueError('Canonical identity required')
            if target['ticker'] != target['ticker'].upper():
                raise ValueError('Canonical ticker required')
            repair._finite(target['target_weight'], 'target_weight')
    items = identity._normalise_schedule(rows)
    identity._validate_schedule_identity_and_execution_guards(items,
        valuation_prices=closes, separate_execution_prices_supplied=True,
        require_separate_execution_prices=True, require_next_session_execution=True,
        require_issuer_trace=True)
    contract = repair._normalise_contract(items,
        risk_chains_by_decision=risk_chains_by_decision,
        initial_cash_usd=initial_cash_usd, minimum_cash_buffer_usd=minimum_cash_buffer_usd,
        transaction_cost_bps=transaction_cost_bps, max_single_weight=max_single_weight,
        min_single_weight=min_single_weight, top_weight_cap=top_weight_cap,
        minimum_effective_n_ratio=minimum_effective_n_ratio,
        risk_chain_top1_cap=risk_chain_top1_cap, max_repair_evaluations=max_repair_evaluations)
    risk_arguments = {key: contract[key] for key in _RISK_KEYS}
    end = repair._strict_session_date(valuation_end_date, 'valuation_end_date')
    start = items[0]['decision_date']
    if start not in closes.index or end not in closes.index or end < items[-1]['execution_date']:
        raise ValueError('Invalid explicit execution interval')
    if any(item['decision_date'] not in closes.index for item in items):
        raise ValueError('Decision Close session missing')
    if type(corporate_actions) not in (list, tuple):
        raise ValueError('Explicit corporate action list required')
    identities = {security for item in items for security in item['targets']}
    if type(identity_events) not in (list, tuple):
        raise ValueError('Explicit identity event list required')
    if identity_events:
        raise ValueError('Ticker identity events unsupported without verified price-identity intervals')
    observed_tickers = {}
    for item in items:
        for key, target in item['targets'].items():
            if key in observed_tickers and observed_tickers[key] != target['ticker']:
                raise ValueError('Ticker changes unsupported without verified price-identity intervals')
            observed_tickers[key] = target['ticker']
    events_by_date = {}
    for event in corporate_actions:
        if type(event) is not dict or set(event) != {
                'security_id', 'session', 'new_shares', 'old_shares', 'source_url', 'evidence_sha256'}:
            raise ValueError('Exact security split schema required')
        date = repair._strict_session_date(event['session'], 'split session')
        if date not in closes.index or not start <= date <= end or event['security_id'] not in identities:
            raise ValueError('Split outside identity/calendar interval')
        adapted = {('ticker' if key == 'security_id' else key): value for key, value in event.items()}
        events_by_date.setdefault(date, []).append(adapted)
    for date, events in events_by_date.items():
        split.apply_split_session(session=date.date().isoformat(), shares={key: 0 for key in identities},
            cash_usd=contract['initial_cash_usd'], pending_plan=None, events=events)
    cash, buffer = contract['initial_cash_usd'], contract['minimum_cash_buffer_usd']
    fee_rate = contract['transaction_cost_bps'] / 10000.
    shares, labels, chains, chain_dates = {}, {}, {}, {}
    decisions, executions, trades, daily, action_trace = [], [], [], [], []
    pending = None
    by_decision = {item['decision_date']: item for item in items}

    def risk(counts, marks):
        if not counts:
            return {'all_passed': False, 'checks': {'ALL_CASH': False}}
        return repair._risk_snapshot(counts, marks, {key: chains[key] for key in counts}, **risk_arguments)

    for date in closes.loc[start:end].index:
        session = date.date().isoformat()
        aliases = []
        active_ids = set(shares) | (set(pending['desired_shares']) if pending is not None else set())
        if len({labels[key]['ticker'] for key in active_ids}) != len(active_ids):
            raise ValueError('Identity events create a concurrent ticker collision')
        if date in events_by_date:
            action = split.apply_split_session(session=session,
                shares={key: shares.get(key, 0) for key in identities}, cash_usd=cash,
                pending_plan=pending, events=events_by_date[date])
            shares = {key: value for key, value in action['shares'].items() if value}
            if action['cancelled_plan'] is not None:
                executions.append(dict(session=session, status='CANCELLED_SPLIT',
                    decision_date=pending['decision_date'], plan=deepcopy(pending)))
            pending = action['pending_plan']
            action_trace.append(action)
        if pending is not None and pending['execution_date'] == session:
            plan = pending
            pending = None
            wanted = plan['desired_shares']
            marks = {key: _mark(opens, date, labels[key]['ticker']) for key in set(shares) | set(wanted)}
            after_cash, buy, sell, fees, delta = _cash_projection(cash, shares, wanted, marks, fee_rate)
            snapshot = risk(wanted, {key: marks[key] for key in wanted})
            failures = [key for key, passed in snapshot['checks'].items() if not passed]
            if after_cash < buffer - 1e-8:
                failures.append('CASH_BUFFER')
            record = dict(session=session, decision_date=plan['decision_date'],
                status='REJECTED' if failures else 'FILLED', failure_reasons=failures,
                frozen_delta=deepcopy(plan['delta']), desired_shares=deepcopy(wanted),
                prices=marks, shares_before=deepcopy(shares), cash_before_usd=cash,
                projected_cash_usd=after_cash, projected_fees_usd=fees, risk=snapshot)
            if delta != plan['delta']:
                raise ValueError('Frozen delta changed without cancellation')
            if not failures:
                pre_equity = cash + sum(shares[key] * marks[key] for key in shares)
                post_equity = after_cash + sum(wanted[key] * marks[key] for key in wanted)
                error = abs(post_equity - pre_equity + fees)
                if error > identity._amount_tolerance(post_equity, pre_equity, fees):
                    raise ValueError('Self-financing identity failed')
                for key, quantity in delta.items():
                    if quantity:
                        trades.append(dict(session=session, security_id=key, ticker=labels[key]['ticker'],
                            share_delta=quantity, price_usd=marks[key],
                            transaction_cost_usd=abs(quantity) * marks[key] * fee_rate))
                cash, shares = after_cash, deepcopy(wanted)
                record['accounting_error_usd'] = error
            record.update(cash_after_usd=cash, shares_after=deepcopy(shares))
            executions.append(record)
        if date in by_decision:
            item = by_decision[date]
            targets = item['targets']
            for key, target in targets.items():
                if key in labels and labels[key]['ticker'] != target['ticker']:
                    raise ValueError('Ticker changes unsupported without verified price-identity intervals')
                labels[key] = dict(ticker=target['ticker'], issuer_id=target['issuer_id'])
                chains[key] = contract['risk_chains_by_decision'][session][key]
                chain_dates[key] = session
            if len({labels[key]['ticker'] for key in set(shares) | set(targets)}) != len(set(shares) | set(targets)):
                raise ValueError('Concurrent identities share a ticker')
            # Issuer uniqueness applies to each target basket (validated above),
            # not to the pre/post union: a genuine share-class replacement must
            # sell the old security and buy the new security, not be prohibited.
            marks = {key: _mark(closes, date, labels[key]['ticker']) for key in set(shares) | set(targets)}
            investable = cash + sum(shares[key] * marks[key] for key in shares) - buffer
            if not math.isfinite(investable) or investable <= 0:
                raise ValueError('No investable capital')
            wanted = {key: math.floor(investable * target['target_weight'] / marks[key])
                      for key, target in targets.items()}
            after_cash, *_ = _cash_projection(cash, shares, wanted, marks, fee_rate)
            while all(value >= 1 for value in wanted.values()) and after_cash < buffer - 1e-8:
                reducible = [key for key, value in wanted.items() if value > 1]
                if not reducible:
                    break
                wanted[max(reducible, key=lambda key: (marks[key], key))] -= 1
                after_cash, *_ = _cash_projection(cash, shares, wanted, marks, fee_rate)
            snapshot = risk(wanted, {key: marks[key] for key in wanted})
            projection = None
            if after_cash < buffer - 1e-8 or not snapshot['all_passed']:
                removed_sell = sum(shares[key] * marks[key] for key in set(shares) - set(targets))
                projection = projector.project_whole_lot_rebalance(
                    current_shares={key: shares.get(key, 0) for key in targets},
                    current_cash_usd=cash + removed_sell * (1 - fee_rate),
                    prices={key: marks[key] for key in targets},
                    target_weights={key: target['target_weight'] for key, target in targets.items()},
                    risk_chain_by_ticker={key: chains[key] for key in targets},
                    minimum_cash_buffer_usd=buffer, transaction_cost_bps=contract['transaction_cost_bps'],
                    max_evaluations=contract['max_repair_evaluations'], **risk_arguments)
                if projection['search_complete'] and projection['feasible_projection_found']:
                    wanted = dict(projection['projected_shares'])
                else:
                    wanted = None
            record = dict(decision_date=session, execution_date=item['execution_date'].date().isoformat(),
                target_k=len(targets), targets=deepcopy(targets), aliases=aliases,
                shares_before=deepcopy(shares), prices=marks, cash_before_usd=cash,
                risk_chains={key: chains[key] for key in marks},
                risk_chain_observation_dates={key: chain_dates[key] for key in marks},
                projection=projection, status='NO_PLAN' if wanted is None else 'FROZEN')
            if wanted is not None:
                after_cash, buy, sell, fees, delta = _cash_projection(cash, shares, wanted, marks, fee_rate)
                snapshot = risk(wanted, {key: marks[key] for key in wanted})
                if after_cash < buffer - 1e-8 or not snapshot['all_passed']:
                    raise ValueError('Decision projection violated strict constraints')
                record.update(desired_shares=wanted, delta=delta, decision_risk=snapshot,
                              projected_cash_usd=after_cash, projected_fees_usd=fees)
                pending = deepcopy(record)
            decisions.append(record)
        marks = {key: _mark(closes, date, labels[key]['ticker']) for key in shares}
        daily.append(dict(session=session, cash_usd=cash, shares=deepcopy(shares), prices=marks,
            tickers={key: labels[key]['ticker'] for key in shares},
            total_value_usd=cash + sum(shares[key] * marks[key] for key in shares),
            risk=risk(shares, marks), risk_chains={key: chains[key] for key in shares},
            risk_chain_observation_dates={key: chain_dates[key] for key in shares}))
    _check_sources()
    values = [row['total_value_usd'] for row in daily]
    peak, drawdown = contract['initial_cash_usd'], 0.
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    return dict(schema='ndx_dynamic_frozen_execution_research_v2', decisions=decisions,
        executions=executions, trades=trades, daily=daily, corporate_actions=action_trace,
        identity_events=[],
        summary=dict(terminal_value_usd=values[-1], path_return_net=values[-1] / contract['initial_cash_usd'] - 1,
            path_max_drawdown=drawdown, session_count=len(daily),
            all_cash_session_count=sum(not row['shares'] for row in daily),
            k_path=[row['target_k'] for row in decisions]),
        source_hashes=dict(_LOADED_SOURCES), portfolio_track='portfolio_optimization',
        execution_policy='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET',
        auto_replan_enabled=False, risk_label_policy='LAST_KNOWN_DECISION_OBSERVATION',
        alias_policy='UNSUPPORTED_FAIL_CLOSED_REQUIRES_PRICE_IDENTITY_INTERVAL_CONTRACT',
        identity_event_source_authenticity_verified=False,
        source_authenticity_verified=False, point_in_time_verified=False,
        corporate_action_coverage_verified=False, dividend_modelled=False,
        broker_atomic_execution_verified=False, promotion_allowed=False)
