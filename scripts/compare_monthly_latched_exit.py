"""Read-only five-arm saved-path comparison; never imports selection or books."""
import hashlib
import json
import sys
from contextlib import contextmanager
from datetime import date
from fractions import Fraction as F
from pathlib import Path
from backtest.continuous_calendar_year_metrics import calendar_year_metrics

ROOT = Path(__file__).resolve().parents[1]
RUN = 'tmp/monthly_latched_sma20_exit_20261016_v1'
OUTPUT = 'tmp/monthly_latched_exit_comparison_20261016_v1'
SEALED = {
    'B0': ('tmp/daily_exclusion_B0_20261016_v1/outcome.json', 'b60767394f091b5107186a01aa7747e0ef467407fc67f2901a410920ddf13e0f'),
    'R2': ('tmp/daily_exclusion_R2_20261016_v1/R2/outcome.json', '38a0f5236bb633b14e7b8c76cf1fe732a5a53a76cfb7bfbdd9db52bf910f14c5'),
    'half': ('tmp/partial_trend_exposure_20261016_v1/outcome.json', '4087208d4d1c37192de55a15677b6eb68409bb9dc84594abffe0598d0995682f'),
    'premium': ('tmp/adaptive_daily_sell_premium_20261016_v1/outcome.json', 'f348ab818c3be0a4a157a5b6f25c0035a76c10df0e2af8c1617e4b99dbd84600'),
}


@contextmanager
def integer_text_limit():
    previous=sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(max(previous,50000) if previous else 0)
        yield
    finally:
        sys.set_int_max_str_digits(previous)


@integer_text_limit()
def statistics(out, sessions, capital='20000'):
    if out['status'] != 'COMPLETE': raise ValueError('OUTCOME_NOT_COMPLETE')
    rows = out['daily_ledger']
    yearly = calendar_year_metrics(opening_date=sessions[0], opening_equity=capital,
        daily_ledger=rows, expected_sessions=sessions[1:], report_through=sessions[-1])
    peak = F(capital); worst = F(0); peak_date=sessions[0]
    worst_peak=worst_trough=None;underwater=longest_underwater=0
    for row in rows:
        equity = F(row['equity'])
        if equity <= 0: raise ValueError('NONPOSITIVE_NAV')
        if equity>=peak:
            peak=equity;peak_date=row['date'];underwater=0
        else:
            underwater+=1;longest_underwater=max(longest_underwater,underwater)
        drawdown=1-equity/peak
        if drawdown>worst:worst=drawdown;worst_peak=peak_date;worst_trough=row['date']
    fills = [r for r in out['order_log'] if r['event'] in ('ASSUMED_NEXT_OPEN_FILLED','ASSUMED_INTRADAY_LIMIT_FILLED')]
    gross = sum((F(r['price'])*r['quantity'] for r in fills), F(0))
    nav_mean = sum((F(r['equity']) for r in rows), F(0))/len(rows)
    cash_ratios = [F(r['cash'])/F(r['equity']) for r in rows]
    ratio = F(rows[-1]['equity'])/F(capital)
    days = (date.fromisoformat(sessions[-1])-date.fromisoformat(sessions[0])).days
    return dict(years=[dict(year=r['year'],sessions=r['sessions'],through=r['last_session'],
        return_fraction=r['cumulative_return'],maximum_close_drawdown=r['maximum_within_year_close_drawdown']) for r in yearly['years']],
        final_equity=rows[-1]['equity'],total_return=str(ratio-1),cagr=float(ratio)**(365/days)-1,
        cagr_exact_inputs=dict(wealth_ratio=str(ratio),exponent=str(F(365,days))),
        maximum_close_drawdown=str(worst),fills=len(fills),fees=str(F(out['fees'])),
        maximum_drawdown_peak_date=worst_peak,maximum_drawdown_trough_date=worst_trough,
        longest_underwater_close_sessions=longest_underwater,end_still_underwater=underwater>0,
        current_underwater_close_sessions=underwater,
        stock_held_close_sessions=sum(F(row['stock_value'])>0 for row in rows),
        stock_held_close_fraction=str(F(sum(F(row['stock_value'])>0 for row in rows),len(rows))),
        turnover_gross_traded_dollars=str(gross),turnover_gross_over_mean_close_nav=str(gross/nav_mean),
        cash_fraction_mean=str(sum(cash_ratios,F(0))/len(rows)),cash_fraction_min=str(min(cash_ratios)),cash_fraction_max=str(max(cash_ratios)))


