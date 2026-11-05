"""Audit-gated fixed momentum comparison; all three early cash-release scenarios required."""
import argparse
import json
import sys
from fractions import Fraction as F
from datetime import date
from pathlib import Path
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.research.summarize_downside_max10_20261105 import read,verify,pinned_book,verify_qqq,require,READ_HASHES
from scripts.research.summarize_cross_month_held_peak_20261105 import metrics
from scripts.research.summarize_ema20_market_20261105 import experience

# Exact schema produced by the independent reviewer, not a local synthetic pass.
AUDIT_STATUS='INDEPENDENT_MOMENTUM_ACCOUNT_PASS'
EXPECTED_PINS={}

def retain_pins(pins):
    verify(pins)
    for name,digest in pins.items():
        canonical=(ROOT/name).resolve().relative_to(ROOT).as_posix()
        require(canonical not in EXPECTED_PINS or EXPECTED_PINS[canonical]==digest,'SUMMARY_SOURCE_PIN_CONFLICT')
        EXPECTED_PINS[canonical]=digest


def validate_candidate_audit(folder,book,window,delay,sessions,months):
    audit=read(folder/'independent_review.json')
    require(audit['status']==AUDIT_STATUS,'UNREVIEWED_AUDIT_PASS_REQUIRED')
    require(audit['window']==window and audit['delay_sessions']==delay,'AUDIT_SCENARIO_MISMATCH')
    require(audit['sessions']==sessions and audit['monthly_targets']==months,'AUDIT_COUNTS_MISMATCH')
    fills=sum(r.get('event')=='ASSUMED_NEXT_OPEN_FILLED' for r in book['order_log'])
    require(audit['trades_checked']==fills,'AUDIT_FILL_COUNT_MISMATCH')
    pinned_book(audit,folder/'book.json');retain_pins(audit['source_hashes'])
    require(audit['book_sha256']==sha256((folder/'book.json').read_bytes()).hexdigest(),'AUDIT_BOOK_SHA_MISMATCH')
    require(F(audit['final_equity'])==F(book['daily_ledger'][-1]['equity']) and
            F(audit['maximum_drawdown'])==F(book['drawdown']['maximum_close_drawdown']),'AUDIT_FINANCIAL_ENDPOINTS')
    document=read(folder/'execution_inputs.json')['document']
    days=[p['decision_date'] for p in document['assembled']['monthly_inputs']]
    require(len(days)==months and len(set(days))==months,'AUDIT_EXPECTED_MONTHS')
    required=[folder/n for n in ('book.json','contract.json','execution_inputs.json','summary.json')]
    required += [folder/(day+suffix) for day in days for suffix in ('.selection.json','.exposure.json')]
    required += [ROOT/'scripts/research/review_momentum_account_20261105.py',ROOT/'backtest/research_exact_fraction_json.py']
    normalized={str((ROOT/n).resolve()):h for n,h in audit['source_hashes'].items()}
    for path in required:
        require(normalized.get(str(path.resolve()))==sha256(path.read_bytes()).hexdigest(),'AUDIT_REQUIRED_INPUT_BINDING:'+str(path))


