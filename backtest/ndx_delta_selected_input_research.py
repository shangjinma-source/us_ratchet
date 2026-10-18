"""One complete new-input v3 evaluation; original results are lineage only."""
from copy import deepcopy
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from backtest import ndx_delta_paired_trace_recovery_v2_research as provenance
from backtest import ndx_delta_window_trace_research as trace
from backtest import ndx_candidate_input_equivalence_v2_research as equivalence
from backtest import ndx_joint_weight_runner as encoding
from scripts.ndx_joint_weight_verify import _restore, _restore_input

SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
ROOT=SOURCE.parents[1]
CORRECTIONS=(('GOOG','2022-07-18',0.,-.025335378898117544),
             ('GOOGL','2022-07-18',0.,-.024580059928059006),
             ('FTNT','2022-06-23',0.,.019968386675822902))
EVIDENCE={
    str(ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json'):
        'a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b',
    str(ROOT/'data/cache/research/legacy_pool_additional_split_probe_20260912_v1/report.json'):
        '64e6c86a9ad8045dcb925990c04a7d00c8480cdec2e922ef215e9ed839acd850'}


def current_runtime():
    return dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)


def correction_sources():
    sources=dict(EVIDENCE)
    for path,expected in EVIDENCE.items():
        report=provenance._read(path,expected)
        for source,digest in report['source_hashes'].items():
            if source in sources and sources[source]!=digest:raise ValueError('Conflicting correction evidence')
            sources[source]=digest
    return sources


def evaluate_selected_delta(*,arguments,corrected_inputs,context_path,context_sha256,checkpoint_path,checkpoint_sha256):
    arguments,corrected_inputs=deepcopy((arguments,corrected_inputs))
    sources=dict(arguments['source_hashes'])
    def merge(mapping):
        for path,digest in mapping.items():
            path=str(Path(path).resolve())
            if path in sources and sources[path]!=digest:raise ValueError('Conflicting selected-delta source')
            sources[path]=digest
    for path,digest in ((context_path,context_sha256),(checkpoint_path,checkpoint_sha256)):
        if sources.get(str(Path(path).resolve()))!=digest:raise ValueError('External original artifact missing')
    merge(correction_sources())
    merge(trace.source_hashes())
    merge({str(SOURCE):LOADED,str(provenance.SOURCE):provenance.LOADED,
           str(provenance.previous.SOURCE):provenance.previous.LOADED,
           str(equivalence.SOURCE):equivalence.LOADED_SHA})
    equivalence.previous._verify(sources)
    try:
        if arguments['engine']!='joint_weight_v3':raise ValueError('Original DELTA v3 required')
        context=provenance._read(context_path,context_sha256)
        checkpoint=provenance._read(checkpoint_path,checkpoint_sha256)
        task=arguments['task']
        observed_runtime=current_runtime()
        if context['runtime']!=observed_runtime:raise ValueError('Original runtime differs from actual process runtime')
        if (context['schema']!='ndx_joint_weight_checkpoint_v1' or context['runtime']!=arguments['runtime']
                or task not in context['tasks'] or context['numerical_sources']!=trace.full._LOADED_SOURCES):
            raise ValueError('Original context/task/runtime/numerical source mismatch')
        gaps=provenance.validate_historical_evidence(context,sources)
        restored={key:_restore_input(value) for key,value in context['prepared_inputs'].items()}
        if provenance._digest(restored)!=provenance._digest(arguments['inputs']):
            raise ValueError('Original six typed inputs mismatch')
        payload=deepcopy(checkpoint);self_sha=payload.pop('checkpoint_sha256')
        if (set(payload)!={'context_sha256','task','status','result'} or self_sha!=encoding._sha(payload)
                or payload['context_sha256']!=encoding._sha(context) or payload['task']!=task or payload['status']!='EVALUATED'):
            raise ValueError('Original checkpoint identity/content mismatch')
        original_result=_restore(payload['result'])
        if any(original_result.get(key)!=task[key] for key in ('tickers','holding_count','weight_spec')):
            raise ValueError('Original result task identity mismatch')
        expected=deepcopy(arguments['inputs'])
        for ticker,date,old,new in CORRECTIONS:
            if expected['returns'].loc[date,ticker]!=old:raise ValueError('Original evidenced return cell mismatch')
            expected['returns'].loc[date,ticker]=new
        if provenance._digest(expected)!=provenance._digest(corrected_inputs):
            raise ValueError('Only the exact three evidenced return cells may change')
        arguments['source_hashes']=sources
        comparison=equivalence.compare_candidate_numerical_inputs(left=arguments,right=dict(arguments,inputs=corrected_inputs))
        changed=comparison['changed_dependency_fields']
        if 'selected_returns' not in changed or not set(changed)<={'selected_returns','incumbent_forward_returns'}:
            raise ValueError('Selected fitted/forward dependency must actually change')
        if type(task['holding_count']) is not int or task['holding_count']<2:
            raise ValueError('Selected DELTA cohort requires k >= 2')
        merge(comparison['left']['source_hashes']);merge(comparison['right']['source_hashes'])
        before_digest=provenance._digest(corrected_inputs)
        observed=trace.evaluate_with_window_trace(task=task,inputs=corrected_inputs)
        if provenance._digest(corrected_inputs)!=before_digest:raise ValueError('New evaluator mutated its inputs')
        merge(observed['source_hashes'])
        # Recompute all window candidate/target/fee and paired measures from the
        # actual new targets; no old targets are inferred or reused.
        windows,paired=provenance.previous._paired_windows(corrected_inputs,task,observed['historical_window_weights'])
        if any(abs(paired[key]-observed['result'][key])>1e-12 for key in provenance.previous.PAIRED):
            raise ValueError('New traced window aggregates disagree with full v3')
        if provenance.validate_historical_evidence(context,sources)!=gaps:
            raise ValueError('Historical loader gap observation changed')
        return dict(schema='ndx_delta_selected_input_research_v1',result=observed['result'],
            historical_window_weights=observed['historical_window_weights'],new_windows=windows,
            source_hashes=sources,context_path=str(Path(context_path).resolve()),context_sha256=context_sha256,
            checkpoint_path=str(Path(checkpoint_path).resolve()),checkpoint_sha256=checkpoint_sha256,
            original_task=task,original_result_lineage_sha256=encoding._sha(payload['result']),
            original_result_reproduced=False,old_input_numerical_evaluation_count=0,
            new_input_numerical_evaluation_count=1,new_fitted_window_count=len(windows),
            original_input_sha256=provenance._digest(restored),new_input_sha256=before_digest,
            changed_dependency_fields=changed,exact_three_return_cells_only=True,
            observed_runtime=observed_runtime,actual_runtime_matches_original_context=True,
            old_window_targets_available=False,window_fit_reuse_performed=False,no_fit_reuse=False,
            nominal_execution_semantics='ORIGINAL_V3_UNCHANGED',
            historical_loader_provenance_gaps=gaps,original_historical_provenance_verified=False,
            reconstruction_scope='NEW_INPUT_FULL_V3_WITH_HISTORICAL_LOADER_PROVENANCE_GAP',
            point_in_time_verified=False,promotion_allowed=False,selection_performed=False)
    finally:
        equivalence.previous._verify(sources)