def build(root=ROOT):
    pins = {}
    def read(name, expected=None):
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()): raise ValueError('OUTSIDE_ROOT')
        raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected: raise ValueError('HASH_MISMATCH:'+name)
        if name in pins and pins[name] != digest: raise ValueError('INPUT_CHANGED:'+name)
        pins[name] = digest
        return json.loads(raw)
    old_report=read('tmp/daily_strategy_comparison_20261016_v2.json','12db07227726db1d2b15dfce3241e9ce72122d8c70beab4b39e8946ddd6f09db')
    old_review=read('tmp/partial_comparison_windows_independent_20261016_v1.json','25463866b29ad6708e22a132fc8e8712342510757ab7dc4bf4ef6ce1fec19119')
    if old_review['status']!='PASS_INDEPENDENT_SAVED_COMPARISON_AND_WINDOWS':raise ValueError('OLD_REVIEW_REQUIRED')
    review = read(RUN+'/independent_review_v1.json')
    if review['status'] != 'PASS_SAVED_MONTHLY_LATCH_REVIEW': raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    terminal = read(RUN+'/terminal.json')
    if terminal['status'] != 'COMPLETE' or not terminal['source_pins_unchanged']: raise ValueError('TERMINAL_NOT_COMPLETE')
    candidate = read(RUN+'/outcome.json', review['outcome_sha256'])
    pre = read(RUN+'/preflight.json')
    closure=dict(old_report['source_hashes'])
    for name,h in pre['source_hashes'].items():
        if name in closure and closure[name]!=h:raise ValueError('SOURCE_PIN_CONFLICT')
        closure[name]=h
    for name,h in closure.items():
        raw=(root/name).resolve()
        if not raw.is_relative_to(root.resolve()): raise ValueError('OUTSIDE_ROOT')
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=h: raise ValueError('SOURCE_DRIFT:'+name)
        pins[name]=h
    if [pre[k] for k in ('initial_cash','fee_bps','slippage_bps')] != ['20000','0','0']: raise ValueError('PARAMETER_MISMATCH')
    prepared=read(pre['prepared_path'],pre['prepared_sha256']);sessions=prepared['session_dates']
    arms={name:statistics(read(path,h),sessions) for name,(path,h) in SEALED.items()}
    arms['latch']=statistics(candidate,sessions)
    # Equal intervals and capital make the exact wealth comparison equivalent to CAGR ordering.
    improvement=F(arms['latch']['final_equity'])>=F(arms['B0']['final_equity']) and F(arms['latch']['maximum_close_drawdown'])<F(arms['B0']['maximum_close_drawdown'])
    return dict(schema='MONTHLY_LATCH_FIVE_ARM_SAVED_COMPARISON_V1',status='VERIFIED_INPUTS_COMPARISON',
        opening_date=sessions[0],through=sessions[-1],initial_cash='20000',arms=arms,
        joint_improvement_against_B0=improvement,automatic_promotion=False,
        turnover_definition='BUY+SELL gross / arithmetic mean daily close NAV; not annualized or one-way',
        cash_definition='Arithmetic mean of daily close cash/NAV; includes unsettled rights in NAV when present',
        underwater_definition='Consecutive close sessions strictly below running peak; equality recovers; first deepest trough and latest prior peak',
        holding_definition='Sessions with close stock_value > 0 / all ledger sessions; excludes rights-only exposure and intraday holding time',
        scope='98-name TRI-excluded observed domain; conditional historical nominal prices; zero modeled fees/slippage, other charges unknown; daily experiment, not current minute limits; inspected sample, not OOS; 2026 is period return',source_hashes=pins)


@integer_text_limit()
def markdown(report):
    pct=lambda x:f'{float(F(str(x)))*100:.2f}%'
    lines=['| 方案 | 2024收益 / 回撤 | 2025收益 / 回撤 | 2026截至10-13收益 / 回撤 | 整段年化 / 回撤 | 期末美元 | 成交笔数 | 费用美元 | 双向换手倍数 | 平均现金占比 |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    labels={'B0':'月度换股、开盘执行','R2':'趋势走弱全退出、恢复即回补','half':'趋势走弱半仓','premium':'月度换股、较高限价卖出','latch':'趋势走弱退出、等下次月度选股'}
    for name,arm in report['arms'].items():
        years=[pct(y['return_fraction'])+' / '+pct(y['maximum_close_drawdown']) for y in arm['years']]
        lines.append('| '+' | '.join([labels[name]]+years+[pct(arm['cagr'])+' / '+pct(arm['maximum_close_drawdown']),f"{float(F(arm['final_equity'])):,.2f}",str(arm['fills']),str(arm['fees']),f"{float(F(arm['turnover_gross_over_mean_close_nav'])):.2f}",pct(arm['cash_fraction_mean'])])+' |')
    lines+=['','| 方案 | 最大回撤峰日 → 谷日 | 最长水下交易日 | 结束仍未恢复 | 收盘持仓时间占比 |','|---|---|---:|---|---:|']
    for name,arm in report['arms'].items():
        lines.append('| '+' | '.join([labels[name],str(arm['maximum_drawdown_peak_date'])+' → '+str(arm['maximum_drawdown_trough_date']),str(arm['longest_underwater_close_sessions']),'是' if arm['end_still_underwater'] else '否',pct(arm['stock_held_close_fraction'])])+' |')
    return '\n'.join(lines)+'\n\n'+report['scope']+'\n'


def main():
    report=build()  # No output until COMPLETE and independent review passes.
    report['source_hashes'][str(Path(__file__).relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for name,expected in report['source_hashes'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('SOURCE_CHANGED_DURING_COMPARISON:'+name)
    output=ROOT/OUTPUT;output.mkdir(exist_ok=False)
    with (output/'comparison.json').open('x',encoding='utf-8') as file:json.dump(report,file,indent=2)
    with (output/'table.md').open('x',encoding='utf-8') as file:file.write(markdown(report))
    print(json.dumps(dict(status=report['status'],output=OUTPUT)))


if __name__=='__main__':main()
