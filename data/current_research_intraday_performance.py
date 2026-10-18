"""Conditional point-in-time valuation of a replay-validated V1/V2 BUY paper account.

Pure: no source reads, network, database writes or inferred fills. ``marks`` and
``source_hashes`` are supplied by a trusted server adapter. Hash references here
are bindings/declarations, NOT verification of bytes or external authenticity.
A source adapter must read and verify saved source bytes before supplying them.
No historical curve, annualization, drawdown or total-return certification.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import re

from data.current_research_intraday_continuation_ledger import review_continuation_ledger


def _time(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('AWARE_TIME_REQUIRED')
    return result.astimezone(timezone.utc)



def ledger_observation_floor(state):
    """Latest accepted operation/recording; call only after full ledger replay."""
    times = [_time(state['acceptance']['accepted_at'])]
    times.extend(_time(e['recorded_at']) for e in state['events'])
    times.extend(_time(op['evidence']['accepted_at']) for op in state.get('operations', []) if op['kind'] == 'ACCEPT')
    return max(times)


def compute_intraday_paper_performance(state, *, now, marks=None, source_hashes=None, valuation_kind='CURRENT_MARK'):
    """Value current V1/V2 BUY-chain state only; missing/invalid/stale marks yield INCOMPLETE.

    marks[sid]: security_id, price (exact string), observed_at, received_at,
    valid_until, price_basis='NOMINAL_PER_CURRENT_SHARE',
    unit_continuity='NO_UNPROCESSED_ACTIONS', source_references=[pin keys].
    Continuity and source bytes remain caller responsibilities; this function
    cannot authenticate them. No quote is needed when there are no held shares.
    """
    if not isinstance(state, dict) or state.get('schema') not in ('INTRADAY_INITIAL_BUY_PAPER_LEDGER_V1', 'INTRADAY_CONTINUATION_PAPER_LEDGER_V2'):
        raise ValueError('SUPPORTED_BUY_LEDGER_REQUIRED')
    reviewed = review_continuation_ledger(state)
    current_time = _time(now)
    if valuation_kind not in ('CURRENT_MARK', 'COMPLETED_SESSION_CLOSE'):
        raise ValueError('INVALID_VALUATION_KIND')
    accepted = _time(reviewed['acceptance']['accepted_at'])
    observation_floor = ledger_observation_floor(reviewed)
    if observation_floor > current_time:
        raise ValueError('LEDGER_AFTER_VALUATION_TIME')
    causal = reviewed['acceptance']['proposal']['causal_inputs']
    initial = Fraction(causal['available_cash'])
    cash = Fraction(reviewed['cash'])
    fills = [e for e in reviewed['events'] if e['kind'] == 'FILL']
    principal = sum((e['quantity'] * Fraction(e['price']) for e in fills), Fraction())
    fees = sum((Fraction(e['fees']) for e in fills), Fraction())
    if initial <= 0 or cash + principal + fees != initial or fees != Fraction(reviewed['fees']):
        raise ValueError('CASH_CONSERVATION_FAILED')
    result = dict(
        status='COMPLETE', account_id=reviewed['account_id'], revision=reviewed['revision'],
        research_id=reviewed['acceptance']['proposal']['research_id'],
        research_only=True, execution_blocked=True, real_account=False,
        source_authenticated=False, source_bytes_verified=False,
        return_scope='PRICE_AND_RECORDED_FILL_FEES_ONLY', total_return_certified=False,
        valuation_kind=valuation_kind, valuation_at=current_time.isoformat(), accepted_at=reviewed['acceptance']['accepted_at'],
        initial_cash=str(initial), cash=str(cash), shares=deepcopy(reviewed['shares']),
        reserved_cash=reviewed['reserved_cash'], recorded_fees=str(fees),
        recorded_buy_notional=str(principal), recorded_fill_count=len(fills),
        equity=None, unrealized_price_pnl=None, net_pnl=None, total_return=None,
        annualized_return=None, maximum_close_drawdown=None,
        performance_available=False, marks={}, source_hashes={}, issues=[],
        limitations=['Conditional current-state valuation; caller must verify source bytes, timestamps and unit continuity.',
                     'Fees already reduce cash; no second fee deduction.',
                     'No dividend, corporate-action, historical-return or broker-execution certification.'])
    marks = marks if isinstance(marks, dict) else {}
    source_hashes = source_hashes if isinstance(source_hashes, dict) else {}
    market_value = Fraction()
    latest_fill = max(observation_floor, max((_time(e['executed_at']) for e in fills), default=accepted))
    for sid, quantity in reviewed['shares'].items():
        if not quantity:
            continue
        try:
            mark = marks[sid]
            if not isinstance(mark, dict) or mark.get('security_id') != sid:
                raise ValueError('MARK_IDENTITY_MISMATCH')
            if not isinstance(mark.get('price'), str) or Fraction(mark['price']) <= 0:
                raise ValueError('INVALID_MARK_PRICE')
            observed, received = (_time(mark[k]) for k in ('observed_at', 'received_at'))
            if not latest_fill <= observed <= received <= current_time:
                raise ValueError('MARK_STALE_FUTURE_OR_BEFORE_FILL')
            if valuation_kind == 'CURRENT_MARK':
                if not current_time < _time(mark['valid_until']):
                    raise ValueError('MARK_STALE_FUTURE_OR_BEFORE_FILL')
            elif observation_floor > observed:
                raise ValueError('CURRENT_STATE_AFTER_CLOSE')
            if mark.get('price_basis') != 'NOMINAL_PER_CURRENT_SHARE' or mark.get('unit_continuity') != 'NO_UNPROCESSED_ACTIONS':
                raise ValueError('MARK_UNIT_CONTINUITY_UNAVAILABLE')
            refs = mark.get('source_references')
            if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref or not isinstance(source_hashes.get(ref), str) or not re.fullmatch(r'[0-9a-f]{64}', source_hashes[ref]) for ref in refs):
                raise ValueError('MARK_SOURCE_BINDING_MISSING')
            market_value += quantity * Fraction(mark['price'])
            result['marks'][sid] = deepcopy(mark)
            result['source_hashes'].update({ref: source_hashes[ref] for ref in refs})
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            result['issues'].append(dict(security_id=sid, reason=str(exc)))
    if result['issues']:
        result['status'] = 'INCOMPLETE'
        return result
    equity = cash + market_value
    result['equity'] = str(equity)
    if fills:
        result.update(performance_available=True, unrealized_price_pnl=str(market_value-principal),
                      net_pnl=str(equity-initial), total_return=str((equity-initial)/initial))
    else:
        result['issues'].append(dict(reason='NO_RECORDED_FILLS'))
    return result
