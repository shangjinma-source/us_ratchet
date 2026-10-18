"""Read-only audited own-capital selector comparison; no strategy execution."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from scripts.compare_monthly_latched_exit import statistics, integer_text_limit

ROOT=Path(__file__).resolve().parents[1]
RUN='tmp/continuous_guided_monthly_book_20261016_v1'
BASE='tmp/daily_exclusion_B0_20261016_v1'
BASE_SHA='b60767394f091b5107186a01aa7747e0ef467407fc67f2901a410920ddf13e0f'
OUTPUT='tmp/continuous_guided_monthly_comparison_20261016_v1'
REVIEW_STATUS='PASS_SAVED_CONTINUOUS_GUIDED_REVIEW'
LABELS={'B0':'原选股搜索，每月换股','continuous32':'改进选股搜索，每月换股'}


def monthly_targets(outcome, expected_dates):
    """Decision-time targets, using each branch's own procurement prices/capital."""
    selections=[row['selection'] for row in outcome['provider_audit'] if row.get('selection') is not None]
    dates=[selection['decision_date'] for selection in selections]
    if dates!=expected_dates or len(set(dates))!=len(dates):
        raise ValueError('MONTHLY_SELECTION_DATES_MISMATCH')
    months=[]
    for selection in selections:
        binding=selection['binding'];args=binding['search_arguments'];selected=selection['search_result']['selected']
        capital=Fraction(args['entered_cash']);quantities=selected['quantities']
        if capital<=0 or binding['decision_date']!=selection['decision_date'] or Fraction(binding['investable_equity'])!=capital:
            raise ValueError('MONTHLY_CAPITAL_BINDING_MISMATCH')
        if selection['target_quantities']!=quantities or selected['actual_k']!=len(quantities):
            raise ValueError('MONTHLY_TARGET_MISMATCH')
        if set(selected['actual_weights'])!=set(quantities):raise ValueError('TARGET_WEIGHTS_MISMATCH')
        targets=[];notional=Fraction(0)
        for sid,quantity in sorted(quantities.items()):
            if type(quantity)is not int or quantity<=0:raise ValueError('INVALID_TARGET_QUANTITY')
            cost=Fraction(args['prices'][sid])*quantity;weight=cost/capital
            if weight!=Fraction(selected['actual_weights'][sid]):raise ValueError('TARGET_WEIGHTS_MISMATCH')
            ticker=args['metadata'][sid]['ticker']
            if not isinstance(ticker,str) or not ticker:raise ValueError('MISSING_TARGET_TICKER')
            targets.append(dict(security_id=sid,ticker=ticker,quantity=quantity,target_weight=str(weight)))
            notional+=cost
        fees=notional*Fraction(args['fee_bps'])/10000;cash=capital-notional-fees
        if cash<0 or Fraction(selected['notional'])!=notional or Fraction(selected['fees'])!=fees or Fraction(selected['residual_cash'])!=cash or Fraction(selected['cash_fraction'])!=cash/capital:
            raise ValueError('TARGET_CASH_OR_FEES_MISMATCH')
        months.append(dict(decision_date=selection['decision_date'],investable_equity=str(capital),actual_k=len(quantities),targets=targets,cash_fraction=str(cash/capital),fee_fraction=str(fees/capital)))
    weights=[Fraction(t['target_weight']) for row in months for t in row['targets']]
    return dict(months=months,concentration=dict(single_stock_months=sum(row['actual_k']==1 for row in months),multi_stock_months=sum(row['actual_k']>1 for row in months),all_cash_months=sum(row['actual_k']==0 for row in months),maximum_target_weight=str(max(weights,default=Fraction(0)))),scope='月度决策时目标，非每日实际持仓；权重以各分支当时独立可投资净值为分母。')


