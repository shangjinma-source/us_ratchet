"""Verify fixed local replay receipts and report unannualized interval metrics."""
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research.run_news_ai_action_local_v1 import CASES, prepare


def interval_metrics(initial_equity, ledger):
    initial=Fraction(str(initial_equity))
    if initial<=0 or not ledger:
        raise ValueError('POSITIVE_INITIAL_EQUITY_AND_LEDGER_REQUIRED')
    peak=initial; drawdown=Fraction(0)
    for row in ledger:
        equity=Fraction(str(row['equity']))
        if equity<0: raise ValueError('NEGATIVE_EQUITY')
        peak=max(peak,equity)
        drawdown=max(drawdown,(peak-equity)/peak)
    final=Fraction(str(ledger[-1]['equity']))
    return dict(initial_equity=str(initial),final_equity=str(final),
        interval_return=str(final/initial-1),interval_return_percent=float((final/initial-1)*100),
        maximum_drawdown=str(drawdown),maximum_drawdown_percent=float(drawdown*100))


def fills(book):
    keys=('date','security_id','side','quantity','price','fee')
    return Counter(tuple(str(row[key]) for key in keys) for row in book['order_log']
        if row['event']=='ASSUMED_NEXT_OPEN_FILLED')


def compare_fills(base, branch):
    old,new=fills(base),fills(branch)
    def rows(counter):
        return [dict(zip(('date','security_id','side','quantity','price','fee'),key),count=count)
                for key,count in sorted(counter.items())]
    removed,added=old-new,new-old
    return dict(baseline_fill_count=sum(old.values()),branch_fill_count=sum(new.values()),
        baseline_only_fill_count=sum(removed.values()),branch_only_fill_count=sum(added.values()),
        changed_fill_key_count=len(set(removed)|set(added)),
        definition='Exact date/security/side/quantity/price/fee multiset; a changed fill appears once in each side, not two independent trades.',
        baseline_only=rows(removed),branch_only=rows(added))


def report(root, directory):
    root=Path(root).resolve();directory=Path(directory)
    summary=json.loads((directory/'summary.json').read_text(encoding='utf-8-sig'))
    if summary['status']!='SAME_MONTH_LOCAL_REPLAY_COMPLETE':raise ValueError('COMPLETE_LOCAL_RUN_REQUIRED')
    for pins in (summary['source_hashes'],summary['review']['source_hashes']):
        for path,digest in pins.items():
            if sha256((root/path).read_bytes()).hexdigest()!=digest:raise ValueError(('SOURCE_CHANGED',path))
    if len(summary['cases'])!=5 or {r['case'] for r in summary['cases']}!=set(CASES):
        raise ValueError('FIVE_CASES_REQUIRED')
    rows=[];evidence={}
    for name in CASES:
        path=directory/(name+'.json');raw=path.read_bytes();evidence[str(path)]=sha256(raw).hexdigest()
        result=json.loads(raw)
        case=json.loads((root/'tmp/local_news_cases_20261027'/(name+'.json')).read_text(encoding='utf-8-sig'))
        base,branch=result['baseline'],result['branch']
        days=base['session_dates']
        if days!=prepare(case):raise ValueError('FROZEN_WINDOW_MISMATCH')
        reviewed=[r for r in summary['review']['records'] if r['case']==name]
        if len(reviewed)!=1 or result['action']!=reviewed[0]['action']:raise ValueError('REVIEW_ACTION_MISMATCH')
        if sha256((root/'tmp/local_news_cases_20261027'/(name+'.json')).read_bytes()).hexdigest()!=reviewed[0]['case_sha256']:raise ValueError('CASE_REVIEW_HASH_MISMATCH')
        if branch['session_dates']!=days:raise ValueError('ARM_WINDOW_MISMATCH')
        expected=[r for r in case['baseline_comparison_ledger'] if r['date'] in days[1:]]
        actual=base['book']['daily_ledger'];changed=branch['book']['daily_ledger']
        if len(expected)!=len(actual) or len(changed)!=len(actual):raise ValueError('LEDGER_LENGTH_MISMATCH')
        for a,b,c in zip(actual,expected,changed):
            if a['date']!=c['date']:raise ValueError('BRANCH_DATE_MISMATCH')
            for key in ('date','cash','shares','equity','dividend_receivable'):
                if a.get(key,'0')!=b.get(key,'0'):raise ValueError(('BASELINE_NOT_EXACT',name,key))
        differences=[dict(date=a['date'],cash_delta=str(Fraction(b['cash'])-Fraction(a['cash'])),
            shares_delta={sid:b['shares'].get(sid,0)-a['shares'].get(sid,0)
                for sid in sorted(set(a['shares'])|set(b['shares'])) if b['shares'].get(sid,0)!=a['shares'].get(sid,0)},
            equity_delta=str(Fraction(b['equity'])-Fraction(a['equity'])))
            for a,b in zip(actual,changed) if a['cash']!=b['cash'] or a['shares']!=b['shares'] or a['equity']!=b['equity']]
        trace=branch['decision_trace']
        eligible=next((t for t in trace if t['news_active']),None)
        affected=next((t for t in trace if t['effective_target']!=t['original_risk_target']),None)
        filldiff=compare_fills(base['book'],branch['book'])
        filldates=[r['date'] for r in filldiff['baseline_only']+filldiff['branch_only']]
        initial=case['initial_baseline_ledger']['equity']
        row=dict(case=name,action=result['action'],baseline_exact=True,
            initial_date=days[0],last_date=days[-1],executed_sessions=len(actual),
            first_eligible_decision=eligible['decision_date'] if eligible else None,
            first_target_change_decision=affected['decision_date'] if affected else None,
            first_changed_fill_date=min(filldates) if filldates else None,
            first_account_difference_date=differences[0]['date'] if differences else None,
            baseline=interval_metrics(initial,actual),branch=interval_metrics(initial,changed),
            fill_comparison=filldiff,daily_account_differences=differences,
            final_baseline_cash=actual[-1]['cash'],final_branch_cash=changed[-1]['cash'],
            final_baseline_shares=actual[-1]['shares'],final_branch_shares=changed[-1]['shares'])
        if result['action']=='NO_CHANGE' and (differences or filldates):raise ValueError('NO_CHANGE_CHANGED_ACCOUNT')
        rows.append(row)
    output=dict(status='LOCAL_FIVE_CASE_METRICS_VERIFIED',cases=rows,evidence_hashes=evidence,
        summary_sha256=sha256((directory/'summary.json').read_bytes()).hexdigest(),
        reviewer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=['Initial equity included in drawdown peak; returns are interval-only and not annualized.',
        'Actual fills here mean research assumed-next-open fills, not broker transactions.',
        'First eligibility, first target change, first fill change and first account change are distinct.',
        'No independent recomputation of fill arithmetic; original baseline exactness is separately checked.',
        'Same-month windows and acceptance proxy only; no cross-month optimization or causal generalization.'])
    (directory/'verified_metrics.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',default='.')
    parser.add_argument('--directory',required=True);args=parser.parse_args()
    print(report(args.root,args.directory)['status'])
