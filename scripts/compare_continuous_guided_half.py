"""Read-only three-arm comparison; no selector, book or network invocation."""
import hashlib,json
from pathlib import Path
from fractions import Fraction as F
from scripts.compare_monthly_latched_exit import statistics,integer_text_limit

ROOT=Path(__file__).resolve().parents[1]
RUN='tmp/continuous_guided_half_exposure_20261016_v1'
OUTPUT='tmp/continuous_guided_half_comparison_20261016_v2'
OLD='tmp/continuous_guided_monthly_comparison_20261016_v1/comparison.json'
OLD_SHA='abdbf7d37d506391195fbd5dcfe8b42fe401a4c2b368df736b887052a15ded5d'
SEALED={'B0':('tmp/daily_exclusion_B0_20261016_v1/outcome.json','b60767394f091b5107186a01aa7747e0ef467407fc67f2901a410920ddf13e0f'),
        'continuous32':('tmp/continuous_guided_monthly_book_20261016_v1/outcome.json','17432bad6c5e1a88205efd94a7bc12bd92228bbb483ad0c863a48a74bb7ed71b')}
REVIEW_STATUS='PASS_SAVED_CONTINUOUS_GUIDED_HALF_REVIEW'
LABELS={'B0':'原选股，每月换股','continuous32':'新候选搜索，每月换股','continuous32_half':'新候选搜索，趋势走弱半仓'}


