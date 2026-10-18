"""Exact, read-only realized paper-event performance; no fills inferred from marks."""
from datetime import date
from fractions import Fraction
import math
from data.current_research_fill_ledger import review_paper_ledger


def compute_paper_performance(state, *, session_dates, marks, through_date, unprocessed_actions=()):
    """Caller supplies a complete authenticated calendar and same-unit close marks.

    Fresh-cash genesis only. Every calendar session requires an explicit marks
    mapping ({} is valid while flat). Late recorded fills restate the history.
    No dividend, corporate action, cash flow or pending-right accounting is added.
    """
    review_paper_ledger(state)
    def require(ok, reason):
        if not ok:raise ValueError(reason)
    def amount(value):
        require(not isinstance(value,bool), 'INVALID_MARK')
        result=Fraction(str(value));require(result>0,'INVALID_MARK');return result
    first=state['plans'][0];start=first['causal_inputs']['decision_date']
    require(not any(first['causal_inputs']['shares'].values()),'FRESH_CASH_GENESIS_REQUIRED')
    require(isinstance(session_dates,list) and session_dates and session_dates==sorted(set(session_dates)), 'INVALID_CALENDAR')
    for day in session_dates:require(date.fromisoformat(day).isoformat()==day,'INVALID_CALENDAR_DATE')
    require(session_dates[0]==start and session_dates[-1]==through_date,'CALENDAR_RANGE_MISMATCH')
    require(isinstance(marks,dict),'MARKS_MAPPING_REQUIRED')
    budget=Fraction(first['available_cash']);require(budget>0,'POSITIVE_INITIAL_CASH_REQUIRED')
    orders={(p['plan_id'],o['order_id']):o for p in state['plans'] for o in p['orders']}
    fills=[e for e in state['events'] if e.get('event_type','FILL')=='FILL']
    require([e['session'] for e in fills]==sorted(e['session'] for e in fills),'NONCHRONOLOGICAL_FILL_SESSIONS')
    byday={};issues=[]
    for e in fills:
        if e['session']>through_date:continue
        require(e['session'] in session_dates, 'FILL_SESSION_MISSING_FROM_CALENDAR')
        byday.setdefault(e['session'],[]).append(e)
    if unprocessed_actions:issues.append(dict(reason='UNPROCESSED_ACTIONS',details=list(unprocessed_actions)))
    cash=budget;shares={};fees=Fraction(0);rows=[];peak=budget;peakdate=start;dd=Fraction(0);ddpeak=start;trough=start
    for day in session_dates:
        for e in byday.get(day,[]):
            o=orders[(e['plan_id'],e['order_id'])];q=e['qty'];cost=Fraction(e['price'])*q;fee=Fraction(e['fees']);sid=o['security_id']
            sign=1 if o['side']=='BUY' else -1
            shares[sid]=shares.get(sid,0)+sign*q;cash-=sign*cost+fee;fees+=fee
            require(cash>=0 and shares[sid]>=0,'REPLAY_NEGATIVE_ASSETS')
            if shares[sid]==0:del shares[sid]
        daily=marks.get(day);missing=[];equity=None
        if not isinstance(daily,dict):missing=['SESSION_OBSERVATION_MISSING']
        else:
            for sid in shares:
                if sid not in daily or daily[sid] is None:missing.append(sid)
            if not missing:equity=cash+sum((q*amount(daily[sid]) for sid,q in shares.items()),Fraction(0))
        if missing:issues.append(dict(reason='MISSING_CLOSE_OBSERVATION',session=day,missing=missing))
        if equity is not None:
            if equity>peak:peak=equity;peakdate=day
            current=(peak-equity)/peak
            if current>dd:dd=current;ddpeak=peakdate;trough=day
        rows.append(dict(session=day,cash=str(cash),shares=dict(shares),recorded_fees_to_date=str(fees),
                         equity=None if equity is None else str(equity),missing=missing))
    if not any(e['session']>through_date for e in fills) and not any(i['reason']=='FILL_SESSION_MISSING_FROM_CALENDAR' for i in issues):
        require(cash==Fraction(state['cash']) and shares=={s:q for s,q in state['shares'].items() if q},'TERMINAL_REPLAY_MISMATCH')
        require(fees==Fraction(state['total_recorded_fees']),'TERMINAL_FEE_MISMATCH')
    complete=not issues;elapsed=(date.fromisoformat(through_date)-date.fromisoformat(start)).days
    total=(Fraction(rows[-1]['equity'])/budget-1) if complete else None
    annual=None;annual_reason=None
    if complete and elapsed>0:
        try:
            annual=math.expm1(math.log(float(Fraction(rows[-1]['equity'])/budget))*365/elapsed) if total>-1 else -1.0
            if not math.isfinite(annual):raise OverflowError('nonfinite annualization')
        except (OverflowError, ValueError):
            annual=None;annual_reason='ANNUALIZATION_NOT_REPRESENTABLE_AS_FINITE_FLOAT'
    elif not complete:annual_reason='INCOMPLETE_PERIOD'
    else:annual_reason='ZERO_ELAPSED_CALENDAR_DAYS'
    return dict(status='COMPLETE' if complete else 'INCOMPLETE',account_id=state['account_id'],revision=state['revision'],
        start_date=start,through_date=through_date,elapsed_calendar_days=elapsed,initial_cash=str(budget),daily_ledger=rows,
        total_return=None if total is None else str(total),annualized_return=annual,annualization_unavailable_reason=annual_reason,
        maximum_close_drawdown=str(dd) if complete else None,drawdown_peak_date=ddpeak if complete else None,
        drawdown_trough_date=trough if complete else None,recorded_fees=str(fees),issues=issues,
        recorded_fill_count=sum(len(v) for v in byday.values()),external_cash_flows='0',generated_fill_count=0,
        history_basis='RECONSTRUCTED_FROM_CURRENT_REVISION_NOT_AS_KNOWN_HISTORY',
        excluded_future_fill_count=sum(e['session']>through_date for e in fills),
        calendar_verified=False,source_verified=False,annualization_basis='ACT_365_CALENDAR_DAYS',
        unit_continuity_assumption='CALLER_SUPPLIED_SAME_UNIT_MARKS_NO_UNPROCESSED_ACTIONS_NOT_VERIFIED',
        limitations=['Calendar completeness and mark source/unit continuity must be authenticated by caller.',
                    'No inferred dividends, actions, pending rights or unknown costs; only recorded fill fees included.',
                    'Daily close drawdown omits intraday variation. Annualization is a descriptive float using 365/elapsed calendar days.'],
        research_only=True,execution_blocked=True)
