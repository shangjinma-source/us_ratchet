"""Offline timing/execution harness; actions are synthetic, NOT an AI recommendation."""
from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backtest.historical_dividend_next_open_book_research import run_next_open_book
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


def eligible(published, opening, latency_seconds=120):
    if latency_seconds < 0: raise ValueError('NEGATIVE_LATENCY')
    p=datetime.fromisoformat(published); o=datetime.fromisoformat(opening)
    if p.tzinfo is None or o.tzinfo is None: raise ValueError('AWARE_CLOCK_REQUIRED')
    return p+timedelta(seconds=latency_seconds)<o


def replay(inputs, book, action, published='2021-07-15T19:01:00-04:00', initial_date='2021-07-15', target_transform=None):
    if action not in ('NO_CHANGE','BLOCK_NEW_BUYS','EXIT','HALF_TARGET'):
        raise ValueError('UNKNOWN_ACTION')
    assembled=inputs['assembled']; all_days=assembled['session_dates']
    expected={'2021-07-15':['2021-07-15','2021-07-16','2021-07-19','2021-07-20'],'2021-11-03':['2021-11-03','2021-11-04','2021-11-05','2021-11-08']}
    if initial_date not in expected: raise ValueError('FIXED_CASE_REQUIRED')
    index=all_days.index(initial_date); days=all_days[index:index+4]
    if days!=expected[initial_date]: raise ValueError('FIXED_SESSIONS_CHANGED')
    audit=dict(zip(all_days[:-1],book['provider_audit']))
    initial=next(r for r in book['daily_ledger'] if r['date']==days[0])
    if any(Fraction(str(initial.get(k,0))) for k in ('receivable','dividend_receivable','nontradable_entitlement_value')) or initial.get('distribution_rights') or initial.get('merger_entitlements'):
        raise ValueError('INITIAL_RIGHTS_UNSUPPORTED')
    for key in ('actions','provider_actions','cash_stock_merger_events','distribution_events'):
        if any(days[0]<e.get('date',e.get('effective_date',''))<=days[-1] for e in assembled.get(key) or []): raise ValueError('LOCAL_ACTION_UNSUPPORTED')
    if any(days[0]<=w['decision_date']<days[-1] for w in assembled['monthly_inputs']): raise ValueError('MONTH_RESET_FORBIDDEN')
    if any(days[0]<e['ex_date']<=days[-1] for e in inputs.get('dividend_events',[])): raise ValueError('LOCAL_DIVIDEND_UNSUPPORTED')
    risk=MonthlyExitCoreResearchAdapter(); risk.state=deepcopy(audit[all_days[index-1]]['risk_overlay']['state']); risk.last_day=risk.state['session_date']
    ceiling=deepcopy(audit[days[0]]['monthly_ceiling']); epoch=audit[days[0]]['target_decision_date']; trace=[]; sid='research:security:mrna'
    def provider(*,decision_date,active_date,state):
        target,diag=risk.apply(day=decision_date,month=epoch,target=deepcopy(ceiling),closes={s:assembled['close_prices'][s][decision_date] for s in ceiling})
        original=deepcopy(target)
        # Risk uses only the preceding close. News can arrive AFTER that close,
        # provided processing completes BEFORE this actual execution opening.
        opening=datetime.fromisoformat(active_date+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
        enabled=eligible(published,opening) and active_date in days[1:3]
        if enabled:
            if action=='EXIT': target[sid]=0
            elif action=='BLOCK_NEW_BUYS': target[sid]=min(target.get(sid,0),state['shares'].get(sid,0))
            elif action=='HALF_TARGET': target[sid]=target.get(sid,0)//2
        if enabled and target_transform is not None:
            target=target_transform(deepcopy(original),deepcopy(state))
            if any(type(v) is not int or v<0 or v>original.get(k,0) for k,v in target.items()): raise ValueError('OVERLAY_EXCEEDS_RISK_TARGET')
        orders=[]
        for s in sorted(set(state['shares'])|set(target)):
            delta=target.get(s,0)-state['shares'].get(s,0)
            if delta: orders.append(dict(id='preopen:'+active_date+':'+s,security_id=s,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),decision_date=decision_date,active_date=active_date,decision_mark=assembled['close_prices'][s][decision_date]))
        trace.append(dict(risk_asof_close=decision_date,news_available_at=published,processing_seconds=120,execution_open=opening,news_active=enabled,original_target=original,target=deepcopy(target),risk=diag,orders=deepcopy(orders)))
        return dict(status='READY',orders=orders)
    result=run_next_open_book(session_dates=days,ohlc=inputs['ohlc'],initial_cash=initial['cash'],initial_shares=initial['shares'],fee_bps='0',slippage_bps='5',order_provider=provider)
    if result['status']!='COMPLETE': raise ValueError(result.get('reason'))
    return dict(book=result,trace=trace)


