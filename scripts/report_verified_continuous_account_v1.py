"""Report only complete independently reviewed frozen accounts; no economic execution."""
import argparse
from datetime import date
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.report_recent_verified_baseline import drawdown


def build_report(book,wrapper,document,initial_equity='20000'):
    original=document.get('baseline_execution_inputs',document)
    assembled=original['assembled'];sessions=assembled['session_dates'];plans=assembled['monthly_inputs']
    scopes={('2020-12-31','2023-12-29'):36,('2023-12-29','2026-07-30'):31}
    count=scopes.get((sessions[0],sessions[-1]))
    if not count or len(plans)!=count or book['status']!='COMPLETE':
        raise ValueError('FULL_FROZEN_INTERVAL_REQUIRED_NO_PREFIX_ANNUALIZATION')
    dates=[p['decision_date'] for p in plans]
    start=date.fromisoformat(sessions[0]);ordinal=start.year*12+start.month
    if (dates!=sorted(set(dates)) or dates[0]!=sessions[0] or any(d not in sessions[:-1] for d in dates)
            or [date.fromisoformat(d).year*12+date.fromisoformat(d).month for d in dates]!=list(range(ordinal,ordinal+count))):
        raise ValueError('COMPLETE_MONTHLY_DECISION_DOMAIN_REQUIRED')
    rows=book['daily_ledger'];proof=wrapper['proof']
    if wrapper['status']!='COMPLETE_DECLARED_INTERVAL_REVIEW_PASS' or wrapper.get('pending_decision_dates'):
        raise ValueError('COMPLETE_REVIEW_REQUIRED')
    if (sessions!=sorted(set(sessions)) or [r['date'] for r in rows]!=sessions[1:]
            or len(book['provider_audit'])!=len(rows)):
        raise ValueError('FULL_LEDGER_AND_PROVIDER_COVERAGE_REQUIRED')
    if (proof['status']!='REVIEWED_ORDINARY_DIVIDEND_ACCOUNT' or not proof['costs_checked']
            or not proof['risk_provider_certified'] or not proof['selection_proof_checked']
            or proof['selection_proofs_checked']!=count or proof['expected_selection_proofs']!=count
            or proof['risk_sessions_checked']!=len(rows)):
        raise ValueError('FULL_SELECTION_AND_RISK_REVIEW_REQUIRED')
    initial=F(initial_equity)
    if initial!=20000 or any(F(r['equity'])<=0 or F(r.get('external_flow','0')) for r in rows):
        raise ValueError('FROZEN_POSITIVE_NO_EXTERNAL_FLOW_ACCOUNT_REQUIRED')
    path=[dict(date=sessions[0],equity=str(initial))]+rows
    dd=drawdown(path);final=F(rows[-1]['equity']);total=final/initial-1
    if (F(proof['final_equity'])!=final or F(proof['maximum_drawdown'])!=F(dd['maximum_drawdown'])
            or F(book['total_return'])!=total or F(book['drawdown']['maximum_close_drawdown'])!=F(dd['maximum_drawdown'])):
        raise ValueError('REVIEW_AND_BOOK_METRICS_MISMATCH')
    annual=[];previous=path[0]
    for year in sorted({int(r['date'][:4]) for r in rows}):
        part=[r for r in rows if int(r['date'][:4])==year]
        annual.append(dict(year=year,start_date=previous['date'],end_date=part[-1]['date'],
            partial_calendar_year=year==2026,return_fraction=str(F(part[-1]['equity'])/F(previous['equity'])-1),
            maximum_drawdown=drawdown([previous]+part)['maximum_drawdown']))
        previous=part[-1]
    days=(date.fromisoformat(sessions[-1])-start).days
    fills=[r for r in book['order_log'] if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED']
    return dict(status='COMPLETE_VERIFIED_ACCOUNT_REPORT',start_date=sessions[0],end_date=sessions[-1],
        initial_equity=str(initial),final_equity=str(final),total_return=str(total),
        cagr=float(final/initial)**(365.25/days)-1,cagr_definition='ACTUAL_CALENDAR_DAYS_DIVIDED_BY_365.25',
        drawdown=dd,annual=annual,filled_order_count=len(fills),buy_count=sum(r['side']=='BUY' for r in fills),
        sell_count=sum(r['side']=='SELL' for r in fills),decision_count=count,execution_sessions=len(rows),
        limitations=['Conditional historical research; not independent out-of-sample or actual account returns.',
                    'Closing-equity drawdown; year drawdowns reset at prior year-end. 2026 ends July 30, not full year.',
                    'Gross dividends, original cost and next-open execution assumptions remain applicable.'])


def markdown(report):
    pct=lambda value:f'{float(F(str(value)))*100:.2f}%'
    lines=['# 完整连续研究账户报告','',f"区间 {report['start_date']} 至 {report['end_date']}；期末 ${float(F(report['final_equity'])):,.2f}。",'',
        f"年化 {pct(report['cagr'])}；最大收盘回撤 {pct(report['drawdown']['maximum_drawdown'])}；累计收益 {pct(report['total_return'])}。",'',
        '| 年度区间 | 收益 | 区间最大回撤 |','|---|---:|---:|']
    for row in report['annual']:
        label=f"{row['year']}（截至 {row['end_date']}，非全年）" if row['partial_calendar_year'] else str(row['year'])
        lines.append(f"| {label} | {pct(row['return_fraction'])} | {pct(row['maximum_drawdown'])} |")
    lines+=['',f"成交 {report['filled_order_count']} 笔：买入 {report['buy_count']}，卖出 {report['sell_count']}。",'',
            '仅为原成本、税前股息及次开盘假设下的条件性历史研究。年度回撤各自重置峰值，不能直接比较为全区间回撤。']
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('book','inputs','review','output'):parser.add_argument('--'+name,type=Path,required=True)
    options=parser.parse_args();documents={};hashes={}
    for name in ('book','inputs','review'):
        raw=getattr(options,name).read_bytes();documents[name]=json.loads(raw);hashes[name]=sha256(raw).hexdigest()
    wrapper=documents['review']
    for name in ('book','inputs'):
        expected=getattr(options,name).resolve()
        matches=[value for filename,value in wrapper['source_hashes'].items() if (ROOT/filename).resolve()==expected]
        if matches!=[hashes[name]]:raise ValueError('EXACT_REVIEW_SOURCE_HASH_REQUIRED:'+name)
    result=build_report(documents['book'],wrapper,documents['inputs']);result['input_hashes']=hashes
    options.output.parent.mkdir(parents=True,exist_ok=True)
    for suffix,text in (('.json',json.dumps(result,indent=2)),('.md',markdown(result))):
        with options.output.with_suffix(suffix).open('x',encoding='utf-8') as stream:stream.write(text)
    print(json.dumps(dict(status=result['status'],cagr=result['cagr'],maximum_drawdown=result['drawdown']['maximum_drawdown'])))

if __name__=='__main__':main()