def overlay_activity(outcome):
    previous={};events=[];off=set();on_days=off_days=0;tickers={};fills={r['id']:r for r in outcome['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED'}
    for row in outcome['provider_audit']:
        selection=row.get('selection')
        if selection:
            tickers.update({sid:meta['ticker'] for sid,meta in selection['binding']['search_arguments']['metadata'].items()})
        risk=row.get('risk_overlay')
        if not risk:continue
        monthly=risk['monthly_decision_date'] if 'monthly_decision_date' in risk else row['target_decision_date']
        for sid,d in risk['diagnostics'].items():
            on=d['on'];key=(monthly,sid)
            if on:on_days+=1
            else:off_days+=1;off.add(sid)
            if key in previous and previous[key]!=on:
                side='BUY' if on else 'SELL'
                orders=[o for o in row['orders'] if o['security_id']==sid and o['side']==side]
                events.append(dict(kind='RECOVERY' if on else 'REDUCTION',security_id=sid,
                    signal_date=risk['signal_date'],monthly_decision_date=monthly,
                    order_ids=[o['id'] for o in orders],filled_order_ids=[o['id'] for o in orders if o['id'] in fills]))
            previous[key]=on
    return dict(reduction_signals=sum(e['kind']=='REDUCTION' for e in events),recovery_signals=sum(e['kind']=='RECOVERY' for e in events),
        reduction_fills=sum(len(e['filled_order_ids']) for e in events if e['kind']=='REDUCTION'),recovery_fills=sum(len(e['filled_order_ids']) for e in events if e['kind']=='RECOVERY'),
        off_state_security_ids=sorted(off),off_state_tickers={sid:tickers.get(sid,sid) for sid in sorted(off)},full_signal_stock_days=on_days,half_signal_stock_days=off_days,events=events,
        definition='Within unchanged monthly decision and SID, ON to OFF / OFF to ON transitions; initial OFF or monthly resets are not counted as reductions/recoveries. Fills count only order IDs generated in the transition row with the matching side. This is temporal linkage, not exclusive causal attribution to risk control; quantities may also reflect prior execution shortfalls or unit migrations.')


def year_window(outcome,year):
    rows=outcome['daily_ledger'];selected=[r for r in rows if r['date'].startswith(str(year))]
    prior=[r for r in rows if r['date']<str(year)]
    if not selected or not prior:raise ValueError('YEAR_WINDOW_BASE_REQUIRED')
    peak=F(prior[-1]['equity']);peak_day=prior[-1]['date'];worst=F(0);peak_at=trough_at=peak_day
    for row in selected:
        value=F(row['equity'])
        if value>=peak:peak=value;peak_day=row['date']
        dd=1-value/peak
        if dd>worst:worst=dd;peak_at=peak_day;trough_at=row['date']
    return dict(peak_date=peak_at,trough_date=trough_at,maximum_close_drawdown=str(worst))


@integer_text_limit()
def build(root=ROOT):
    root=Path(root).resolve();pins={}
    def read(name,expected=None):
        p=(root/name).resolve()
        if not p.is_relative_to(root):raise ValueError('OUTSIDE_ROOT')
        raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest()
        if expected is not None and expected!=h:raise ValueError('HASH_MISMATCH')
        if name in pins and pins[name]!=h:raise ValueError('SOURCE_CONFLICT')
        pins[name]=h;return json.loads(raw)
    old=read(OLD,OLD_SHA)
    if old['status']!='VERIFIED_INPUTS_COMPARISON':raise ValueError('OLD_COMPARISON_NOT_VERIFIED')
    review=read(RUN+'/independent_review_v1.json')
    if review['status']!=REVIEW_STATUS:raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    terminal=read(RUN+'/terminal.json')
    if terminal['status']!='COMPLETE' or terminal.get('source_pins_unchanged')is not True:raise ValueError('COMPLETE_REQUIRED')
    pre=read(RUN+'/preflight.json');original=read('tmp/continuous_guided_monthly_book_20261016_v1/preflight.json')
    for p in (pre,original):
        if [p[k] for k in ('initial_cash','fee_bps','slippage_bps','continuous_iterations')]!=['20000','0','0',32]:raise ValueError('PARAMETERS_DIFFER')
    if pre['prepared_sha256']!=original['prepared_sha256'] or pre['search_parameters']!=original['search_parameters']:raise ValueError('PREPARATION_OR_BUDGET_DIFFER')
    for name,h in {**old['source_hashes'],**pre['source_hashes']}.items():
        if name in old['source_hashes'] and name in pre['source_hashes'] and old['source_hashes'][name]!=h:raise ValueError('PIN_CONFLICT')
        p=(root/name).resolve()
        if not p.is_relative_to(root) or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_DRIFT')
        pins[name]=h
    for name in ('scripts/compare_continuous_guided_half.py','scripts/compare_monthly_latched_exit.py','backtest/continuous_calendar_year_metrics.py'):
        h=hashlib.sha256((root/name).read_bytes()).hexdigest()
        if name in pins and pins[name]!=h:raise ValueError('IMPLEMENTATION_CHANGED')
        pins[name]=h
    prepared=read(pre['prepared_path'],pre['prepared_sha256']);sessions=prepared['session_dates']
    outcomes={name:read(p,h) for name,(p,h) in SEALED.items()}
    outcomes['continuous32_half']=read(RUN+'/outcome.json',review['outcome_sha256'])
    arms={}
    for key,out in outcomes.items():
        if any(r['event']=='ASSUMED_INTRADAY_LIMIT_FILLED' for r in out['order_log']):raise ValueError('WRONG_FILL_MODEL')
        arms[key]=statistics(out,sessions)
        if key in old['arms'] and arms[key]!=old['arms'][key]:raise ValueError('OLD_METRICS_DIFFER')
    new=arms['continuous32_half']
    comparisons={key:dict(joint_improvement=F(new['final_equity'])>=F(arms[key]['final_equity']) and F(new['maximum_close_drawdown'])<F(arms[key]['maximum_close_drawdown']),
        ending_equity_difference=str(F(new['final_equity'])-F(arms[key]['final_equity'])),drawdown_difference=str(F(new['maximum_close_drawdown'])-F(arms[key]['maximum_close_drawdown']))) for key in ('continuous32','B0')}
    windows={key:year_window(out,2026) for key,out in outcomes.items()}
    reference=windows['continuous32'];fixed={}
    for key,out in outcomes.items():
        values={r['date']:F(r['equity']) for r in out['daily_ledger']}
        fixed[key]=str(values[reference['trough_date']]/values[reference['peak_date']]-1)
    for name,h in pins.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_CHANGED_DURING_BUILD')
    return dict(status='VERIFIED_INPUTS_COMPARISON',schema='CONTINUOUS32_HALF_THREE_ARM_V1',labels=LABELS,arms=arms,primary_comparator='continuous32',comparisons=comparisons,
        overlay_activity=overlay_activity(outcomes['continuous32_half']),descriptive_2026=dict(own_year_drawdown_windows=windows,continuous32_peak_to_trough_return_each_arm=fixed,reference_window=reference,not_primary_acceptance=True),
        initial_cash='20000',opening_date=sessions[0],through=sessions[-1],source_hashes=pins,automatic_promotion=False,
        scope='固定样本、条件性历史价格、非完整PIT/非独立样本外。初始20000美元，零模型费用滑点；2026只报告期间收益。主比较新搜索加半仓对新搜索；旧B0另列。2026窗口仅描述，不代替全期回撤。')


@integer_text_limit()
def markdown(report):
    pct=lambda v:f'{float(F(str(v)))*100:.2f}%'
    lines=['| 方案 | 2024收益/回撤 | 2025收益/回撤 | 2026期间收益/回撤 | 全段年化/回撤 | 期末美元 | 换手倍数 | 平均现金 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for key,arm in report['arms'].items():
        row=[LABELS[key]]+[pct(y['return_fraction'])+'/'+pct(y['maximum_close_drawdown']) for y in arm['years']]+[pct(arm['cagr'])+'/'+pct(arm['maximum_close_drawdown']),f"{float(F(arm['final_equity'])):,.2f}",f"{float(F(arm['turnover_gross_over_mean_close_nav'])):.2f}",pct(arm['cash_fraction_mean'])]
        lines.append('| '+' | '.join(row)+' |')
    for key,c in report['comparisons'].items():lines.append('\n相对'+LABELS[key]+'联合改善：'+('是' if c['joint_improvement'] else '否')+'。')
    activity=report['overlay_activity'];lines.append('\n同月减仓/回补信号：'+str(activity['reduction_signals'])+'/'+str(activity['recovery_signals'])+'；切换时生成的同向订单成交：'+str(activity['reduction_fills'])+'/'+str(activity['recovery_fills'])+'。')
    lines.append('全仓/半仓信号股票日数：'+str(activity['full_signal_stock_days'])+'/'+str(activity['half_signal_stock_days'])+'；以上成交关联不是独占风控归因。')
    return '\n'.join(lines)+'\n\n'+report['scope']+'\n'


def main():
    report=build();output=ROOT/OUTPUT;output.mkdir(exist_ok=False)
    with integer_text_limit(),(output/'comparison.json').open('x',encoding='utf8') as f:json.dump(report,f,indent=2,ensure_ascii=False)
    with (output/'table.md').open('x',encoding='utf8') as f:f.write(markdown(report))


if __name__=='__main__':main()
