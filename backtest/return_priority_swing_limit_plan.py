"""Fixed Root research hypotheses, not adopted strategy or return forecast."""
from fractions import Fraction


def amount(value, positive=False):
    if isinstance(value, bool):
        raise ValueError('Boolean amount')
    parsed = Fraction(str(value))
    if parsed < 0 or positive and not parsed:
        raise ValueError('Invalid amount')
    return parsed


def floor_cent(value):
    return Fraction(value * 100 // 1, 100)


def ceil_cent(value):
    return Fraction(-(-value * 100 // 1), 100)


def build_swing_limit_plan(*, mode, observed_ohlc, decision_date, next_session,
                           frozen_weights, initial_cash, available_cash, shares,
                           entry_positions=None):
    """Caller supplies consecutive completed sessions in decision nominal units.

    observed_ohlc[sid]: basis='DECISION_NOMINAL_SHARE_UNITS', unit_asof=decision,
    bars=[{date,open,high,low,close}]. All past OHLC must be converted to the
    decision share unit, using only then-effective splits, before calling.
    entry_positions[sid]: average_cost, entry_atr14, basis, unit_asof. Both
    values use current decision units; entry ATR is frozen at actual entry.
    next_session is caller's explicit market-calendar next session, never inferred.
    No fees assumed. Same-day prospective sell proceeds never fund buys.
    """
    if mode not in ('trend_exit', 'band_exit') or next_session <= decision_date:
        raise ValueError('Explicit mode and later next market session required')
    budget, cash = amount(initial_cash), amount(available_cash)
    weights = {sid: amount(weight) for sid, weight in frozen_weights.items()}
    if sum(weights.values()) > 1:
        raise ValueError('Frozen weights exceed initial cash')
    if any(type(q) is not int or q < 0 for q in shares.values()):
        raise ValueError('Nonnegative integer shares required')
    identifiers = sorted(set(weights) | {sid for sid, q in shares.items() if q})
    orders, diagnostics, errors = [], {}, []
    reserved = Fraction(0)
    for sid in identifiers:
        try:
            source = observed_ohlc[sid]
            if source['basis'] != 'DECISION_NOMINAL_SHARE_UNITS' or source['unit_asof'] != decision_date:
                raise ValueError('UNKNOWN_OR_STALE_SHARE_UNITS')
            bars = [bar for bar in source['bars'] if bar['date'] <= decision_date]
            dates = [bar['date'] for bar in bars]
            if len(bars) < 20 or dates != sorted(set(dates)) or dates[-1] != decision_date:
                raise ValueError('INSUFFICIENT_OR_INVALID_COMPLETED_HISTORY')
            # Caller binds full session calendar; dates alone cannot certify
            # holiday vs missing session, so explicit continuity assertion needed.
            if source.get('complete_session_history') is not True:
                raise ValueError('SESSION_CONTINUITY_NOT_DECLARED')
            values = []
            for bar in bars[-20:]:
                row = {key: amount(bar[key], True) for key in ('open', 'high', 'low', 'close')}
                if not row['low'] <= min(row['open'], row['close']) <= max(row['open'], row['close']) <= row['high']:
                    raise ValueError('INVALID_OHLC')
                values.append(row)
            close = values[-1]['close']
            sma5 = sum(row['close'] for row in values[-5:]) / 5
            sma20 = sum(row['close'] for row in values) / 20
            tr = [max(values[i]['high'] - values[i]['low'],
                      abs(values[i]['high'] - values[i - 1]['close']),
                      abs(values[i]['low'] - values[i - 1]['close'])) for i in range(6, 20)]
            atr = sum(tr) / 14
            held = shares.get(sid, 0)
            diagnostic = dict(close=str(close), sma5=str(sma5), sma20=str(sma20), atr14=str(atr), held_shares=held)
            side, q, limit = None, 0, None
            if held:
                if close <= sma20:
                    side, q, limit = 'SELL', held, floor_cent(close * Fraction('0.994'))
                    diagnostic['reason'] = 'CLOSE_NOT_ABOVE_SMA20_EXIT'
                elif mode == 'band_exit':
                    entry = (entry_positions or {})[sid]
                    if entry['basis'] != 'DECISION_NOMINAL_SHARE_UNITS' or entry['unit_asof'] != decision_date:
                        raise ValueError('ENTRY_COST_OR_ATR_UNIT_UNKNOWN')
                    limit = ceil_cent(amount(entry['average_cost'], True) + 2 * amount(entry['entry_atr14']))
                    side, q = 'SELL', held
                    diagnostic['reason'] = 'ENTRY_COST_PLUS_TWO_FROZEN_ENTRY_ATR'
                else:
                    diagnostic['reason'] = 'TREND_HOLD'
            elif close > sma20 and weights.get(sid, 0):
                limit = floor_cent(min(close * Fraction('0.994'), max(sma5, sma20, close - Fraction('0.6') * atr)))
                if limit <= 0:
                    raise ValueError('NONPOSITIVE_ROUNDED_LIMIT')
                q = int(budget * weights[sid] // limit)
                side = 'BUY' if q else None
                reserved += q * limit
                diagnostic['reason'] = 'TREND_ENTRY' if q else 'ALLOCATION_BELOW_ONE_SHARE'
            else:
                diagnostic['reason'] = 'NO_ENTRY_WEAK_TREND_OR_ZERO_WEIGHT'
            if side:
                if limit <= 0:
                    raise ValueError('NONPOSITIVE_ROUNDED_LIMIT')
                orders.append(dict(id=f'{mode}:{decision_date}:{sid}:{side}', security_id=sid,
                                   decision_date=decision_date, active_date=next_session,
                                   side=side, quantity=q, limit=str(limit)))
            diagnostics[sid] = diagnostic
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as error:
            errors.append({'security_id': sid, 'reason': str(error)})
    status = 'BLOCKED' if errors else 'CASH_ALLOCATION_REQUIRED' if reserved > cash else 'READY'
    return dict(status=status, orders=orders if status == 'READY' else [],
                proposed_orders=orders, errors=errors, diagnostics=diagnostics,
                signal_asof=decision_date, active_date=next_session, expiry=next_session,
                time_in_force='DAY', reservation_cash=str(reserved), available_cash=str(cash),
                mode=mode, assumption_role='ROOT_FIXED_RESEARCH_HYPOTHESIS_NOT_USER_RISK_PREFERENCE',
                adopted=False, forecast_return=None,
                limitations=['Limit sell can remain unfilled after a gap down; no stop-loss or return guarantee.',
                             'Actual entry cost and entry ATR must come from fills and frozen entry-day information.',
                             'Next-session calendar and historical unit/continuity declarations are caller responsibilities.'])
