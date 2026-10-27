"""Fixed-path forced-action attribution, NOT a deployable news strategy backtest."""
import argparse
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backtest.historical_dividend_next_open_book_research import run_next_open_book


def run(root, directory):
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    out=directory/'replay';out.mkdir(exist_ok=True)
    summary=[]
    for entry in manifest['cases']:
        path=root/entry['path'];raw=path.read_bytes()
        if sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('CASE_HASH_CHANGED')
        case=json.loads(raw)
        if case['initialization_requires_entitlement_reconstruction']:raise ValueError('INITIAL_RIGHTS_UNSUPPORTED')
        initial,last=case['session_dates'][0],case['session_dates'][-1]
        frozen=case['corporate_action_inputs']
        sourcepath=root/'tmp'/case['window']/'execution_inputs.json'
        if sha256(sourcepath.read_bytes()).hexdigest()!=manifest['source_hashes'][str(sourcepath.relative_to(root))]:raise ValueError('INPUT_HASH_CHANGED')
        source=json.loads(sourcepath.read_text(encoding='utf-8'))
        def within(event):return initial < event.get('effective_date',event.get('date','')) <= last
        args=dict(session_dates=case['session_dates'],ohlc=case['ohlc'],initial_cash=case['initial_baseline_ledger']['cash'],
                  initial_shares=case['initial_baseline_ledger']['shares'],fee_bps='0',slippage_bps='5',
                  events=[e for e in frozen['actions'] if within(e)],
                  cash_stock_merger_events=[e for e in frozen['cash_stock_merger_events'] if within(e)],
                  distribution_events=[e for e in frozen['distribution_events'] if within(e)],
                  fractional_settlements=frozen['fractional_settlements'],
                  distribution_fractional_cash_values=frozen['distribution_fractional_cash_values'],
                  price_source_references=frozen['price_source_references'],account_model=source['assembled'].get('account_model'),
                  dividend_events=[e for e in case['dividend_events'] if initial < e['ex_date'] <= last])
        fixed={p['decision_date']:p for p in case['fixed_effective_target_path']}
        original_orders=[o for p in fixed.values() for o in p['original_orders']]
        baseline=run_next_open_book(**args,orders=original_orders)
        if baseline['status']!='COMPLETE':raise ValueError((case['case'],'BASELINE_BLOCKED',baseline['reason']))
        def equal_rows(actual,expected):
            if len(actual)!=len(expected):raise ValueError('ROW_COUNT_MISMATCH')
            for a,b in zip(actual,expected):
                for key in ('date','cash','shares','equity','dividend_receivable'):
                    if a.get(key,'0')!=b.get(key,'0'):raise ValueError((case['case'],a['date'],key,'BASELINE_REPLAY_MISMATCH'))
        equal_rows(baseline['daily_ledger'],case['baseline_comparison_ledger'])
        reports={'BASELINE_ORIGINAL_ORDERS':baseline}
        for arm in ('NO_ACTION','BLOCK_NEW_BUYS','EXIT'):
            def provider(*,decision_date,active_date,state):
                plan=fixed[decision_date]
                if decision_date < case['first_news_decision_close'] or plan['action']=='WAIT_POST_ACTION_MARK':
                    return dict(status='READY',orders=deepcopy(plan['original_orders']))
                target=dict(plan['target_shares']);sid=case['security_id']
                if arm=='EXIT':target[sid]=0
                elif arm=='BLOCK_NEW_BUYS':target[sid]=min(target.get(sid,0),state['shares'].get(sid,0))
                orders=[]
                for security in sorted(set(state['shares'])|set(target)):
                    delta=target.get(security,0)-state['shares'].get(security,0)
                    if delta:orders.append(dict(id='local:'+decision_date+':'+security,security_id=security,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),decision_date=decision_date,active_date=active_date,decision_mark=case['close_prices'][security][decision_date]))
                return dict(status='READY',orders=orders)
            result=run_next_open_book(**args,order_provider=provider)
            if result['status']!='COMPLETE':raise ValueError((case['case'],arm,result['reason']))
            if arm=='NO_ACTION':equal_rows(result['daily_ledger'],baseline['daily_ledger'])
            reports[arm]=result
        starting=Fraction(case['initial_baseline_ledger']['equity'])
        base_end=Fraction(baseline['daily_ledger'][-1]['equity'])
        for arm,book in reports.items():
            end=Fraction(book['daily_ledger'][-1]['equity']);peak=starting;drawdown=Fraction(0)
            for row in book['daily_ledger']:
                value=Fraction(row['equity']);peak=max(peak,value);drawdown=max(drawdown,1-value/peak)
            record=dict(case=case['case'],arm=arm,status='COMPLETE',sessions=len(book['daily_ledger']),
                initial_equity=str(starting),terminal_equity=str(end),delta_vs_baseline=str(end-base_end),
                period_return_pct=float((end/starting-1)*100),local_max_drawdown_pct=float(drawdown*100),
                fill_count=sum(x.get('event')=='ASSUMED_NEXT_OPEN_FILLED' for x in book['order_log']),
                baseline_reference_exact_replay=True,
                branch_matches_baseline=arm in ('BASELINE_ORIGINAL_ORDERS', 'NO_ACTION'),
                forced_action=arm in ('BLOCK_NEW_BUYS','EXIT'))
            summary.append(record)
            (out/(case['case']+'_'+arm+'.json')).write_text(json.dumps(dict(summary=record,book=book),ensure_ascii=False,indent=2),encoding='utf-8')
    result=dict(status='FIXED_PATH_ATTRIBUTION_COMPLETE',cases=5,arms=4,rows=summary,
        source_manifest_sha256=sha256((directory/'manifest.json').read_bytes()).hexdigest(),
        kernel_sha256=sha256((root/'backtest/historical_dividend_next_open_book_research.py').read_bytes()).hexdigest(),
        runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=['Forced actions are sensitivity probes, not news-admitted signals.','Fixed future baseline target path is an ex-post comparator, not branch monthly reselection.',
                    'Original risk targets are frozen; no counterfactual risk-state reoptimization.',
                    'Original kernel cash rationing may allocate more to other unchanged targets after suppressing a buy or selling; no dedicated cash quarantine.',
                    'Metadata availability proxy not earliest original publication certification.','No annualization, candidate selection or production adoption.'])
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 五份报告固定短窗动作敏感性','',
      '这是固定已记录基准目标路径的事后归因，不是新闻事实准入、分支重新选股或可部署策略。五例原订单重放及 NO_ACTION 的每日日终现金、持仓、权益、分红应收均与历史基准精确一致。每例20交易日观察窗（包含新闻首次决策前已发生的执行日，不是动作后20日），佣金0、滑点5bp。','',
      '|案例|强制动作|期末权益USD|相对基准USD|区间收益%|局部最大回撤%|',
      '|---|---|---:|---:|---:|---:|']
    for r in summary:
        if r['arm']=='BASELINE_ORIGINAL_ORDERS':continue
        lines.append(f"|{r['case']}|{r['arm']}|{float(Fraction(r['terminal_equity'])):.2f}|{float(Fraction(r['delta_vs_baseline'])):.2f}|{r['period_return_pct']:.2f}|{r['local_max_drawdown_pct']:.2f}|")
    lines+=['','BLOCK_NEW_BUYS 与 EXIT 是强制敏感性，不代表报告应触发。无参数优化、未择优；锁从首次新闻决策维持至固定窗末。现有kernel会用可用现金按原规则执行其他固定目标，不能解释为卖出所得或被阻止买入的预算单独封存。完整限制见 replay/summary.json。']
    (root/'docs/candidates/local_news_case_replay_result_20261027.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--input',default='tmp/local_news_cases_20261027')
    a=p.parse_args();root=Path(a.root).resolve();r=run(root,root/a.input);print(r['status'])
