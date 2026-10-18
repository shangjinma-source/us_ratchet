"""Read-only whole-lot failure attribution for one explicitly chosen v2 task."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_joint_weight_evaluation_v2 as evaluator
from backtest import ndx_joint_weight_runner_v2 as runner_v2
from backtest import ndx_joint_weight_runner as runner
from backtest.ndx_whole_lot_rebalance import simulate_continuous_whole_lot_rebalance
from scripts.ndx_joint_weight_verify import _restore_input
from scripts.ndx_joint_weight_progress import Snapshot


def _require(condition,message):
    if not condition:
        raise ValueError(message)


def explain_path(prices,schedule,ledger,contract):
    """Observe original ledger shares at each daily close; no alternate trades."""
    by_date={str(r['rebalance_date']):r for r in ledger.to_dict('records')}
    schedule_by_date={str(d.date()):dict(w) for d,w in schedule}
    tickers=sorted(schedule[0][1]);shares=None;daily=[];independent=[];previous_failures=set()
    for date,row in prices.loc[schedule[0][0]:,tickers].iterrows():
        key=str(date.date());rebalance=key in by_date
        if rebalance:
            shares={t:int(n) for t,n in (item.split(':') for item in by_date[key]['shares'].split(';'))}
        _require(shares is not None and set(shares)==set(tickers),'Ledger missing initial shares')
        notionals={t:shares[t]*float(row[t]) for t in tickers};invested=sum(notionals.values())
        weights={t:notionals[t]/invested if invested>0 else 0. for t in tickers}
        ordered=sorted(weights.values(),reverse=True)
        groups={}
        for ticker,weight in weights.items():
            group=contract['risk_chain_by_ticker'][ticker]
            groups[group]=groups.get(group,0.)+weight
        effective=1/sum(w*w for w in weights.values()) if invested>0 else 0.
        failures=[]
        if min(shares.values())<1:failures.append('MINIMUM_ONE_SHARE')
        if min(weights.values())<contract['min_single_weight']-1e-9:failures.append('WEIGHT_FLOOR')
        if max(weights.values())>contract['max_single_weight']+1e-9:failures.append('TOP1')
        if sum(ordered[:3])>contract['top_weight_cap']+1e-9:failures.append('TOP3')
        if effective<contract['minimum_effective_n_ratio']*len(tickers)-1e-9:failures.append('EFFECTIVE_N')
        if max(groups.values())>contract['risk_chain_top1_cap']+1e-9:failures.append('RISK_CHAIN_TOP1')
        if invested<=0:failures.append('NO_INVESTED_EQUITY')
        onsets={f:('REBALANCE_DAY' if rebalance else 'NEW_HOLDING_DRIFT')
                for f in failures if f not in previous_failures}
        daily.append(dict(date=key,phase='REBALANCE_DAY' if rebalance else 'HOLDING_DAY',failures=failures,
            newly_breached_constraints=onsets,persisting_failures=sorted(set(failures)&previous_failures),
            shares=dict(shares),weights=weights,effective_n=effective,risk_chain_weights=groups,
            rebalance_target_weights=schedule_by_date.get(key),
            top1=max(weights.values()),top3=sum(ordered[:3]),min_weight=min(weights.values())))
        previous_failures=set(failures)
        if rebalance:
            weights_target=schedule_by_date[key]
            static_cash=contract['portfolio_cash_usd']-contract['minimum_cash_buffer_usd']
            static_shares={t:math.floor(static_cash*weights_target[t]/float(row[t])) for t in tickers}
            if min(static_shares.values())<1:
                independent.append(dict(date=key,shares=static_shares,
                    reason='LEGACY_INDEPENDENT_WINDOW_INITIAL_CAPITAL_FLOOR'))
    kinds=sorted({f for r in daily for f in r['failures']})
    return dict(daily=daily,first_failure=next((r for r in daily if r['failures']),None),
        failure_summary={kind:dict(days=sum(kind in r['failures'] for r in daily),
            rebalance_days=sum(kind in r['failures'] and r['phase']=='REBALANCE_DAY' for r in daily),
            holding_days=sum(kind in r['failures'] and r['phase']=='HOLDING_DAY' for r in daily),
            new_holding_drift_breaches=sum(r['newly_breached_constraints'].get(kind)=='NEW_HOLDING_DRIFT' for r in daily),
            first=next(r for r in daily if kind in r['failures'])) for kind in kinds},
        independent_window_min_share_failures=independent)


def evaluate_observed(task,inputs):
    observations=[]
    def observe(prices,schedule,**contract):
        summary,ledger=simulate_continuous_whole_lot_rebalance(prices,schedule,**contract)
        observations.append(dict(original_summary=dict(summary),ledger=ledger.to_dict('records'),
            attribution=explain_path(prices,schedule,ledger,contract)))
        return summary,ledger
    portfolio=evaluator._bind(evaluator._PORTFOLIO,simulate_continuous_whole_lot_rebalance=observe)
    evaluate=evaluator._bind(evaluator._EVALUATE,evaluate_synthetic_portfolio=portfolio)
    original=evaluator.evaluate_joint_weight_task_v2(task,**inputs)
    observed=evaluate(task,**inputs)
    _require(runner._json_bytes(runner._normalize(original))==runner._json_bytes(runner._normalize(observed)),
             'Observer changed original evaluation result')
    _require(len(observations)==1,'Unexpected simulator invocation count')
    return dict(result=observed,observation=observations[0],observer_result_exactly_unchanged=True)


def run(context_sha256,job_id):
    _require(isinstance(context_sha256,str) and len(context_sha256)==64
             and all(c in '0123456789abcdef' for c in context_sha256),'Explicit canonical context SHA required')
    _require(isinstance(job_id,str) and len(job_id)==64
             and all(c in '0123456789abcdef' for c in job_id),'Explicit canonical job ID required')
    sources=runner_v2.source_hashes()
    watched={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__),ROOT/'scripts/ndx_joint_weight_verify.py',ROOT/'scripts/ndx_joint_weight_progress.py')}
    snapshot=Snapshot();directory=runner_v2.CHECKPOINT_ROOT/context_sha256
    context=snapshot.read(directory/'context.json')
    _require(runner._sha(context)==context_sha256 and context.get('schema')=='ndx_joint_weight_checkpoint_v1'
             and context['numerical_sources']==sources,'V2 context identity/source differs')
    tasks=context['tasks']
    _require(isinstance(tasks,list) and tasks and len({t['job_id'] for t in tasks})==len(tasks),'Invalid task denominator')
    selected=[t for t in tasks if t['job_id']==job_id]
    _require(len(selected)==1,'Explicit task not found')
    runner._validate_task(selected[0])
    inputs={k:_restore_input(v) for k,v in context['prepared_inputs'].items()}
    result=evaluate_observed(selected[0],inputs)
    snapshot.verify()
    _require(runner_v2.source_hashes()==sources and watched=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in watched},
             'Probe source changed during observation')
    return dict(result,context_sha256=context_sha256,job_id=job_id,source_hashes=sources,
        scope='ONE_EXPLICIT_TASK_NOT_GLOBAL_ATTRIBUTION',constraint_changes=False,trade_changes=False,
        promotion_allowed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context',required=True)
    parser.add_argument('--job-id',required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.context,args.job_id),ensure_ascii=False,indent=2))
