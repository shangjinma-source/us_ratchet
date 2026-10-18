"""Private adapter around the actual BASE fitter, with exact window-input reuse."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from backtest import ndx_non_equal_fractional_research as base
from backtest import ndx_saved_fractional_window_v2_research as recovery
from scripts import ndx_non_equal_base_runner as checkpoints
from scripts.ndx_joint_weight_verify import _restore_input

SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def _input_digest(inputs):
    return checkpoints.encoding._sha({key:checkpoints.encoding._panel_context(value) for key,value in inputs.items()})


def _read(path,sha):
    import json
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External cache source SHA differs')
    return json.loads(raw)


def evaluate_window_delta(*,arguments,corrected_inputs,checkpoint_path,checkpoint_sha256,
                          context_path,context_sha256,typed_context_path,typed_context_sha256):
    """Run BASE semantics; cached weights must be external-source-bound actual fits.

    This mathematical adapter does not authorize new market data or membership.
    The caller must separately bind its precise correction scope.
    """
    arguments,corrected_inputs=deepcopy((arguments,corrected_inputs))
    if arguments['engine']!='non_equal_fractional_v1':raise ValueError('Original BASE engine required')
    sources=dict(arguments['source_hashes'])
    for path,sha in ((checkpoint_path,checkpoint_sha256),(context_path,context_sha256),(typed_context_path,typed_context_sha256)):
        if sources.get(str(Path(path).resolve()))!=sha:raise ValueError('Original source absent from argument closure')
    context=_read(context_path,context_sha256)
    if (context.get('schema')!='ndx_non_equal_base_context_v1' or type(context.get('planned')) is not int
        or context['planned']!=len(context['tasks'])):
        raise ValueError('Complete original BASE context required')
    typed=_read(typed_context_path,typed_context_sha256)
    for original in (context,typed):
        for path,sha in original.get('source_hashes',{}).items():
            if sources.get(path)!=sha:raise ValueError('Incomplete original input source closure')
    checkpoints._verify_sources(sources)
    if context['source_hashes'].get(str(Path(typed_context_path).resolve()))!=typed_context_sha256:
        raise ValueError('Typed input not in original context closure')
    restored={key:_restore_input(value) for key,value in typed['prepared_inputs'].items()}
    if (_input_digest(restored)!=_input_digest(arguments['inputs']) or context['runtime']!=arguments['runtime'] or
        arguments['task'] not in context['tasks']):raise ValueError('Original input/runtime/task binding differs')
    _read(checkpoint_path,checkpoint_sha256)
    saved=checkpoints._read_checkpoint(Path(checkpoint_path),context_sha256,arguments['task'],context['numerical_sources'])
    original_recovery=recovery.verify_original(arguments=arguments,saved=saved)
    if set(corrected_inputs)!=set(arguments['inputs']):raise ValueError('Exact original input channels required')
    for key in arguments['inputs']:
        if key!='returns' and _input_digest({key:corrected_inputs[key]})!=_input_digest({key:arguments['inputs'][key]}):
            raise ValueError('Return delta cannot change identity/contract/price/benchmark metadata')
    if (not corrected_inputs['returns'].index.equals(arguments['inputs']['returns'].index)
        or not corrected_inputs['returns'].columns.equals(arguments['inputs']['returns'].columns)):
        raise ValueError('Original full return coordinates required')
    # Validate full new inputs before any cache callback can run. Source and
    # runtime checks remain in both the original adapter and BASE evaluator.
    revised=dict(arguments,inputs=corrected_inputs)
    new_proof=recovery.equivalence.candidate_numerical_input_fingerprint(**revised)
    old_inputs=arguments['inputs'];task=arguments['task'];combo=tuple(task['tickers'].split(';'))
    contract=old_inputs['contract'];fit=contract['fit_days'];window=contract['window_days'];step=contract['step_days']
    starts=list(range(fit,len(old_inputs['returns'])-window+1,step))
    anchored=task['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor'
    chain=old_inputs['universe'].set_index('ticker')['risk_chain'].astype(str).to_dict()
    def fingerprint(history,names,parameters):
        keys={'shrinkage_intensity','max_single_weight','min_single_weight','top_weight_cap',
              'minimum_effective_n_ratio','risk_chain_by_ticker','risk_chain_top1_cap',
              'anchor_weights','turnover_anchor_strength'}
        if set(parameters)!=keys or tuple(names)!=combo:raise ValueError('Exact original fitter signature required')
        anchor=parameters['anchor_weights']
        if anchor is not None:
            if not isinstance(anchor,pd.Series) or list(anchor.index)!=list(combo):raise ValueError('Exact anchor coordinates required')
            anchor={ticker:float(anchor[ticker]) for ticker in combo}
        payload=dict(tickers=list(combo),fit_start=str(history.index[0].date()),fit_end=str(history.index[-1].date()),
            fit_count=len(history),values=('K1_CONSTANT_NO_COVARIANCE' if len(combo)==1 else
                checkpoints.encoding._panel_context(history[list(combo)])),
            parameters={key:parameters[key] for key in keys-{'risk_chain_by_ticker','anchor_weights'}},
            risk_chains={ticker:parameters['risk_chain_by_ticker'][ticker] for ticker in combo},
            anchor=(None if len(combo)==1 else anchor))
        return checkpoints.encoding._sha(checkpoints.encoding._normalize(payload))
    expected=[]
    for start,record in zip(starts,saved['historical_window_weights']):
        parameters={key:contract[key] for key in ('shrinkage_intensity','max_single_weight','min_single_weight',
            'top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')}
        parameters.update(risk_chain_by_ticker=chain,
            anchor_weights=None if record['anchor_weights'] is None else pd.Series(record['anchor_weights']).reindex(combo),
            turnover_anchor_strength=contract['turnover_anchor_strength'] if anchored else 0.)
        expected.append(fingerprint(old_inputs['returns'].iloc[start-fit:start],combo,parameters))
    audit=[];actual_binding=base.binding
    def private_bind(function,**dependencies):
        bound=actual_binding._bind(function,**dependencies)
        if function is not actual_binding._SHRINKAGE:return bound
        # This is precisely the fitter just created by the original BASE
        # call chain, including its original certified projection dependencies.
        def cached_fit(history,names,**parameters):
            ordinal=len(audit)
            if ordinal>=len(expected):raise ValueError('Unexpected extra fit invocation')
            start=starts[ordinal]
            if not history.index.equals(old_inputs['returns'].iloc[start-fit:start].index):
                raise ValueError('Fit boundary/order changed')
            key=fingerprint(history,names,parameters)
            record=saved['historical_window_weights'][ordinal]
            hit=key==expected[ordinal]
            if hit:
                weights=pd.Series(record['weights'],index=list(combo),dtype=float)
                if len(combo)==1 and (weights.iloc[0]!=1. or record['risk_chain_projection_relaxed']!=(parameters['risk_chain_top1_cap']<1.)):
                    raise ValueError('Invalid original constant single-name result')
                weights.attrs['risk_chain_projection_relaxed']=record['risk_chain_projection_relaxed']
            else:weights=bound(history,names,**parameters)
            audit.append(dict(ordinal=ordinal,old_fitter_input_sha256=expected[ordinal],new_fitter_input_sha256=key,
                mode='REUSED_EXACT_FITTER_INPUT' if hit else 'REFITTED_ORIGINAL_BASE_FITTER',
                constant_single_name=len(combo)==1,fit_start=record['fit_start'],fit_end=record['fit_end']))
            return weights
        return cached_fit
    proxy=SimpleNamespace(**dict(vars(actual_binding),_bind=private_bind))
    evaluator=actual_binding._bind(base.evaluate_non_equal_fractional,binding=proxy)
    evaluated=evaluator(task=task,inputs=corrected_inputs)
    if len(audit)!=len(starts):raise ValueError('Incomplete observed fit denominator')
    # Original economic execution still computes turnover from the actual
    # prior target, including when this window's fitted weight was cached.
    sources.update(original_recovery['source_hashes']);sources.update(new_proof['source_hashes'])
    sources[str(SOURCE)]=LOADED
    checkpoints._verify_sources(sources)
    return dict(schema='ndx_base_window_delta_research_v1',evaluation=evaluated,window_cache_audit=audit,
        reused_window_count=sum(row['mode']=='REUSED_EXACT_FITTER_INPUT' for row in audit),
        refitted_window_count=sum(row['mode']=='REFITTED_ORIGINAL_BASE_FITTER' for row in audit),
        original_metric_reconstruction_max_error=max(abs(value-saved['result'][key]) for key,value in original_recovery['metrics'].items()),
        source_hashes=sources,cache_checkpoint_sha256=checkpoint_sha256,
        actual_base_fitter_preserved=True,global_module_mutation_performed=False,
        cached_projection_attempts_are_new_attempts=False,
        membership_verified=False,point_in_time_verified=False,promotion_allowed=False)
