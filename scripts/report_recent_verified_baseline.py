"""One-page report of a complete reviewed account; no search or book execution."""
import argparse
from datetime import date
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path


def drawdown(rows):
    peak = F(rows[0]['equity']); peak_day = rows[0]['date']
    worst = F(0); worst_peak = peak_day; trough = peak_day; peak_value = peak
    for row in rows:
        value = F(row['equity'])
        if value >= peak:
            peak, peak_day = value, row['date']
        loss = 1-value/peak
        if loss > worst:
            worst, worst_peak, trough, peak_value = loss, peak_day, row['date'], peak
    recovery = next((r['date'] for r in rows if r['date'] > trough and F(r['equity']) >= peak_value), None) if worst else rows[0]['date']
    return dict(maximum_drawdown=str(worst), peak_date=worst_peak, trough_date=trough,
                recovery_date=recovery, recovery_calendar_days=None if recovery is None else (date.fromisoformat(recovery)-date.fromisoformat(worst_peak)).days)


def build_report(book, review, assembled, *, initial_equity, market_context=None):
    sessions = assembled['session_dates']; plans = assembled['monthly_inputs']
    if book['status'] != 'COMPLETE' or sessions[0] != '2020-12-31' or sessions[-1] != '2023-12-29' or len(plans) != 36:
        raise ValueError('FULL_36_MONTH_REPORT_REQUIRED_NO_PARTIAL_ANNUALIZATION')
    if len({p['decision_date'] for p in plans}) != 36:
        raise ValueError('DUPLICATE_MONTHLY_PLAN')
    expected_months = {(2020,12)} | {(y,m) for y in (2021,2022,2023) for m in range(1,13) if (y,m)!=(2023,12)}
    if {(int(p['decision_date'][:4]),int(p['decision_date'][5:7])) for p in plans} != expected_months:
        raise ValueError('MONTHLY_PLAN_DOMAIN')
    ledger = book['daily_ledger']
    if [r['date'] for r in ledger] != sessions[1:] or sessions != sorted(set(sessions)):
        raise ValueError('SESSION_COVERAGE')
    if (review['status'] != 'REVIEWED_ORDINARY_DIVIDEND_ACCOUNT' or not review['costs_checked']
            or not review['risk_provider_certified'] or not review['selection_proof_checked']
            or review['selection_proofs_checked'] != 36 or review['expected_selection_proofs'] != 36):
        raise ValueError('FULL_INDEPENDENT_REVIEW_REQUIRED')
    if any(F(r.get('external_flow','0')) != 0 for r in ledger):
        raise ValueError('EXTERNAL_FLOW_REQUIRES_DIFFERENT_RETURN_METHOD')
    initial=F(initial_equity)
    if initial<=0 or any(F(r['equity'])<=0 for r in ledger):raise ValueError('POSITIVE_EQUITY_REQUIRED')
    path=[dict(date=sessions[0],equity=str(initial))]+ledger
    dd=drawdown(path); end=F(ledger[-1]['equity']); total=end/initial-1
    if F(review['final_equity'])!=end or F(review['maximum_drawdown'])!=F(dd['maximum_drawdown']) or F(book['total_return'])!=total:
        raise ValueError('REVIEW_PERFORMANCE_MISMATCH')
    years=[]; previous=path[0]
    for year in (2021,2022,2023):
        rows=[r for r in ledger if r['date'].startswith(str(year))]
        if not rows:raise ValueError('YEAR_MISSING')
        local=drawdown([previous]+rows)
        years.append(dict(year=year,start_date=previous['date'],end_date=rows[-1]['date'],
            return_fraction=str(F(rows[-1]['equity'])/F(previous['equity'])-1),
            within_year_maximum_drawdown=local['maximum_drawdown']))
        previous=rows[-1]
    days=(date.fromisoformat(sessions[-1])-date.fromisoformat(sessions[0])).days
    return dict(status='COMPLETE_REVIEWED_RESEARCH_REPORT',initial_equity=str(initial),final_equity=str(end),
        start_date=sessions[0],end_date=sessions[-1],calendar_days=days,total_return=str(total),
        cagr=float(end/initial)**(365.25/days)-1,cagr_definition='ACTUAL_CALENDAR_DAYS_DIVIDED_BY_365.25',
        drawdown=dd,annual=years,market_context=market_context,
        limitations=['Close-equity drawdown, not intraday drawdown. Annual drawdown restarts peak at preceding year-end.',
            'QQQ context is dividend-excluded price return, not a same-cost executable benchmark.',
            'Research account assumptions and data limitations remain applicable; no strategy superiority claim.'])