def measure(rows,start,orders=None):
    fills=None if orders is None else [r for r in orders if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED']
    result=metrics(rows,start,1 if fills is None else len(fills))
    result['experience']=experience(rows,start)
    years=F((date.fromisoformat(rows[-1]['date'])-date.fromisoformat(start)).days,1)/F('365.25')
    require(years>0,'POSITIVE_MEASUREMENT_DURATION')
    average_equity=sum((F(r['equity']) for r in rows),F(0))/len(rows)
    require(average_equity>0,'POSITIVE_AVERAGE_EQUITY')
    gross=None if fills is None else sum((F(r['quantity'])*F(r['price']) for r in fills),F(0))
    result['turnover']=dict(gross_traded_notional=None if gross is None else float(gross),
                           gross_traded_notional_exact=None if gross is None else str(gross),
                           average_daily_account_equity=float(average_equity),calendar_years=float(years),
                           annualized_gross_turnover=None if gross is None else float(gross/average_equity/years),
                           definition='Both BUY and SELL fill notional at actual fill price, divided by mean session-close account equity and elapsed calendar days/365.25; not one-way turnover.',
                           unavailable_reason='QQQ ledger-only call lacks a bound fill record; no guessed notional.' if gross is None else None)
    result['return_pct']=float(F(rows[-1]['equity'])/20000-1)*100
    holdings=[sum(F(q)>0 for q in r['shares'].values()) if isinstance(r['shares'],dict) else int(r['shares']>0) for r in rows]
    result['maximum_actual_holdings']=max(holdings)
    result['cash_only_sessions']=holdings.count(0)
    result['calendar_periods']={}
    previous,day=F(20000),start
    for year in sorted({r['date'][:4] for r in rows}):
        subset=[r for r in rows if r['date'].startswith(year)]
        normalized=[dict(date=r['date'],equity=F(r['equity'])*20000/previous) for r in subset]
        count=int(year==rows[0]['date'][:4]) if fills is None else sum(r['date'].startswith(year) for r in fills)
        period=metrics(normalized,day,count)
        period.update(start_equity=float(previous),end_equity=float(F(subset[-1]['equity'])),return_pct=float(F(subset[-1]['equity'])/previous-1)*100,
                      partial=year=='2026',normalized_terminal_base=20000)
        period['experience']=experience(normalized,day)
        result['calendar_periods'][year]=period;previous=F(subset[-1]['equity']);day=subset[-1]['date']
    if rows[-1]['date'].startswith('2026'):
        subset=[r for r in rows if r['date']<='2025-12-31']
        subset_orders=None if orders is None else [r for r in orders if r['date']<='2025-12-31']
        result['excluding_2026']=measure(subset,start,subset_orders)
    return result


def benchmarks(window):
    name='recent_continuous_baseline_20261026_v7' if window=='2021_2023' else 'old_continuous_baseline_20261026_v9'
    folder=ROOT/'tmp'/name;book=read(folder/'book.json');audit=read(folder/'independent_prefix_review.json')
    document=read(folder/'execution_inputs.json');dates=document['assembled']['session_dates']
    sessions,months=(753,36) if window=='2021_2023' else (646,31)
    require(book['status']=='COMPLETE' and audit['status']=='COMPLETE_DECLARED_INTERVAL_REVIEW_PASS','BASELINE_COMPLETE_AUDIT')
    require(audit['executed_sessions']==sessions and audit['proof']['selection_proofs_checked']==months,'BASELINE_AUDIT_COUNTS')
    require(not audit['pending_decision_dates'] and not audit['unexecuted_selection_dates'],'BASELINE_PENDING')
    pinned_book(audit,folder/'book.json');retain_pins(audit['source_hashes']);retain_pins(document['source_hashes'])
    require(F(book['fee_bps'])==0 and F(book['slippage_bps'])==5,'BASELINE_COSTS')
    require([r['date'] for r in book['daily_ledger']]==dates[1:] and len(dates)==sessions+1,'BASELINE_DATES')
    qdir=ROOT/'tmp/qqq_fair_hold_20261105';qqq=read(qdir/(name+'.json'));manifest=read(qdir/'summary.json')
    qaudit=next(r for r in read(qdir/'independent_audit.json') if r['window']==name)
    require([r['date'] for r in qqq['ledger']]==dates[1:],'QQQ_DATES');verify_qqq(qqq,manifest,qaudit,dates);retain_pins(manifest['source_hashes'])
    order=qqq['order']
    quantity=qqq['ledger'][0]['shares']
    fill_price=(F(20000)-F(qqq['ledger'][0]['cash']))/quantity
    require(F(order['fill'])==fill_price and F(order['cash_after'])==F(qqq['ledger'][0]['cash']),'QQQ_FILL_CASH_BINDING')
    qorders=[dict(event='ASSUMED_NEXT_OPEN_FILLED',date=dates[1],quantity=quantity,price=str(fill_price),side='BUY',fee='0')]
    return dates,dict(v27=measure(book['daily_ledger'],dates[0],book['order_log']),qqq=measure(qqq['ledger'],dates[0],qorders))


def candidate(folder,window,delay,dates):
    book=read(folder/'book.json');summary=read(folder/'summary.json');contract=read(folder/'contract.json')
    sessions,months=(753,36) if window=='2021_2023' else (646,31)
    require(book['status']==summary['status']=='COMPLETE','UNREVIEWED_OR_INCOMPLETE_ACCOUNT')
    require(summary['completed_sessions']==summary['required_sessions']==len(book['daily_ledger'])==sessions,'INCOMPLETE_SESSIONS')
    require(summary['target_sizing_calls']==book['target_sizing_calls']==months,'INCOMPLETE_MONTH_SIZINGS')
    require(contract['window']==window and contract['settlement_delay']==summary['settlement_delay']==delay,'SCENARIO_BINDING')
    require(F(contract['initial_cash'])==20000 and F(contract['fee_bps'])==F(book['fee_bps'])==0
            and F(contract['slippage_bps'])==F(book['slippage_bps'])==5,'ACCOUNT_COSTS')
    require([r['date'] for r in book['daily_ledger']]==dates[1:],'ACCOUNT_DATE_GRID')
    retain_pins(contract['source_hashes'])
    validate_candidate_audit(folder,book,window,delay,sessions,months)
    result=measure(book['daily_ledger'],dates[0],book['order_log'])
    require(abs(result['drawdown_pct']-float(F(book['drawdown']['maximum_close_drawdown']))*100)<1e-9,'DD_RECONCILIATION')
    result['settlement_delay_sessions']=delay
    result['assumption']='SGEN merger available-cash timing sensitivity; not certified HSBC arrival' if window=='2021_2023' else 'No early-window settlement scenario selection'
    return result


def run(early,late,output):
    # Every scenario must pass its independently produced, current-book-bound report.
    require(AUDIT_STATUS is not None,'UNREVIEWED_AUDIT_SCHEMA_NOT_YET_INTEGRATED')
    results={}
    for window,folder,delays in [('2021_2023',(ROOT/early).resolve(),[0,1,5]),('2024_2026',(ROOT/late).resolve(),[0])]:
        manifest=read(folder/'all_scenarios.json')
        require(manifest['window']==window and manifest['selection_of_best_delay_forbidden'] is True,'ALL_SCENARIOS_MANIFEST')
        require([r['settlement_delay'] for r in manifest['scenarios']]==delays,'ALL_FIXED_DELAYS_REQUIRED')
        dates,base=benchmarks(window);base['scenarios']={}
        for delay in delays:base['scenarios']['D'+str(delay)]=candidate(folder/('D'+str(delay)),window,delay,dates)
        results[window]=base
    pins=dict(EXPECTED_PINS)
    for path,digest in READ_HASHES.items():
        name=path.relative_to(ROOT).as_posix()
        require(name not in pins or pins[name]==digest,'SUMMARY_READ_PIN_CONFLICT')
        pins[name]=digest
    for name in [Path(__file__).relative_to(ROOT).as_posix(),'scripts/research/summarize_downside_max10_20261105.py',
                 'scripts/research/summarize_cross_month_held_peak_20261105.py','scripts/research/summarize_ema20_market_20261105.py']:
        pins[name]=sha256((ROOT/name).read_bytes()).hexdigest()
    verify(pins)
    report=dict(status='COMPLETE_ALL_SCENARIOS_AUDITED_COMPARISON',results=results,source_hashes=pins,
                selection_of_best_delay_forbidden=True,limitations=['Conditional sources; not PIT/OOS certification.',
                'Early D0/D1/D5 are all retained; do not choose the most profitable arrival assumption.',
                'Gross dividends and issuer payment convention do not certify broker net cash arrival.',
                'QQQ first-next-open hold,5bps,zero commission,unspent dividend receivables; terminal close mark,not forced sale.',
                '2026 ends July30; excluding2026 is provided separately.'])
    target=(ROOT/output).resolve();require(target.is_relative_to(ROOT/'tmp'),'LOCAL_TMP_OUTPUT_REQUIRED')
    require(not target.exists(),'REFUSE_OVERWRITE_COMPARISON');target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2),encoding='utf8');return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--early',required=True);parser.add_argument('--late',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();run(args.early,args.late,args.output)
