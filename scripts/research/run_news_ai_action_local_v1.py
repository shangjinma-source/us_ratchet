"""Research-only same-month AI action replay; no monthly optimization or model calls."""
import argparse
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backtest.historical_dividend_next_open_book_research import run_next_open_book
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter

CASES = ('MRNA_Q2','MRNA_Q3','NVDA_Q3_2023','NVDA_Q3_2024','APP_Q3')
ACTIONS = ('NO_CHANGE','BLOCK_NEW_BUYS','EXIT')


def instant(value):
    result = datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('AWARE_TIME_REQUIRED')
    return result


def prepare(case):
    if case['initialization_requires_entitlement_reconstruction']:
        raise ValueError('INITIAL_ENTITLEMENTS_UNSUPPORTED')
    reset = min(case['monthly_reset_dates'], default='9999-12-31')
    days = [day for day in case['session_dates'] if day < reset]
    if len(days) < 2:
        raise ValueError('NO_EXECUTABLE_PRE_SELECTION_WINDOW')
    initial, last = days[0], days[-1]
    frozen = case['corporate_action_inputs']
    for key in ('actions','provider_actions','cash_stock_merger_events','distribution_events'):
        for event in frozen.get(key) or []:
            date = event.get('effective_date', event.get('date'))
            if not date:
                raise ValueError('ACTION_DATE_REQUIRED')
            if initial < date <= last:
                raise ValueError('LOCAL_CORPORATE_ACTION_UNSUPPORTED')
    # Initial rights cannot be recreated from just cash/shares. Ex dates inside
    # the window are handled by the real kernel, including its unpaid receivable.
    for key in ('receivable','dividend_receivable','nontradable_entitlement_value'):
        if Fraction(str(case['initial_baseline_ledger'].get(key,0))):
            raise ValueError('INITIAL_ENTITLEMENTS_UNSUPPORTED')
    return days


def replay(case, action, session_closes):
    if action not in ACTIONS:
        raise ValueError('ACTION_NOT_ALLOWED')
    days = prepare(case)
    availability = instant(case['metadata_availability'])
    for day in days[:-1]:
        instant(session_closes[day])
    ceiling = deepcopy(case['initial_close_baseline_audit']['monthly_ceiling'])
    epoch = case['initial_close_baseline_audit']['target_decision_date']
    risk = MonthlyExitCoreResearchAdapter()
    risk.state = deepcopy(case['initial_risk_state_before_close'])
    risk.last_day = risk.state['session_date'] if risk.state else None
    trace = []
    sid = case['security_id']
    def provider(*, decision_date, active_date, state):
        if decision_date in case['monthly_reset_dates']:
            raise ValueError('MONTHLY_SELECTION_FORBIDDEN')
        if any(state.get(k) for k in ('pending_post_close_coordinates','distribution_rights','merger_entitlements')):
            raise ValueError('ACTION_STATE_UNSUPPORTED')
        target, diagnostics = risk.apply(day=decision_date, month=epoch,
            target=deepcopy(ceiling), closes={s:case['close_prices'][s][decision_date] for s in ceiling})
        original = deepcopy(target)
        enabled = availability < instant(session_closes[decision_date])
        if enabled and action == 'BLOCK_NEW_BUYS':
            target[sid] = min(target.get(sid,0), state['shares'].get(sid,0))
        if enabled and action == 'EXIT':
            target[sid] = 0
        orders=[]
        for security in sorted(set(state['shares']) | set(target)):
            delta=target.get(security,0)-state['shares'].get(security,0)
            if delta:
                orders.append(dict(id='ai-local:'+decision_date+':'+security,
                    security_id=security,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),
                    decision_date=decision_date,active_date=active_date,
                    decision_mark=case['close_prices'][security][decision_date]))
        trace.append(dict(decision_date=decision_date,active_date=active_date,news_active=enabled,
            action=action,account_state=deepcopy(state),original_risk_target=original,
            effective_target=deepcopy(target),risk=diagnostics,orders=deepcopy(orders)))
        return dict(status='READY',orders=orders)
    ledger=case['initial_baseline_ledger']
    result=run_next_open_book(session_dates=days,ohlc=case['ohlc'],initial_cash=ledger['cash'],
        initial_shares=ledger['shares'],fee_bps='0',slippage_bps='5',order_provider=provider,
        dividend_events=[e for e in case['dividend_events'] if days[0]<e['ex_date']<=days[-1]])
    if result['status']!='COMPLETE':
        raise ValueError(('LOCAL_REPLAY_INCOMPLETE',result.get('reason')))
    return dict(book=result,decision_trace=trace,session_dates=days)