@integer_text_limit()
def build(root=ROOT):
    root=Path(root).resolve();pins={}
    def read(name,expected=None):
        path=(root/name).resolve()
        if not path.is_relative_to(root):raise ValueError('OUTSIDE_ROOT')
        raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest()
        if expected is not None and h!=expected:raise ValueError('SOURCE_HASH_MISMATCH')
        if name in pins and pins[name]!=h:raise ValueError('SOURCE_CHANGED')
        pins[name]=h;return json.loads(raw)
    implementation_paths=['scripts/compare_continuous_guided_monthly_book.py','scripts/compare_monthly_latched_exit.py','backtest/continuous_calendar_year_metrics.py']
    for name in implementation_paths:pins[name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
    review=read(RUN+'/independent_review_v1.json')
    if review['status']!=REVIEW_STATUS:raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    terminal=read(RUN+'/terminal.json');base_terminal=read(BASE+'/terminal.json')
    if any(t['status']!='COMPLETE' or t.get('source_pins_unchanged')is not True for t in (terminal,base_terminal)):
        raise ValueError('COMPLETE_UNCHANGED_TERMINALS_REQUIRED')
    pre=read(RUN+'/preflight.json');base_pre=read(BASE+'/preflight.json')
    for receipt in (pre,base_pre):
        if [receipt[k] for k in ('initial_cash','fee_bps','slippage_bps')]!=['20000','0','0']:
            raise ValueError('ECONOMIC_PARAMETERS_MISMATCH')
    if pre['prepared_sha256']!=base_pre['prepared_sha256'] or pre.get('continuous_iterations')!=32:
        raise ValueError('COMPARABLE_PREPARATION_REQUIRED')
    for name,h in pre['source_hashes'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=h:
            raise ValueError('SOURCE_DRIFT')
        if name in pins and pins[name]!=h:raise ValueError('SOURCE_PIN_CONFLICT')
        pins[name]=h
    prepared=read(pre['prepared_path'],pre['prepared_sha256']);sessions=prepared['session_dates']
    candidate=read(RUN+'/outcome.json',review['outcome_sha256']);baseline=read(BASE+'/outcome.json',BASE_SHA)
    arms={};targets={}
    expected_dates=[window['decision_date'] for window in prepared['windows']]
    for name,outcome in [('B0',baseline),('continuous32',candidate)]:
        if any(row['event']=='ASSUMED_INTRADAY_LIMIT_FILLED' for row in outcome['order_log']):
            raise ValueError('WRONG_EXECUTION_MODEL')
        arms[name]=statistics(outcome,sessions)
        targets[name]=monthly_targets(outcome,expected_dates)
    for name in implementation_paths:
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=pins[name]:raise ValueError('STATISTICS_IMPLEMENTATION_CHANGED')
    old,new=arms['B0'],arms['continuous32']
    # Same positive capital and exact dates: terminal wealth ordering equals CAGR
    # ordering, without comparing rounded percentages or transcendental floats.
    return dict(schema='AUDITED_CONTINUOUS_GUIDED_MONTHLY_COMPARISON_V1',status='VERIFIED_INPUTS_COMPARISON',
        labels=LABELS,monthly_target_comparison=targets,opening_date=sessions[0],through=sessions[-1],initial_cash='20000',arms=arms,
        joint_improvement_against_B0=Fraction(new['final_equity'])>=Fraction(old['final_equity'])
            and Fraction(new['maximum_close_drawdown'])<Fraction(old['maximum_close_drawdown']),
        automatic_promotion=False,selector_only_changed=True,current_intraday_policy_performance=False,
        equal_computation_budget_comparison=False,independent_oos=False,
        turnover_definition='BUY+SELL gross / arithmetic mean daily close NAV; not annualized',
        scope='只改变选股搜索；两者均每月换股、次日开盘执行。条件历史价格、剔除TRI观察域、非完整PIT认证、非独立样本外；模型费滑点为零，其他费用未知。2026只报告截至共同终点的期间收益。',
        source_hashes=pins)


@integer_text_limit()
def markdown(report):
    pct=lambda v:f'{float(Fraction(str(v)))*100:.2f}%'
    years=report['arms']['B0']['years']
    headers=[str(y['year'])+('截至'+y['through'] if y['year']==2026 else '')+'收益 / 回撤' for y in years]
    lines=['| '+' | '.join(['方案']+headers+['整段年化 / 回撤','期末美元','成交笔数','双向换手倍数','平均现金占比'])+' |',
           '| '+' | '.join(['---']+['---:']*(len(headers)+5))+' |']
    for name,arm in report['arms'].items():
        values=[pct(y['return_fraction'])+' / '+pct(y['maximum_close_drawdown']) for y in arm['years']]
        values += [pct(arm['cagr'])+' / '+pct(arm['maximum_close_drawdown']),f"{float(Fraction(arm['final_equity'])):,.2f}",
                   str(arm['fills']),f"{float(Fraction(arm['turnover_gross_over_mean_close_nav'])):.2f}",pct(arm['cash_fraction_mean'])]
        lines.append('| '+' | '.join([LABELS[name]]+values)+' |')
    lines += ['', '月度目标（非每日实际持仓；各分支使用自己的决策净值）', '', '| 决策日期 | 原方案目标 / k / 现金 | 新方案目标 / k / 现金 |', '| --- | --- | --- |']
    target_report=report['monthly_target_comparison']
    for old,new in zip(target_report['B0']['months'],target_report['continuous32']['months']):
        cells=[]
        for row in (old,new):
            positions='、'.join(t['ticker']+' '+pct(t['target_weight']) for t in row['targets']) or '全现金'
            cells.append(positions+' / '+str(row['actual_k'])+' / '+pct(row['cash_fraction']))
        lines.append('| '+old['decision_date']+' | '+' | '.join(cells)+' |')
    for name,data in target_report.items():
        c=data['concentration']
        lines.append('\n'+LABELS[name]+'：单股 '+str(c['single_stock_months'])+' 月，多股 '+str(c['multi_stock_months'])+' 月，全现金 '+str(c['all_cash_months'])+' 月，最大单股目标权重 '+pct(c['maximum_target_weight'])+'。')
    return '\n'.join(lines)+'\n\n'+report['scope']+'\n\n联合改善：'+('是' if report['joint_improvement_against_B0'] else '否')+'。不自动替换当前策略。\n'


def main():
    report=build()
    report['source_hashes'][Path(__file__).relative_to(ROOT).as_posix()]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for name,h in report['source_hashes'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_CHANGED_DURING_COMPARISON')
    output=ROOT/OUTPUT;output.mkdir(exist_ok=False)
    with integer_text_limit(),(output/'comparison.json').open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,ensure_ascii=False)
    with (output/'table.md').open('x',encoding='utf8') as stream:stream.write(markdown(report))
    print(json.dumps(dict(status=report['status'],output=OUTPUT)))


if __name__=='__main__':main()
