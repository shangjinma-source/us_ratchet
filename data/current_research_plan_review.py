"""Pure same-plan daily range observations, never simulated fills or profit."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import re

from data.current_research_fill_ledger import review_paper_ledger


def review_research_plan(state, *, observed_through, market_bars, source_hashes):
    """observed_through is the caller-confirmed last *completed* market session.

    This pure function cannot authenticate wall-clock session completion or
    source bytes. The caller must do both before supplying the cutoff/pins.
    A current intraday bar is not a completed daily bar. Future bars are rejected,
    not used to retrospectively describe an earlier order. Only the state's
    active frozen plan is reviewed; historical plans are never merged into it.
    """
    def require(ok, message):
        if not ok:
            raise ValueError(message)

    def session(value):
        require(type(value) is str, '明确的交易日期字符串必需')
        require(date.fromisoformat(value).isoformat() == value, '交易日期格式无效')
        return value

    def price(value):
        require(not isinstance(value, bool) and isinstance(value, (str, int, float, Fraction)), 'OHLC必须是明确数值')
        parsed = Fraction(str(value))
        require(parsed > 0, 'OHLC必须为有限正数')
        return parsed

    cutoff = session(observed_through)
    ledger = review_paper_ledger(state)
    require(isinstance(source_hashes, dict) and all(
        isinstance(path, str) and path.strip() and isinstance(digest, str)
        and re.fullmatch('[0-9a-f]{64}', digest) for path, digest in source_hashes.items()), '行情来源指纹格式无效')
    require(isinstance(market_bars, list), '行情必须是明确列表')
    indexed = {}
    for bar in market_bars:
        require(isinstance(bar, dict), '行情行必须是对象')
        sid, day = bar['security_id'], session(bar['session'])
        require(isinstance(sid, str) and bool(sid.strip()), '证券编号无效')
        require(day <= cutoff, '不能使用尚未完成或未来交易日的行情')
        key = (sid, day)
        require(key not in indexed, '证券与交易日行情重复')
        refs = bar['source_references']
        require(isinstance(refs, list) and refs and all(isinstance(ref, str) and ref in source_hashes for ref in refs), '行情引用缺少来源指纹')
        o, h, l, c = (price(bar[field]) for field in ('open', 'high', 'low', 'close'))
        require(l <= min(o, c) <= max(o, c) <= h, 'OHLC范围矛盾')
        indexed[key] = dict(open=str(o), high=str(h), low=str(l), close=str(c), source_references=list(refs))

    plan = state['plan']
    rows = []
    for order, recorded in zip(plan['orders'], ledger['orders']):
        require(order['order_id'] == recorded['order_id'], '冻结订单与账本顺序不匹配')
        bar = indexed.get((order['security_id'], order['active_date']))
        touch, reason = 'UNKNOWN', 'MATCHING_COMPLETED_SESSION_BAR_MISSING'
        if order['active_date'] > cutoff:
            bar, reason = None, 'ORDER_SESSION_AFTER_OBSERVATION_CUTOFF'
        elif bar is not None:
            limit = Fraction(order['limit'])
            touched = Fraction(bar['low']) <= limit if order['side'] == 'BUY' else Fraction(bar['high']) >= limit
            touch, reason = ('YES' if touched else 'NO'), 'COMPLETED_DAILY_RANGE_ONLY'
        rows.append(dict(deepcopy(recorded), ticker=order['ticker'], active_date=order['active_date'],
            limit=order['limit'], observed_touch=touch, reason=reason,
            observed_bar=deepcopy(bar), fill_inferred=False, execution_opportunity_established=False,
            missed_trade_established=False))
    return dict(schema='CURRENT_RESEARCH_PLAN_RANGE_REVIEW_V1', research_only=True,
        execution_blocked=True, account_id=ledger['account_id'], plan_id=ledger['plan_id'],
        research_id=ledger['research_id'], strategy_version=plan['strategy_version'],
        revision=ledger['revision'], observed_through=cutoff, source_hashes=deepcopy(source_hashes),
        completion_basis='CALLER_CONFIRMED_COMPLETED_SESSION_CUTOFF_NOT_CLOCK_VERIFIED_BY_PURE_FUNCTION',
        orders=rows, generated_fill_count=0, pnl_computed=False,
        limitations=['触价仅描述完整日线范围，不证明订单排队、实际成交或漏买。',
                    '部分成交、撤销或到期订单也只描述当日行情；日线不能判定撤单前后是否触价。',
                    '来源字节真实性与交易日收盘时点须由调用方核验；本函数不读文件或时钟。'])
