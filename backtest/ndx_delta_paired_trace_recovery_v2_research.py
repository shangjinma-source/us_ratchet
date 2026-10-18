"""Explicit numerical reconstruction with one narrowly declared historical loader gap."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from backtest import ndx_delta_paired_trace_recovery_research as previous
from backtest import ndx_delta_window_trace_research as trace
from backtest import ndx_candidate_input_equivalence_v2_research as equivalence
from backtest import ndx_joint_weight_runner as encoding
from scripts.ndx_joint_weight_verify import _restore, _restore_input
from backtest.ndx_delta_paired_trace_recovery_research import _read, _digest, _paired_windows, PAIRED

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
GAP_PATH=str((SOURCE.parents[1]/'config/ndx_cardinality_discovery_v1.yaml').resolve())
GAP_EXPECTED_SHA='1f85b1d848c5a884290b9a8edc89efd4a9d8520c271ad9581c33c3601e72d78e'


def validate_historical_evidence(context,sources):
    """Never edit the original evidence; report the single explicit old pointer."""
    gaps={}
    def pointer(path,expected):
        path=str(Path(path).resolve())
        if sources.get(path)==expected:return
        if path!=GAP_PATH or expected!=GAP_EXPECTED_SHA:
            raise ValueError('Other original evidence source missing or replaced')
        observed=hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None
        if observed==expected:raise ValueError('Available original evidence must be explicitly source-bound')
        gaps[path]=dict(path=path,expected_historical_sha256=expected,observed_current_sha256=observed,
            status='UNAVAILABLE' if observed is None else 'HISTORICAL_SOURCE_DRIFT',
            used_as_current_numerical_input=False,original_pointer_preserved=True)
    def visit(value):
        if isinstance(value,dict):
            if 'path' in value and 'sha256' in value:pointer(value['path'],value['sha256'])
            for key,item in value.items():
                if isinstance(key,str) and Path(key).is_absolute() and isinstance(item,str) and len(item)==64:pointer(key,item)
                visit(item)
        elif isinstance(value,(list,tuple)):
            for item in value:visit(item)
    visit(_restore(context['source_evidence']))
    if len(gaps)!=1:raise ValueError('Exactly the explicitly declared historical loader gap required')
    return list(gaps.values())


def recover_paired_delta(*,arguments,corrected_inputs,context_path,context_sha256,checkpoint_path,checkpoint_sha256):
    arguments,corrected_inputs=deepcopy((arguments,corrected_inputs));sources=dict(arguments['source_hashes'])
    if arguments['engine']!='joint_weight_v3':raise ValueError('Original DELTA v3 required')
    for path,sha in ((context_path,context_sha256),(checkpoint_path,checkpoint_sha256)):
        if sources.get(str(Path(path).resolve()))!=sha:raise ValueError('Original external artifact absent from closure')
    for path,sha in (trace.source_hashes()|{str(SOURCE):LOADED,str(previous.SOURCE):previous.LOADED}).items():
        if path in sources and sources[path]!=sha:raise ValueError('Conflicting loaded source SHA')
        sources[path]=sha
    equivalence.previous._verify(sources)
    context=_read(context_path,context_sha256);checkpoint=_read(checkpoint_path,checkpoint_sha256)
    if (context['schema']!='ndx_joint_weight_checkpoint_v1' or context['runtime']!=arguments['runtime'] or
        arguments['task'] not in context['tasks']):raise ValueError('Original DELTA context/task/runtime differs')
    if context['numerical_sources']!=trace.full._LOADED_SOURCES:raise ValueError('Original v3 numerical closure differs')
    gaps=validate_historical_evidence(context,sources)
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
    if validate_historical_evidence(context,sources)!=gaps:raise ValueError('Historical gap observation changed during reconstruction')
    return dict(schema='ndx_delta_paired_trace_recovery_research_v2',result=corrected_result,
        original_result=old_result,historical_window_weights=windows,original_windows=old_rows,corrected_windows=new_rows,
        changed_result_fields=[key for key in PAIRED if old_result[key]!=corrected_result[key]],
        original_full_result_exact=True,original_paired_metric_max_error=max(abs(old_metrics[k]-old_result[k]) for k in PAIRED),
        source_hashes=sources,context_path=str(Path(context_path).resolve()),context_sha256=context_sha256,
        checkpoint_path=str(Path(checkpoint_path).resolve()),checkpoint_sha256=checkpoint_sha256,
        reconstruction_scope='NUMERICAL_RECONSTRUCTION_WITH_HISTORICAL_LOADER_PROVENANCE_GAP',
        historical_loader_provenance_gaps=gaps,original_historical_provenance_verified=False,
        old_trace_numerical_evaluation_count=1,new_input_fit_count=0,no_fit_reuse=False,
        trace_recovery_requires_original_v3_execution=True,point_in_time_verified=False,promotion_allowed=False)
