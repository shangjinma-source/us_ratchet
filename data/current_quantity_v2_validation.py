"""Pinned saved V2 annual path projection. No strategy imports or execution."""
from pathlib import Path
from fractions import Fraction
from datetime import date
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parents[1]
BASE='tmp/next12_quantity_v2_execution_20261015_v1'
REVIEW='tmp/next12_quantity_v2_actual_independent_20261015_v1.json'
METHOD='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2'
PINS={
 BASE+'/result.json':'ba6e8ee29a88533b8540a1d0ac40664e47ac37cf695bc7eaf1847d48c5b9b0a4',
 BASE+'/registration.json':'f262f451020317147f83294e415eb39eb12c7e757d4fad2de0076eea27156350',
 BASE+'/quantity_v2/outcome.json':'74b8de41f91ca25a6e3fcbdc7c119b4e9c95a5d330069b572b900495215fd309',
 BASE+'/quantity_v2/result.json':'388afeee70788d4cfd5945792aaeb484913bf20ee7f8c480f4c0b860cb652f1a',
 REVIEW:'bf9c0a24c9602c6a75b8da73efaa8e3ee96a2b2a5574b7a86f6cb19e6b6f4461'}


def require(ok):
    if not ok:raise ValueError('V2_SAVED_EVIDENCE_MISMATCH')


def read_quantity_v2_validation(*,root=ROOT):
    """Missing/changed V2 evidence yields None; never substitute another method."""
    try:
        documents={}
        for p,h in PINS.items():
            file=Path(root)/p;require(file.stat().st_size<=32*1024*1024)
            raw=file.read_bytes();require(hashlib.sha256(raw).hexdigest()==h)
            documents[p]=json.loads(raw)
        result=documents[BASE+'/result.json'];reg=documents[BASE+'/registration.json'];audit=documents[REVIEW]
        method=documents[BASE+'/quantity_v2/result.json'];out=documents[BASE+'/quantity_v2/outcome.json'];m=method['metrics']
        require(audit['independent_review'] is True and audit['status']=='PASS_INDEPENDENT_SAVED_LEDGER_AND_12_V2_DECISIONS')
        require(all(audit['source_hashes'].get(p)==h for p,h in PINS.items() if p!=REVIEW))
        require(result['methods']==[method] and method['method']==reg['method']==METHOD)
        require(result['book_calls']==result['complete_books']==result['denominator']==1 and result['baseline_reruns']==0)
        require(method['core_calls']==method['capital_decision_attempts']==method['completed_capital_decisions']==audit['core_calls']==12)
        require(method['selector_calls']==0 and method['book_calls']==audit['book_calls']==1)
        require(reg['initial_cash']=='20000' and reg['initial_shares']=={} and reg['monthly_cash_reset'] is False)
        dates=reg['session_dates'];require(len(dates)==251 and dates==sorted(set(dates)) and dates[0]=='2025-07-31' and dates[-1]=='2026-07-30')
        require(len(reg['decision_dates'])==len(audit['monthly'])==12 and [r['date'] for r in audit['monthly']]==reg['decision_dates'])
        require(all(r['all_affordable_k_initialized'] is True and 0<r['objective_evaluations']<=8192 for r in audit['monthly']))
        require(m['status']==out['status']=='COMPLETE' and m['complete_full_period'] is True)
        require(m['terminal_state_valuation_synchronized'] is True and out['terminal_state_valuation_synchronized'] is True)
        require(m['final_wealth_basis']==out['final_wealth_basis']=='REGULAR_CLOSE_CURRENT_STATE')
        require(m['provider_callbacks']==m['valued_sessions']==audit['callbacks']==audit['valued_sessions']==250 and audit['observations']==251)
        ledger=out['daily_ledger'];require([r['date'] for r in ledger]==dates[1:])
        values=[Fraction(20000)]+[Fraction(r['equity']) for r in ledger];require(all(v>0 for v in values))
        peak=values[0];peak_i=0;dd=Fraction();pi=ti=0
        for i,v in enumerate(values):
            if v>peak:peak=v;peak_i=i
            draw=1-v/peak
            if draw>dd:dd=draw;pi=peak_i;ti=i
        terminal=values[-1];total=terminal/20000-1;days=(date.fromisoformat(dates[-1])-date.fromisoformat(dates[0])).days
        annual=float(terminal/20000)**(365/days)-1
        require(terminal==Fraction(m['terminal_equity'])==Fraction(audit['terminal_equity_exact']))
        require(total==Fraction(m['total_return']) and dd==Fraction(m['daily_close_maximum_drawdown'])==Fraction(audit['maximum_drawdown_exact']))
        require(days==m['annualization_basis']['calendar_days']==364 and math.isclose(annual,m['annualized_return'],rel_tol=1e-12) and math.isclose(annual,float(audit['annualized_return']),rel_tol=1e-12))
        require(dates[pi]==audit['peak_date'] and dates[ti]==audit['trough_date'])
        require(reg['execution_policy']=='SEALED_PREVIOUS_CLOSE_DAY_NOT_LIVE_MINUTE_RULE')
        require(all(obj['price_only'] is True and obj['independent_oos'] is False and obj['adoption_allowed'] is False for obj in (reg,result,method)))
        return dict(status='AVAILABLE',method=METHOD,period=dict(start=dates[0],end=dates[-1],calendar_days=days),
            initial_cash=20000,historical_initial_cash=20000,currency='USD',complete_full_period=True,
            total_return=float(total),annualized_return=annual,max_drawdown=float(dd),terminal_equity=float(terminal),
            peak_date=dates[pi],trough_date=dates[ti],core_calls=12,book_calls=1,observations=251,
            execution_policy=reg['execution_policy'],independent_oos=False,current_candidate_performance=False,
            current_minute_execution_validated=False,price_only=True,research_only=True,execution_blocked=True,
            optimality_proven=False,source_fingerprints=dict(PINS),calculation_calls=0,search_calls=0,
            note='历史2万美元连续账户；昨日收盘DAY触价假设，不是当前现金候选收益或分钟报价策略验证。')
    except (OSError,ValueError,TypeError,KeyError,IndexError,ArithmeticError):
        return None