def validate_actions(root, review, cases):
    if review.get('schema')!='NEWS_AI_LOCAL_ACTION_REVIEW_V1':
        raise ValueError('REVIEW_SCHEMA_REQUIRED')
    pins=review.get('source_hashes',{})
    if not pins:
        raise ValueError('REVIEW_EVIDENCE_REQUIRED')
    for path,digest in pins.items():
        if sha256((root/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('REVIEW_SOURCE_CHANGED')
    rows=review.get('records',[])
    if len(rows)!=5 or {r['case'] for r in rows}!=set(CASES):
        raise ValueError('ALL_FIVE_UNIQUE_CASES_REQUIRED')
    for row in rows:
        case,digest=cases[row['case']]
        if row['action'] not in ACTIONS or row.get('case_sha256')!=digest:
            raise ValueError('ACTION_OR_CASE_BINDING_INVALID')
        if instant(row['available_at'])!=instant(case['metadata_availability']):
            raise ValueError('ACCEPTANCE_PROXY_BINDING_REQUIRED')
        if row.get('review_reference') not in pins:
            raise ValueError('INDEPENDENT_REVIEW_REFERENCE_REQUIRED')
    return rows


def run(root, reviewed_actions_path, clock_path, output):
    root=Path(root).resolve(); output=Path(output)
    cases={}
    pins={}
    def read(path):
        path=Path(path);raw=path.read_bytes();pins[str(path)]=sha256(raw).hexdigest()
        return json.loads(raw),pins[str(path)]
    for name in CASES:
        cases[name]=read(root/'tmp/local_news_cases_20261027'/(name+'.json'))
    review,_=read(reviewed_actions_path)
    rows=validate_actions(root,review,cases)
    clock,_=read(clock_path)
    closes={x['date']:x['close'] for x in clock['sessions']}
    # Validate all windows before writing or executing any branch.
    for case,_ in cases.values():
        for day in prepare(case)[:-1]: instant(closes[day])
    output.mkdir(parents=True,exist_ok=False)
    summaries=[]
    for row in rows:
        case,_=cases[row['case']]
        base=replay(case,'NO_CHANGE',closes)
        expected=[r for r in case['baseline_comparison_ledger'] if r['date'] in base['session_dates'][1:]]
        actual=base['book']['daily_ledger']
        if len(actual)!=len(expected): raise ValueError('BASELINE_LENGTH_MISMATCH')
        for a,b in zip(actual,expected):
            for key in ('date','cash','shares','equity','dividend_receivable'):
                if a.get(key,'0')!=b.get(key,'0'):
                    raise ValueError(('BASELINE_NOT_EXACT',row['case'],a['date'],key))
        branch=replay(case,row['action'],closes)
        result=dict(case=row['case'],action=row['action'],baseline_exact=True,
            initial_date=base['session_dates'][0],last_date=base['session_dates'][-1],
            availability=case['metadata_availability'],baseline=base,branch=branch,
            terminal_equity_delta=str(Fraction(branch['book']['daily_ledger'][-1]['equity'])-Fraction(actual[-1]['equity'])))
        (output/(row['case']+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
        summaries.append({k:v for k,v in result.items() if k not in ('baseline','branch')})
    pins[str(Path(__file__))]=sha256(Path(__file__).read_bytes()).hexdigest()
    for relative in ('backtest/historical_dividend_next_open_book_research.py','backtest/monthly_exit_core_research_adapter.py','core/monthly_peak_exit.py'):
        pins[relative]=sha256((root/relative).read_bytes()).hexdigest()
    result=dict(status='SAME_MONTH_LOCAL_REPLAY_COMPLETE',cases=summaries,source_hashes=pins,
        review=review,limitations=['Acceptance timestamp is a conservative proxy, not certified original news publication.',
        'Same-month incremental execution only: stop strictly before next monthly decision date or fixed 20-session end.',
        'No new selection; real daily original risk; reviewed action persists to window end.',
        'NO_CHANGE baseline must reproduce each day exactly; no annualization or deployable strategy claim.',
        'Cash remains available to original targets; no new capital redistribution optimization.'])
    (output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review',required=True);parser.add_argument('--clock',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--root',default='.')
    args=parser.parse_args()
    print(json.dumps(run(args.root,args.review,args.clock,args.output)['cases']))
