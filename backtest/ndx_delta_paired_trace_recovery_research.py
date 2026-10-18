"""Recover one original v3 trace, then update only incumbent paired statistics."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from backtest import ndx_delta_window_trace_research as trace
from backtest import ndx_candidate_input_equivalence_v2_research as equivalence
from backtest import ndx_joint_weight_runner as encoding
from scripts.ndx_joint_weight_verify import _restore, _restore_input

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PAIRED=('paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
        'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent')


def _read(path,sha):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External original artifact SHA differs')
    return json.loads(raw)


def _digest(inputs):
    return encoding._sha({key:encoding._panel_context(value) for key,value in inputs.items()})


def _paired_windows(inputs,task,windows):
    returns=inputs['returns'];contract=inputs['contract'];combo=task['tickers'].split(';')
    fit,window,step=(contract[key] for key in ('fit_days','window_days','step_days'))
    starts=list(range(fit,len(returns)-window+1,step))
    if len(windows)!=len(starts):raise ValueError('Complete DELTA fitted window denominator required')
    incumbent={key:float(inputs['incumbent_weights'][key]) for key in sorted(inputs['incumbent_weights'])}
    total=sum(incumbent.values());incumbent={key:value/total for key,value in incumbent.items()}
    prior=None;rows=[];anchored=task['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor'
    def metric(series,cost=0.):
        values=series.astype(float).copy()
        if (not np.isfinite(values.to_numpy()).all() or (values<=-1.).any() or
            not math.isfinite(cost) or not 0<=cost<1):raise ValueError('Finite valid return and cost required')
        values.iloc[0]=(1.+values.iloc[0])*(1.-cost)-1.
        nav=pd.Series(np.concatenate(([1.],(1.+values).cumprod().to_numpy(dtype=float))))
        if not np.isfinite(nav).all() or (nav<=0).any():raise ValueError('Finite positive NAV required')
        result=(float(nav.iloc[-1]**(252./len(values))-1.),float((1.-nav/nav.cummax()).max()))
        if not all(math.isfinite(v) for v in result):raise ValueError('Finite metric required')
        return result
    for start,record in zip(starts,windows):
        if (record['fit_start']!=str(returns.index[start-fit].date()) or record['fit_end']!=str(returns.index[start-1].date()) or
            type(record['fit_row_count']) is not int or record['fit_row_count']!=fit or record['tickers']!=combo):
            raise ValueError('Original trace fit boundary/order differs')
        weights=record['weights']
        if (set(weights)!=set(combo) or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in weights.values()) or
            abs(sum(weights.values())-1.)>1e-12):raise ValueError('Complete finite simplex trace required')
        if (record['anchor_weights']!=(prior if anchored else None) or
            type(record['turnover_anchor_strength']) not in (int,float) or
            type(record['risk_chain_projection_relaxed']) is not bool or
            record['turnover_anchor_strength']!=(contract['turnover_anchor_strength'] if anchored else 0.)):
            raise ValueError('Original trace anchor propagation differs')
        reference=incumbent if prior is None else prior
        turnover=.5*sum(abs(weights.get(t,0.)-reference.get(t,0.)) for t in set(weights)|set(reference))
        cost=float(turnover*contract['transaction_cost_bps']/10000.);forward=returns.iloc[start:start+window]
        cr,cd=metric(forward[combo].mul(pd.Series(weights),axis=1).sum(axis=1),cost)
        ir,idd=metric(forward[list(incumbent)].mul(pd.Series(incumbent),axis=1).sum(axis=1))
        tr,td=metric(inputs['target_returns'].iloc[start:start+window])
        rows.append(dict(start=str(forward.index[0].date()),end=str(forward.index[-1].date()),candidate_return=cr,
            candidate_drawdown=cd,incumbent_return=ir,incumbent_drawdown=idd,target_return=tr,target_drawdown=td,turnover=turnover,cost=cost))
        prior=weights
    metrics={}
    for name,key,quantile in zip(PAIRED,('return','return','drawdown','drawdown'),(.5,.1,.5,.9)):
        metrics[name]=float(np.quantile([row['candidate_'+key]-row['incumbent_'+key] for row in rows],quantile))
    return rows,metrics


def recover_paired_delta(*,arguments,corrected_inputs,context_path,context_sha256,checkpoint_path,checkpoint_sha256):
    arguments,corrected_inputs=deepcopy((arguments,corrected_inputs));sources=dict(arguments['source_hashes'])
    if arguments['engine']!='joint_weight_v3':raise ValueError('Original DELTA v3 required')
    for path,sha in ((context_path,context_sha256),(checkpoint_path,checkpoint_sha256)):
        if sources.get(str(Path(path).resolve()))!=sha:raise ValueError('Original external artifact absent from closure')
    for path,sha in (trace.source_hashes()|{str(SOURCE):LOADED}).items():
        if path in sources and sources[path]!=sha:raise ValueError('Conflicting loaded source SHA')
        sources[path]=sha
    equivalence.previous._verify(sources)
    context=_read(context_path,context_sha256);checkpoint=_read(checkpoint_path,checkpoint_sha256)
    if (context['schema']!='ndx_joint_weight_checkpoint_v1' or context['runtime']!=arguments['runtime'] or
        arguments['task'] not in context['tasks']):raise ValueError('Original DELTA context/task/runtime differs')
    if context['numerical_sources']!=trace.full._LOADED_SOURCES:raise ValueError('Original v3 numerical closure differs')
    def check_evidence(value):
        if isinstance(value,dict):
            if 'path' in value and 'sha256' in value:
                if sources.get(str(Path(value['path']).resolve()))!=value['sha256']:
                    raise ValueError('Original context evidence source missing or replaced')
            for key,item in value.items():
                if isinstance(key,str) and Path(key).is_absolute() and isinstance(item,str) and len(item)==64:
                    if sources.get(str(Path(key).resolve()))!=item:raise ValueError('Original evidence hash map omitted')
                check_evidence(item)
        elif isinstance(value,(list,tuple)):
            for item in value:check_evidence(item)
    check_evidence(_restore(context['source_evidence']))
    restored={key:_restore_input(value) for key,value in context['prepared_inputs'].items()}
    if _digest(restored)!=_digest(arguments['inputs']):raise ValueError('Original DELTA typed inputs differ')
    payload=deepcopy(checkpoint);self_sha=payload.pop('checkpoint_sha256')
    if (set(payload)!={'context_sha256','task','status','result'} or self_sha!=encoding._sha(payload) or
        payload['context_sha256']!=encoding._sha(context) or payload['task']!=arguments['task'] or payload['status']!='EVALUATED'):
        raise ValueError('Original DELTA checkpoint binding differs')
    comparison=equivalence.compare_candidate_numerical_inputs(left=arguments,right=dict(arguments,inputs=corrected_inputs))
    if comparison['changed_dependency_fields']!=['incumbent_forward_returns']:
        raise ValueError('Only incumbent-forward dependency may change for paired-only DELTA')
    observed=trace.evaluate_with_window_trace(task=arguments['task'],inputs=arguments['inputs'])
    # The original evaluator already applies its declared output rounding. Use
    # its original canonical encoder for every field, including nested audits.
    if encoding._normalize(observed['result'])!=payload['result']:
        raise ValueError('Original full v3 checkpoint does not reproduce exactly')
    old_result=_restore(payload['result']);windows=observed['historical_window_weights']
    old_rows,old_metrics=_paired_windows(arguments['inputs'],arguments['task'],windows)
    new_rows,new_metrics=_paired_windows(corrected_inputs,arguments['task'],windows)
    for key in PAIRED:
        if abs(old_metrics[key]-old_result[key])>1e-12:raise ValueError('Original paired metric differs: '+key)
    for old,new in zip(old_rows,new_rows):
        if {k:v for k,v in old.items() if not k.startswith('incumbent_')}!={k:v for k,v in new.items() if not k.startswith('incumbent_')}:
            raise ValueError('Candidate/target/fee window changed in paired-only recovery')
    corrected_result=deepcopy(old_result);corrected_result.update(new_metrics)
    for mapping in (comparison['left']['source_hashes'],comparison['right']['source_hashes'],observed['source_hashes']):
        for path,sha in mapping.items():
            if path in sources and sources[path]!=sha:raise ValueError('Conflicting recovery source SHA')
            sources[path]=sha
    equivalence.previous._verify(sources)
    return dict(schema='ndx_delta_paired_trace_recovery_research_v1',result=corrected_result,
        original_result=old_result,historical_window_weights=windows,original_windows=old_rows,corrected_windows=new_rows,
        changed_result_fields=[key for key in PAIRED if old_result[key]!=corrected_result[key]],
        original_full_result_exact=True,original_paired_metric_max_error=max(abs(old_metrics[k]-old_result[k]) for k in PAIRED),
        source_hashes=sources,context_path=str(Path(context_path).resolve()),context_sha256=context_sha256,
        checkpoint_path=str(Path(checkpoint_path).resolve()),checkpoint_sha256=checkpoint_sha256,
        old_trace_numerical_evaluation_count=1,new_input_fit_count=0,no_fit_reuse=False,
        trace_recovery_requires_original_v3_execution=True,point_in_time_verified=False,promotion_allowed=False)
