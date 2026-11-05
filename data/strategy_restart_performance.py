"""Pure restart performance for a ledger-reconciled epoch without external flows.
No account writes. Ledger/quote authenticity is the caller's responsibility.
Trades are reconciled by replay; external cash flows are never inferred.
"""
from fractions import Fraction as F
from datetime import datetime
from core.strategy_account_ledger import replay


def _time(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('AWARE_TIME_REQUIRED')
    return result


def _positions(rows):
    result = {}
    for row in rows:
        sid, quantity = row['security_id'], row['quantity']
        if sid in result or type(quantity) is not int or quantity < 0:
            raise ValueError('INVALID_HOLDINGS')
        if quantity:
            result[sid] = quantity
    return result


def restart_performance(*, baseline, valuations, expected_sample_times=None, account_evidence=None):
    """Valuations are full account valuation API snapshots, in chronological order.
    Grid completeness proves only sampled drawdown, never intraday maximum risk.
    """
    unavailable = dict(status='UNAVAILABLE', return_fraction=None, maximum_drawdown_fraction=None,
        drawdown_certified=False, ledger_mutated=False)
    try:
        initial = F(baseline['initial_equity'])
        cash = F(baseline['cash'])
        start = _time(baseline['effective_at'])
        positions = _positions(baseline['holdings'])
        if initial <= 0 or not valuations:
            return dict(unavailable, reason='POSITIVE_BASELINE_AND_SAMPLES_REQUIRED')
        previous = start
        evidence = account_evidence or {}
        equity_values = [initial]
        times = []
        previous_events = None
        previous_revision = baseline['account_revision']
        for value in valuations:
            at = _time(value['valued_at'])
            if at < start or (times and at <= previous):
                return dict(unavailable, reason='SAMPLE_TIME_ORDER')
            if value.get('status') != 'READY' or not value.get('cash_confirmed'):
                return dict(unavailable, reason='VALUATION_NOT_READY')
            expected_cash, expected_positions = cash, positions
            if value['account_revision'] != baseline['account_revision']:
                pair = evidence.get(value['account_revision'])
                if pair is None:
                    return dict(unavailable, reason='UNVERIFIED_ACCOUNT_CHANGE')
                old, current = pair['baseline_account'], pair['current_account']
                for state in (old, current):
                    if replay(state['account_id'], [r['payload'] for r in state['events']]) != state:
                        return dict(unavailable, reason='ACCOUNT_REPLAY_MISMATCH')
                if old['revision'] != baseline['account_revision'] or current['revision'] != value['account_revision'] or old['account_id'] != current['account_id'] or current['events'][:len(old['events'])] != old['events'] or F(old['total_uninvested_cash']) != cash or {k:q for k,q in old['shares'].items() if q} != positions:
                    return dict(unavailable, reason='BASELINE_LEDGER_BINDING_MISMATCH')
                if previous_events is not None and current['events'][:len(previous_events)] != previous_events:
                    return dict(unavailable, reason='ACCOUNT_HISTORY_REGRESSION')
                previous_events = current['events']
                for record in current['events'][len(old['events']):]:
                    expected_cash += F(record['effect']['cash_delta'])
                    event = record['payload']
                    if event['kind'] == 'CASH_CONFIRM':
                        prefix = current['events'][:current['events'].index(record)+1]
                        confirmed = replay(current['account_id'], [r['payload'] for r in prefix])
                        if F(confirmed['total_uninvested_cash']) != expected_cash:
                            return dict(unavailable, reason='UNCLASSIFIED_CASH_CHANGE')
                expected_positions = {k:q for k,q in current['shares'].items() if q}
                if F(current['total_uninvested_cash']) != expected_cash:
                    return dict(unavailable, reason='UNRECONCILED_TRADE_CASH')
            elif previous_revision != baseline['account_revision']:
                return dict(unavailable, reason='ACCOUNT_HISTORY_REGRESSION')
            if _positions(value['holdings']) != expected_positions:
                return dict(unavailable, reason='UNVERIFIED_ACCOUNT_CHANGE')
            market = sum((F(row['market_value']) for row in value['holdings']), F(0))
            for row in value['holdings']:
                if F(row['price']) <= 0 or F(row['price']) * row['quantity'] != F(row['market_value']):
                    return dict(unavailable, reason='VALUATION_ARITHMETIC_MISMATCH')
                observed = _time(row['observed_at'])
                if not 0 <= (at - observed).total_seconds() <= 120:
                    return dict(unavailable, reason='STALE_OR_FUTURE_QUOTE')
            total = F(value['strategy_total'])
            if market != F(value['market_value']) or total - market != expected_cash:
                return dict(unavailable, reason='UNCLASSIFIED_CASH_CHANGE')
            if total < 0:
                return dict(unavailable, reason='INVALID_EQUITY')
            equity_values.append(total)
            times.append(at)
            previous = at
            previous_revision = value['account_revision']
        peak, drawdown = initial, F(0)
        for equity in equity_values:
            peak = max(peak, equity)
            drawdown = max(drawdown, (peak-equity)/peak)
        complete = (expected_sample_times is not None and len(times) >= 2 and
                    [_time(t) for t in expected_sample_times] == times)
        return dict(status='READY_RECONCILED_NO_EXTERNAL_FLOW', return_fraction=str(equity_values[-1]/initial-1),
            maximum_drawdown_fraction=str(drawdown) if complete else None,
            observed_sample_drawdown_fraction=str(drawdown) if len(times) >= 2 else None,
            drawdown_certified=complete, drawdown_scope='DECLARED_SAMPLES_ONLY' if complete else 'INCOMPLETE_SAMPLING',
            valuation_count=len(times), as_of=valuations[-1]['valued_at'], ledger_mutated=False,
            limitation='Fills require ledger replay; external cash changes require classification. Sampled drawdown is not a continuous or intraday guarantee.')
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return dict(unavailable, reason='INVALID_PERFORMANCE_INPUT')
