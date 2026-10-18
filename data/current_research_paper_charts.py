"""Read-only charts of the verified current paper plan; no initial-cache fallback."""
from pathlib import Path

from data.current_research_paper_service import SERVICE as BASE_SERVICE
from data.current_research_ohlc_panel import parse_provider_ohlc
from data.current_portfolio_preview import _group_bars


class CurrentResearchPaperCharts:
    def __init__(self, base_service=BASE_SERVICE):
        self.base = base_service

    def bars(self, account_id, expected_plan_id, security_id, interval='day'):
        def require(ok, message):
            if not ok:
                raise ValueError(message)

        require(interval in ('day', 'week', 'month'), 'K线周期无效')
        state = self.base._read_account(account_id)
        plan = state['plan']
        require(expected_plan_id == plan['plan_id'], '当前模拟计划已变化，请恢复读取')
        allowed = {sid for positions in (plan['target_quantities'], state['shares'])
                   for sid, quantity in positions.items() if quantity > 0}
        require(isinstance(security_id, str) and security_id in allowed, '证券不在当前正目标或正持仓中')
        causal = plan['causal_inputs']
        ticker = causal['securities'][security_id]
        quote = causal['quotes'].get(security_id)
        require(isinstance(quote, dict), '当前证券缺少计划内报价来源')
        pins = causal['research_snapshot']['source_hashes']
        # A quote's own pinned raw is authoritative; never scan unrelated closure files.
        paths = [path for path in quote['source_references']
                 if path in pins and Path(path).name == ticker + '.response.bin']
        require(len(set(paths)) == 1, '当前证券缺少唯一已绑定原始日线来源')
        path = paths[0]
        channel = parse_provider_ohlc(self.base._read_pin(path, pins[path]), ticker)
        cutoff = causal['decision_date']
        daily, missing = [], []
        for session, values in zip(channel['dates'], channel['values']):
            if session > cutoff:
                continue
            if any(value is None for value in values[:4]):
                missing.append(session)
                continue
            daily.append(dict(date=session, open=values[0], high=values[1], low=values[2],
                              close=values[3], volume=values[4]))
        require(daily and daily[-1]['date'] == cutoff, '缺少决策日完整OHLC，不使用旧日线替代')
        return dict(status='AVAILABLE', account_id=account_id, plan_id=plan['plan_id'],
                    research_id=plan['research_id'], security_id=security_id, ticker=ticker,
                    interval=interval, as_of=cutoff, daily_as_of=cutoff,
                    bars=_group_bars(daily, interval)[-260:], source_references=[path],
                    source_hashes={path:pins[path]}, missing_sessions=missing,
                    missing_session_count=len(missing), no_missing_fill=True,
                    calendar_completeness_verified=False,
                    last_period_may_be_partial=interval != 'day',
                    adjustment_basis='PINNED_PROVIDER_RAW_HISTORICAL_COORDINATES_NOT_CERTIFIED_NOMINAL',
                    research_only=True, execution_blocked=True)


SERVICE = CurrentResearchPaperCharts()
