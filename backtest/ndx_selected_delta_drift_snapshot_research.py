"""Immutable selected-input snapshots with the one exact recorded cache gap."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from weakref import WeakKeyDictionary
from backtest import ndx_delta_selected_input_research as selected
from backtest import ndx_exact_price_cache_drift_research as drift
from backtest import ndx_legacy_close_accounting_oracle_research as ledger
from scripts import ndx_base_delta_probe_independent_audit as scalar
SOURCE=Path(__file__).resolve();LOADED=drift.file_sha(SOURCE)
STATES=WeakKeyDictionary()
RESTORE_SCOPE='EXTERNAL_SHA_LINEAGE_PLUS_TWENTY_METRICS_WINDOWS_AND_DECIMAL_CLOSE_ACCOUNTING'


class Snapshot:
    __slots__=('__weakref__',)


def read(path,expected):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('External artifact SHA differs')
    return json.loads(raw)


def sources():
    return selected.trace.source_hashes()|selected.equivalence.previous.LOADED|{
        str(SOURCE):LOADED,str(selected.SOURCE):selected.LOADED,str(drift.SOURCE):drift.LOADED,
        str(selected.provenance.SOURCE):selected.provenance.LOADED,str(selected.provenance.previous.SOURCE):selected.provenance.previous.LOADED,
        str(selected.equivalence.SOURCE):selected.equivalence.LOADED_SHA,
        str(Path(ledger.__file__).resolve()):LEDGER_SHA,str(Path(scalar.__file__).resolve()):SCALAR_SHA}


LEDGER_SHA=drift.file_sha(ledger.__file__);SCALAR_SHA=drift.file_sha(scalar.__file__)


def merge(target,addition):
    for path,sha in addition.items():
        path=str(Path(path).resolve())
        if path in target and target[path]!=sha:raise ValueError('Conflicting source SHA')
        target[path]=sha


def state(snapshot):
    if type(snapshot) is not Snapshot or snapshot not in STATES or STATES[snapshot]['closed']:
        raise ValueError('Unknown or closed selected snapshot')
    return STATES[snapshot]


def begin(*,manifest_path,manifest_sha256):
    manifest_path=str(Path(manifest_path).resolve());manifest=read(manifest_path,manifest_sha256)
    if manifest['schema']!='ndx_selected_delta_exact_gap_manifest_v1':raise ValueError('Selected exact-gap manifest required')
    if manifest['parent_plan_path']!=str(drift.SELECTED_PLAN) or manifest['parent_plan_sha256']!=drift.SELECTED_PLAN_SHA:
        raise ValueError('Hard original selected plan required')
    parent=read(drift.SELECTED_PLAN,drift.SELECTED_PLAN_SHA)
    if manifest['tasks']!=[r for day in parent['dates'] for r in day['tasks']] or manifest['corrections']!=parent['errors']:
        raise ValueError('Exact selected tasks and corrections required')
    expected=dict(parent['source_hashes']);merge(expected,manifest['historical_expected_source_hashes']);merge(expected,sources())
    merge(expected,{manifest_path:manifest_sha256,str(drift.SELECTED_PLAN):drift.SELECTED_PLAN_SHA})
    contract=drift.load_contract();drift.verify_expected_sources(expected,contract)
    contexts={};rows={}
    for row in manifest['tasks']:
        identifier=row['new_job_id'];path=row['context_path']
        if identifier in rows or expected.get(path)!=row['context_sha256'] or expected.get(row['checkpoint_path'])!=row['checkpoint_sha256']:
            raise ValueError('Task context/checkpoint source mismatch')
        if path not in contexts:
            context=read(path,row['context_sha256'])
            if context['runtime']!=selected.current_runtime():raise ValueError('Actual numerical runtime differs')
            inputs={k:selected._restore_input(v) for k,v in context['prepared_inputs'].items()};changed=deepcopy(inputs)
            for ticker,date,old,new in selected.CORRECTIONS:
                if changed['returns'].loc[date,ticker]!=old:raise ValueError('Original correction differs')
                changed['returns'].loc[date,ticker]=new
            gaps=selected.provenance.validate_historical_evidence(context,expected)
            if parent['historical_context_gap_observations'][path]!=dict(context_sha256=row['context_sha256'],gaps=gaps):
                raise ValueError('Original config gap observation differs')
            contexts[path]=dict(context=context,inputs=inputs,changed=changed,gaps=gaps,
                original_digest=selected.provenance._digest(inputs),corrected_digest=selected.provenance._digest(changed))
        if row['task'] not in contexts[path]['context']['tasks'] or row['runtime']!=contexts[path]['context']['runtime']:
            raise ValueError('Original task/runtime mismatch')
        rows[identifier]=row
    if len(rows)!=manifest['planned'] or len(contexts)!=manifest['context_count']:raise ValueError('Full manifest denominator differs')
    snapshot=Snapshot();STATES[snapshot]=dict(manifest=manifest,parent=parent,path=manifest_path,sha=manifest_sha256,
        expected=expected,contract=contract,contexts=contexts,rows=rows,records={},additional={},closed=False,busy=False)
    verify_all(STATES[snapshot]);return snapshot


def check_memory(item):
    if selected.provenance._digest(item['inputs'])!=item['original_digest'] or selected.provenance._digest(item['changed'])!=item['corrected_digest']:
        raise ValueError('Captured typed input changed')


def verify_all(s):
    verification=drift.verify_expected_sources(s['expected'],s['contract'])
    for p,h in s['additional'].items():
        if drift.file_sha(p)!=h:raise ValueError('External provenance changed')
    for item in s['contexts'].values():
        check_memory(item)
        if item['context']['runtime']!=selected.current_runtime():raise ValueError('Actual numerical runtime changed')
        if selected.provenance.validate_historical_evidence(item['context'],s['expected'])!=item['gaps']:
            raise ValueError('Historical config observation changed')
    return verification


def verify_small(s,mapping):
    for p,h in mapping.items():
        if s['expected'].get(p)!=h:raise ValueError('Unverified snapshot source or SHA')
        if Path(p).suffix.lower()=='.py' and drift.file_sha(p)!=h:raise ValueError('Numerical source changed')


def wrap(s,row,item,result,mode):
    return dict(schema='ndx_selected_delta_exact_gap_task_v1',new_job_id=row['new_job_id'],original=row,result=result,
        manifest_path=s['path'],manifest_sha256=s['sha'],mode=mode,
        input_digests=dict(original=item['original_digest'],corrected=item['corrected_digest']),
        saved_result_revalidation_scope=RESTORE_SCOPE,
        non20_risk_projection_fields_independently_recomputed=False,
        historical_full_source_closure_verified=False,source_closure_finalized=False,
        original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)


def evaluate(snapshot,identifier):
    s=state(snapshot)
    if s['busy'] or identifier not in s['rows']:raise ValueError('Unknown or concurrent task')
    row=s['rows'][identifier];item=s['contexts'][row['context_path']];check_memory(item);verify_small(s,sources())
    if row['runtime']!=selected.current_runtime():raise ValueError('Actual runtime differs')
    if identifier in s['records']:return deepcopy(s['records'][identifier])
    checkpoint=read(row['checkpoint_path'],row['checkpoint_sha256']);s['busy']=True
    try:
        bind=selected.trace.binding._bind
        def captured(path,sha):
            if str(Path(path).resolve())==row['context_path'] and sha==row['context_sha256']:return deepcopy(item['context'])
            if str(Path(path).resolve())==row['checkpoint_path'] and sha==row['checkpoint_sha256']:return deepcopy(checkpoint)
            raise ValueError('Read outside captured task')
        small=lambda mapping:verify_small(s,mapping)
        old=selected.equivalence.previous
        old_proxy=SimpleNamespace(**dict(vars(old),_verify=small,candidate_numerical_input_fingerprint=bind(old.candidate_numerical_input_fingerprint,_verify=small)))
        eq=selected.equivalence;fingerprint=bind(eq.candidate_numerical_input_fingerprint,previous=old_proxy)
        eq_proxy=SimpleNamespace(**dict(vars(eq),previous=old_proxy,candidate_numerical_input_fingerprint=fingerprint,
            compare_candidate_numerical_inputs=bind(eq.compare_candidate_numerical_inputs,previous=old_proxy,candidate_numerical_input_fingerprint=fingerprint)))
        provenance=SimpleNamespace(**dict(vars(selected.provenance),_read=captured))
        run=bind(selected.evaluate_selected_delta,equivalence=eq_proxy,provenance=provenance)
        result=run(arguments=dict(task=row['task'],inputs=item['inputs'],engine='joint_weight_v3',runtime=row['runtime'],source_hashes=s['expected']),
            corrected_inputs=item['changed'],context_path=row['context_path'],context_sha256=row['context_sha256'],
            checkpoint_path=row['checkpoint_path'],checkpoint_sha256=row['checkpoint_sha256'])
        verify_small(s,result.pop('source_hashes'));check_memory(item)
        output=wrap(s,row,item,result,'ONE_NEW_INPUT_FULL_V3_EVALUATION_NO_OLD_WINDOW_REUSE')
        s['records'][identifier]=deepcopy(output);return output
    finally:s['busy']=False


def validate_saved(s,row,result):
    item=s['contexts'][row['context_path']];check_memory(item)
    if row['runtime']!=selected.current_runtime():raise ValueError('Actual runtime differs')
    checkpoint=read(row['checkpoint_path'],row['checkpoint_sha256'])
    if (result['schema']!='ndx_delta_selected_input_research_v1' or result['original_task']!=row['task']
        or result['checkpoint_path']!=row['checkpoint_path'] or result['checkpoint_sha256']!=row['checkpoint_sha256']
        or result['context_path']!=row['context_path'] or result['context_sha256']!=row['context_sha256']
        or result['original_input_sha256']!=item['original_digest'] or result['new_input_sha256']!=item['corrected_digest']
        or result['original_result_lineage_sha256']!=selected.encoding._sha(checkpoint['result'])
        or result['observed_runtime']!=row['runtime'] or result['actual_runtime_matches_original_context'] is not True):
        raise ValueError('Saved result input/lineage/runtime differs')
    for flag in ('original_result_reproduced','window_fit_reuse_performed','old_window_targets_available','original_historical_provenance_verified','point_in_time_verified','promotion_allowed','selection_performed'):
        if result[flag] is not False:raise ValueError('Saved result upgraded unsupported flag')
    if (type(result['old_input_numerical_evaluation_count']) is not int or result['old_input_numerical_evaluation_count']!=0
        or type(result['new_input_numerical_evaluation_count']) is not int or result['new_input_numerical_evaluation_count']!=1
        or result['no_fit_reuse'] is not False or result['exact_three_return_cells_only'] is not True
        or result['nominal_execution_semantics']!='ORIGINAL_V3_UNCHANGED'
        or result['reconstruction_scope']!='NEW_INPUT_FULL_V3_WITH_HISTORICAL_LOADER_PROVENANCE_GAP'):
        raise ValueError('Saved evaluation count differs')
    inputs=item['changed'];windows=result['historical_window_weights'];contract=inputs['contract'];task=row['task']
    def finite_tree(value):
        if type(value) is float and not math.isfinite(value):raise ValueError('Nonfinite saved result field')
        if isinstance(value,dict):
            for child in value.values():finite_tree(child)
        elif isinstance(value,(list,tuple)):
            for child in value:finite_tree(child)
    finite_tree(result)
    def numeric_close(actual,saved,tolerance=1e-12):
        return (type(saved) in (int,float) and math.isfinite(saved) and
                type(actual) in (int,float) and math.isfinite(actual) and abs(actual-saved)<=tolerance)
    # Validate actual history/anchor/date/simplex via existing pure window math,
    # then independently audit saved economic outputs and legacy Close ledger.
    _,paired=selected.provenance.previous._paired_windows(inputs,task,windows)
    returns={t:list(inputs['returns'][t]) for t in inputs['returns'].columns}
    rows,metrics=scalar.economics(returns,list(inputs['target_returns']),inputs['incumbent_weights'],contract,windows)
    if len(rows)!=len(result['new_windows']):raise ValueError('Saved window denominator differs')
    for computed,saved in zip(rows,result['new_windows']):
        if any(not numeric_close(v,saved[k]) for k,v in computed.items()):raise ValueError('Saved window scalar differs')
    if any(not numeric_close(v,result['result'][k]) for k,v in metrics.items()):raise ValueError('Saved twenty metrics differ')
    starts=list(range(contract['fit_days'],len(inputs['returns'])-contract['window_days']+1,contract['step_days']))
    dates=[str(x.date()) for x in inputs['returns'].index]
    if type(result['new_fitted_window_count']) is not int or result['new_fitted_window_count']!=len(starts):
        raise ValueError('Saved actual window count differs')
    for start,saved_window in zip(starts,result['new_windows']):
        if (saved_window['start'],saved_window['end'])!=(dates[start],dates[start+contract['window_days']-1]):
            raise ValueError('Saved forward window dates differ')
    schedule={dates[start]:w['weights'] for start,w in zip(starts,windows)}
    price=inputs['nominal_prices'].loc[dates[starts[0]]:dates[starts[-1]+contract['window_days']-1],task['tickers'].split(';')]
    universe=inputs['universe'].set_index('ticker')
    actual=ledger.account(dates=[str(x.date()) for x in price.index],prices={t:list(price[t]) for t in price.columns},schedule=schedule,
        risk_chains={t:universe.loc[t,'risk_chain'] for t in price.columns},contract=contract)['summary']
    independent_shares=[];residuals=[]
    for start,window in zip(starts,windows):
        marks=inputs['nominal_prices'].loc[dates[start]]
        investable=ledger.number(contract['portfolio_cash_usd'])-ledger.number(contract['minimum_cash_buffer_usd'])
        shares={t:int(investable*ledger.number(window['weights'][t])/ledger.number(float(marks[t]))) for t in price.columns}
        independent_shares.append(shares)
        residuals.append(float(ledger.number(contract['portfolio_cash_usd'])-sum(shares[t]*ledger.number(float(marks[t])) for t in price.columns)))
    actual.update(whole_lot_min_shares=min(min(x.values()) for x in independent_shares),
        whole_lot_residual_cash_p50=scalar.quantile(residuals,.5),
        whole_lot_executable_all_windows=actual['whole_lot_cash_buffer_preserved'] and actual['whole_lot_constraints_preserved_all_days'] and all(min(x.values())>=1 for x in independent_shares),
        whole_lot_executability=actual['whole_lot_execution_mode'])
    for key,value in actual.items():
        saved=result['result'][key]
        if type(value) is float:
            if not numeric_close(value,saved,1e-8+1e-12*abs(value)):raise ValueError('Saved Close accounting differs')
        elif type(value) is not type(saved) or value!=saved:raise ValueError('Saved Close state/constraint differs')
    if result['historical_loader_provenance_gaps']!=item['gaps']:raise ValueError('Saved config gap differs')


def track(s,path,sha):
    path=str(Path(path).resolve())
    for mapping in (s['expected'],s['additional']):
        if path in mapping and mapping[path]!=sha:raise ValueError('External source collision')
    if drift.file_sha(path)!=sha:raise ValueError('External provenance SHA differs')
    s['additional'][path]=sha


def import_probe(snapshot,path,sha):
    s=state(snapshot);probe=read(path,sha);identifier=probe['selected']['task']['new_job_id']
    validate_import_reference(s,path,sha,identifier)
    if identifier in s['records'] or probe['selected']!=s['parent']['probe'] or probe['plan_sha256']!=drift.SELECTED_PLAN_SHA:
        raise ValueError('Original completed probe differs')
    result=deepcopy(probe['result']);verify_small(s,result.pop('source_hashes'));row=s['rows'][identifier]
    validate_saved(s,row,result);track(s,path,sha)
    output=wrap(s,row,s['contexts'][row['context_path']],result,'EXTERNAL_FIRST_PROBE_IMPORTED_WITHOUT_NEW_FIT')
    output.update(imported_probe_path=str(Path(path).resolve()),imported_probe_sha256=sha)
    s['records'][identifier]=deepcopy(output);return output


def validate_import_reference(s,path,sha,identifier):
    if dict(path=str(Path(path).resolve()),sha256=sha,new_job_id=identifier)!=s['manifest']['completed_probe']:
        raise ValueError('Imported probe must use exact manifest path/SHA/task')


def restore(snapshot,path,sha):
    s=state(snapshot);value=read(path,sha);identifier=value['new_job_id']
    if identifier not in s['rows'] or identifier in s['records']:raise ValueError('Unknown/duplicate saved task')
    row=s['rows'][identifier]
    if value['original']!=row or value['manifest_path']!=s['path'] or value['manifest_sha256']!=s['sha']:raise ValueError('Saved manifest/task differs')
    for flag in ('historical_full_source_closure_verified','original_historical_provenance_verified','point_in_time_verified','promotion_allowed'):
        if value[flag] is not False:raise ValueError('Saved task upgraded unsupported flag')
    if value['non20_risk_projection_fields_independently_recomputed'] is not False or value['saved_result_revalidation_scope']!=RESTORE_SCOPE:
        raise ValueError('Saved task upgraded revalidation disclosure')
    item=s['contexts'][row['context_path']]
    if value['input_digests']!=dict(original=item['original_digest'],corrected=item['corrected_digest']):
        raise ValueError('Saved typed input digest differs')
    validate_saved(s,row,value['result']);track(s,path,sha)
    if value['mode']=='EXTERNAL_FIRST_PROBE_IMPORTED_WITHOUT_NEW_FIT':
        validate_import_reference(s,value['imported_probe_path'],value['imported_probe_sha256'],identifier)
        track(s,value['imported_probe_path'],value['imported_probe_sha256'])
    elif value['mode']!='ONE_NEW_INPUT_FULL_V3_EVALUATION_NO_OLD_WINDOW_REUSE':raise ValueError('Unknown task mode')
    s['records'][identifier]=deepcopy(value);return value


def finish(snapshot):
    s=state(snapshot)
    if s['busy']:raise ValueError('Task still evaluating')
    try:
        checked=verify_all(s)
        return dict(schema='ndx_selected_delta_exact_gap_finalization_v1',planned=len(s['rows']),completed=len(s['records']),
            status='COMPLETE' if len(s['records'])==len(s['rows']) else 'PARTIAL',
            verified_source_hashes=checked['verified_source_hashes'],historical_expected_source_hashes=s['expected'],
            historical_price_cache_gap_observations=checked['historical_gap_observations'],additional_provenance_hashes=s['additional'],
            historical_full_source_closure_verified=False,immutable_numerical_source_closure_verified=True,
            original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
    finally:s['closed']=True


def verify_finished(snapshot):
    if snapshot not in STATES or not STATES[snapshot]['closed']:raise ValueError('Finalized snapshot required')
    verify_all(STATES[snapshot])