def opening_metrics(initial, ohlc, results, first_day):
    """Separate the already-realized overnight gap from post-opening changes."""
    cash=Fraction(initial['cash']); shares=deepcopy(initial['shares'])
    common_open=cash+sum(Fraction(ohlc[s][first_day]['open'])*q for s,q in shares.items() if q)
    arms={}
    for action,result in results.items():
        filled=[x for x in result['book']['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED' and x['date']==first_day]
        after_cash=cash; after_shares=deepcopy(shares)
        for fill in filled:
            sid=fill['security_id']; quantity=fill['quantity']; value=Fraction(fill['price'])*quantity
            after_cash+=value if fill['side']=='SELL' else -value
            after_cash-=Fraction(fill['fee'])
            after_shares[sid]=after_shares.get(sid,0)+(quantity if fill['side']=='BUY' else -quantity)
        after_equity=after_cash+sum(Fraction(ohlc[s][first_day]['open'])*q for s,q in after_shares.items() if q)
        arms[action]=dict(first_open_fills=filled,post_fill_open_equity=str(after_equity),
            first_open_execution_cost=str(common_open-after_equity),
            terminal_pnl_from_common_first_open=str(Fraction(result['book']['daily_ledger'][-1]['equity'])-common_open))
    return dict(first_execution_date=first_day,common_pre_fill_open_equity=str(common_open),
        initial_close_equity=initial['equity'],shared_close_to_open_gap_pnl=str(common_open-Fraction(initial['equity'])),
        gap_is_not_attributed_to_news_action=True,arms=arms)


def run(root,output):
    root=Path(root); output=Path(output); pins={}
    def read(path):
        raw=(root/path).read_bytes();pins[path]=sha256(raw).hexdigest();return json.loads(raw)
    base='tmp/recent_continuous_baseline_20261026_v7/'
    inputs=read(base+'execution_inputs.json');book=read(base+'book.json')
    receipt_dir='tmp/news_next_three_source_audit_20261028/'
    receipts=read(receipt_dir+'receipts.json')
    for name in ('spglobal.html','prnewswire.html'):
        receipt=next(r for r in receipts if r['file']==name)
        raw=(root/receipt_dir/name).read_bytes()
        if receipt['status']!=200 or sha256(raw).hexdigest()!=receipt['sha256']: raise ValueError('SOURCE_CHANGED')
        pins[receipt_dir+name]=receipt['sha256']
    results={a:replay(inputs,book,a) for a in ('NO_CHANGE','BLOCK_NEW_BUYS','EXIT','HALF_TARGET')}
    baseline=results['NO_CHANGE']['book']['daily_ledger']
    for actual in baseline:
        expected=next(r for r in book['daily_ledger'] if r['date']==actual['date'])
        for k in ('cash','shares','equity','dividend_receivable'):
            if actual.get(k,'0')!=expected.get(k,'0'):raise ValueError(('BASELINE_NOT_EXACT',actual['date'],k))
    sid='research:security:mrna'
    summary=dict(status='ENGINEERING_EXECUTION_PROBE_COMPLETE',baseline_exact=True,synthetic_actions_not_ai=True,published_at='2021-07-15T19:01:00-04:00',source_time_boundary='Current original distribution page timestamp; not archived first public availability',initial_shares=next(r['shares'][sid] for r in book['daily_ledger'] if r['date']=='2021-07-15'),initial_target=results['NO_CHANGE']['trace'][0]['original_target'][sid],first_open=inputs['ohlc'][sid]['2021-07-16'],arms={a:dict(terminal_delta_vs_baseline=str(Fraction(r['book']['daily_ledger'][-1]['equity'])-Fraction(baseline[-1]['equity'])),fills=sum(x['event']=='ASSUMED_NEXT_OPEN_FILLED' for x in r['book']['order_log'])) for a,r in results.items()},source_hashes=pins,limitations=['Outcome-selected discovery sample, not strategy validation.','All arms share close-to-open gap; fills use actual next open plus 5bp, never prior close.','Two execution openings affected, third expires; expiry does not override original 20% exit.','Daily close marks only; intraday drawdown and actual news processing not known.','No AI inference, no annualization, no new optimizer, no production changes.'])
    initial=next(r for r in book['daily_ledger'] if r['date']=='2021-07-15')
    summary['event_open_basis']=opening_metrics(initial,inputs['ohlc'],results,'2021-07-16')
    for filename in (__file__,'backtest/historical_dividend_next_open_book_research.py','backtest/monthly_exit_core_research_adapter.py'):
        path=Path(filename);pins[str(path)]=sha256(path.read_bytes()).hexdigest()
    output.mkdir(parents=True,exist_ok=True)
    for a,r in results.items():(output/(a+'.json')).write_text(json.dumps(r,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.root,a.output)))

