"""Explain a verified equity path without searches, fitting, or parameter changes."""
import argparse
from collections import defaultdict
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def drawdown_dates(points):
    peak=0; best=(F(0),0,0)
    for index,(_,value) in enumerate(points):
        if value>=points[peak][1]:peak=index
        decline=1-value/points[peak][1]
        if decline>best[0]:best=(decline,peak,index)
    decline,peak,trough=best
    recovery=next((i for i in range(trough+1,len(points)) if points[i][1]>=points[peak][1]),None) if decline else peak
    return dict(maximum_drawdown=str(decline),peak_date=points[peak][0],trough_date=points[trough][0],
        peak_equity=str(points[peak][1]),trough_equity=str(points[trough][1]),
        recovery_date=points[recovery][0] if recovery is not None else None,
        recovery_sessions_from_peak=recovery-peak if recovery is not None else None,
        recovery_time_unit='TRADING_SESSIONS',recovery_observed_through=points[-1][0],
        recovery_status='RECOVERED_IN_VERIFIED_INTERVAL' if recovery is not None else 'NOT_RECOVERED_BY_VERIFIED_END')


def audit(book_path,review_path):
    raw=book_path.read_bytes(); reviewed=json.loads(review_path.read_bytes())
    if reviewed['status'] not in ('EXECUTED_PREFIX_REVIEW_PASS','COMPLETE_DECLARED_INTERVAL_REVIEW_PASS'):
        raise ValueError('SUCCESSFUL_INTERVAL_REVIEW_REQUIRED')
    if not reviewed['proof']['risk_provider_certified']:raise ValueError('RISK_REVIEW_REQUIRED')
    pins=reviewed['source_hashes']
    matches=[p for p,h in pins.items() if (ROOT/p).resolve()==book_path.resolve() and h==sha256(raw).hexdigest()]
    if len(matches)!=1:raise ValueError('REVIEW_BOOK_HASH_MISMATCH')
    candidates=[]
    for p,h in pins.items():
        if p.endswith('.json') and (ROOT/p).resolve()!=book_path.resolve():
            content=(ROOT/p).read_bytes()
            if sha256(content).hexdigest()!=h:raise ValueError('REVIEW_INPUT_HASH_CHANGED:'+p)
            value=json.loads(content)
            if 'assembled' in value and 'ohlc' in value:candidates.append(value)
    if len(candidates)!=1:raise ValueError('UNIQUE_REVIEWED_PRICE_INPUT_REQUIRED')
    document=candidates[0]; bars=document['ohlc']; assembled=document['assembled']; book=json.loads(raw)
    rows=book['daily_ledger']; count=reviewed['executed_sessions']
    if len(rows)!=count or rows[-1]['date']!=reviewed['end']:raise ValueError('REVIEW_INTERVAL_MISMATCH')
    points=[(reviewed['start'],F(20000))]+[(row['date'],F(row['equity'])) for row in rows]
    path=drawdown_dates(points)
    if F(path['maximum_drawdown'])!=F(reviewed['proof']['maximum_drawdown']):raise ValueError('DRAWDOWN_PROOF_MISMATCH')
    annual=[]
    for year in sorted({row['date'][:4] for row in rows}):
        indices=[i for i,(day,value) in enumerate(points) if i and day.startswith(year)]
        first,last=indices[0],indices[-1]
        year_points=points[first-1:last+1]
        expected=[day for day in assembled['session_dates'][1:] if day.startswith(year)]
        actual=[points[i][0] for i in indices]
        full=(actual==expected and bool(expected) and expected[0][5:7]=='01' and expected[-1][5:7]=='12')
        annual.append(dict(year=int(year),valuation_start=year_points[0][0],first_execution_date=points[first][0],
            end=points[last][0],covered_sessions=len(indices),complete_calendar_year_in_frozen_calendar=full,
            interval_return=str(year_points[-1][1]/year_points[0][1]-1),
            maximum_drawdown=drawdown_dates(year_points)['maximum_drawdown'],annualized=False))
    fills=defaultdict(list)
    for log in book['order_log']:
        if log['event']=='ASSUMED_NEXT_OPEN_FILLED':fills[log['date']].append(log)
    daily=[]; exits=[]; previous_shares={}; previous_date=reviewed['start']; previous_equity=F(20000)
    last_month=None; exited=set(); peak_to_trough=defaultdict(F)
    for row,provider in zip(rows,book['provider_audit'][:count]):
        day=row['date']; netflow=defaultdict(F)
        for fill in fills[day]:
            sid=fill['security_id']; notional=fill['quantity']*F(fill['price']); fee=F(fill['fee'])
            netflow[sid]+=notional+fee if fill['side']=='BUY' else -notional+fee
        pnl={}
        for sid in set(previous_shares)|set(row['shares'])|set(netflow):
            old=previous_shares.get(sid,0); new=row['shares'].get(sid,0)
            new_value=new*F(bars[sid][day]['close']) if new else F(0)
            old_value=old*F(bars[sid][previous_date]['close']) if old else F(0)
            pnl[sid]=new_value-old_value-netflow[sid]
        change=F(row['equity'])-previous_equity
        residual=change-sum(pnl.values(),F(0))
        daily.append(dict(date=day,equity=str(row['equity']),equity_change=str(change),
            security_mark_and_trade_pnl={s:str(v) for s,v in pnl.items()},
            other_cash_receivable_or_action_contribution=str(residual),shares=row['shares']))
        if path['peak_date']<day<=path['trough_date']:
            for sid,value in pnl.items():peak_to_trough[sid]+=value
            peak_to_trough['OTHER_CASH_RECEIVABLE_OR_ACTION']+=residual
        risk=provider.get('risk_overlay') or {}; state=risk.get('state')
        if state:
            if state['decision_date']!=last_month:exited=set();last_month=state['decision_date']
            for sid in sorted(set(state['exited'])-exited):
                signal_close=F(state['last_closes'][sid]); peak_close=F(state['peaks'][sid])
                sold=[fill for fill in fills[day] if fill['security_id']==sid and fill['side']=='SELL']
                exits.append(dict(security_id=sid,signal_date=state['session_date'],execution_date=day if sold else None,
                    quantity_before=previous_shares.get(sid,0),sold_quantity=sum(f['quantity'] for f in sold),
                    peak_close=str(peak_close),signal_close=str(signal_close),signal_drawdown=str(1-signal_close/peak_close),
                    marked_decline_from_risk_peak=str(previous_shares.get(sid,0)*(signal_close-peak_close)),
                    signal_close_to_fill_pnl=str(sum((f['quantity']*(F(f['price'])-signal_close)-F(f['fee']) for f in sold),F(0))),
                    interpretation='Peak-mark decline is not tax-lot realized loss; next-open gap/slippage is shown separately.'))
            exited=set(state['exited'])
        previous_shares=row['shares'];previous_date=day;previous_equity=F(row['equity'])
    if sum(peak_to_trough.values(),F(0))!=F(path['trough_equity'])-F(path['peak_equity']):raise ValueError('ATTRIBUTION_DOES_NOT_RECONCILE')
    return dict(status='VERIFIED_INTERVAL_DRAWDOWN_DIAGNOSTIC',start=reviewed['start'],end=reviewed['end'],
        executed_sessions=count,drawdown=path,calendar_year_intervals=annual,daily_contributions=daily,risk_exit_events=exits,
        peak_to_trough_contributions={s:str(v) for s,v in sorted(peak_to_trough.items(),key=lambda item:item[1])},
        source_hashes={str(book_path):sha256(raw).hexdigest(),str(review_path):sha256(review_path.read_bytes()).hexdigest()},
        limitations=['Verified interval only; no full bull/bear claim, parameter selection, or annualization.',
                    'Security PnL is closing position value change minus net trade cashflow; distributions/action effects may remain in separately shown residual.'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--book',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=audit(args.book,args.review)
    with args.output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    dd=result['drawdown']; top=list(result['peak_to_trough_contributions'].items())[:5]
    lines=['# 已验证区间回撤诊断','',f"区间 {result['start']} 至 {result['end']}，共 {result['executed_sessions']} 个交易日。",'',
        f"最大回撤 {float(F(dd['maximum_drawdown'])):.2%}；峰值 {dd['peak_date']}，谷值 {dd['trough_date']}。",
        f"恢复日期：{dd['recovery_date'] or '截至 '+dd['recovery_observed_through']+' 仍未恢复'}；恢复耗时单位为交易会话。",'', '峰值至谷值贡献（美元，含交易费用）：']
    lines += [f'- {sid}: {float(F(value)):.2f}' for sid,value in top]
    lines += ['', '| 自然年 | 估值起点 | 已覆盖末日 | 区间收益 | 区间回撤 | 全年完整 |', '|---|---|---|---:|---:|---|']
    lines += [f"| {row['year']} | {row['valuation_start']} | {row['end']} | {float(F(row['interval_return'])):.2%} | {float(F(row['maximum_drawdown'])):.2%} | {'是' if row['complete_calendar_year_in_frozen_calendar'] else '否'} |" for row in result['calendar_year_intervals']]
    lines += ['',f"识别 {len(result['risk_exit_events'])} 次新增退出信号；信号日、实际成交日及隔夜/滑点损益见 JSON。",'', '仅用于定位已验证路径的损失来源，不据此选择参数，也不代表完整牛熊结论。']
    args.output.with_suffix('.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(status=result['status'],drawdown=dd,risk_exits=len(result['risk_exit_events']))))


if __name__=='__main__':main()