def markdown(report):
    percent=lambda x:f'{float(F(str(x)))*100:.2f}%'
    lines=['# 连续研究账户复核报告','',f"区间：{report['start_date']} 至 {report['end_date']}；初始 ${float(F(report['initial_equity'])):,.2f}，期末 ${float(F(report['final_equity'])):,.2f}。",'',
        '| 年份 | 账户收益 | 年内收盘最大回撤 | QQQ价格涨跌（仅环境） |','|---|---:|---:|---:|']
    context={r['year']:r for r in (report.get('market_context') or {}).get('rows',[])}
    for row in report['annual']:
        q=context.get(row['year']); value=f"{q['price_return_percent']:.2f}%" if q else '未提供'
        lines.append(f"| {row['year']} | {percent(row['return_fraction'])} | {percent(row['within_year_maximum_drawdown'])} | {value} |")
    dd=report['drawdown']
    lines += ['',f"全区间累计收益 {percent(report['total_return'])}，年化 {percent(report['cagr'])}（实际天数/365.25），最大收盘回撤 {percent(dd['maximum_drawdown'])}。",'',
        f"最大回撤：峰值 {dd['peak_date']} → 谷底 {dd['trough_date']}；恢复日期：{dd['recovery_date'] or '区间内未恢复'}。",'',
        'QQQ列不含股息、交易成本，仅说明市场环境。账户结果以原研究的股息、税费及执行假设为准；年内回撤以各年初重新计算峰值。', '',
        '采用同策略核心的历史次日开盘模型；不等同实盘逐笔成交，也不等同当前账户启动时点。']
    if report.get('gross_dividends_research'):
        lines += ['', '普通股息按官方历史金额计入，未扣投资者预提税；这是税前研究收益，不代表汇丰账户税后收益或个人税率。']
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('book','review','assembled','drawdown-path','market-context','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--initial-equity',default='20000')
    options=p.parse_args();inputs={}
    for name in ('book','review','assembled','drawdown_path','market_context'):
        path=getattr(options,name);raw=path.read_bytes();inputs[name]=(json.loads(raw),sha256(raw).hexdigest())
    def check_binding(document, name):
        matches=[value for path,value in document['source_hashes'].items() if Path(path).resolve()==getattr(options,name).resolve()]
        if matches != [inputs[name][1]]:raise ValueError('SOURCE_BINDING_MISMATCH:'+name)
    reviewed=inputs['review'][0]; diagnostic=inputs['drawdown_path'][0]
    for name in ('book','assembled'):check_binding(reviewed,name)
    for name in ('book','review'):check_binding(diagnostic,name)
    if reviewed['end']!='2023-12-29' or reviewed.get('pending_decision_dates'):
        raise ValueError('PARTIAL_REVIEW_NOT_FULL_REPORT')
    document=inputs['assembled'][0];assembled=document.get('assembled',document)
    result=build_report(inputs['book'][0],reviewed['proof'],assembled,initial_equity=options.initial_equity,market_context=inputs['market_context'][0])
    result['gross_dividends_research']=bool(document.get('gross_dividends_research'))
    result['execution_assumption']=document.get('execution_assumption')
    for key in ('maximum_drawdown','peak_date','trough_date','recovery_date'):
        if diagnostic['drawdown'][key]!=result['drawdown'][key]:raise ValueError('DRAWDOWN_PATH_MISMATCH:'+key)
    for computed,saved in zip(result['annual'],diagnostic['calendar_year_intervals']):
        if not saved['complete_calendar_year_in_frozen_calendar'] or computed['year']!=saved['year'] or F(computed['return_fraction'])!=F(saved['interval_return']) or F(computed['within_year_maximum_drawdown'])!=F(saved['maximum_drawdown']):
            raise ValueError('YEAR_DIAGNOSTIC_MISMATCH')
    if len(diagnostic['calendar_year_intervals'])!=3:raise ValueError('THREE_FULL_YEARS_REQUIRED')
    result['input_hashes']={k:v[1] for k,v in inputs.items()};result['review_binding']='INDEPENDENT_REVIEW_AND_DRAWDOWN_SOURCE_HASHES'
    result['limitations'].append('Same strategy core under historical next-open execution; not equivalent to live tick execution or current account startup epoch.')
    options.output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    options.output.with_suffix('.md').write_text(markdown(result),encoding='utf-8')


if __name__=='__main__':main()
