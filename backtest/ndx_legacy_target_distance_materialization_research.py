"""One explicit LEGACY_TARGET_DISTANCE-lane target at a time; durable raw-first, never trades."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
DATES=('2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01')
CUTOFFS=('2023-03-31','2023-04-28','2023-05-31','2023-06-30','2023-07-31','2023-08-31')
SCHEMA='LEGACY_TARGET_DISTANCE_SIX_PERIOD_STRATEGIC_TARGET_PLAN_V1'
ROOT=SOURCE.parents[1]
HARD_LANE=dict(path=str(ROOT/'data/cache/research/cutoff_training_lanes_20260923_v2/prepare.json'),
    sha256='b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba')
OUTPUT=ROOT/'data/cache/research/legacy_target_distance_targets_20260923_v1'
JOBS=('bb73a78d49b97c61a601006d1774a384a9f706973b0fa9602e69c0f52dd004f8',
 'dfe51ac1cff3fb16a70a245adada700653f96e326960574a72dc4f9db86836d8',
 '197a4eae41deab2f7df7d60f53af6452faa3a4cdc8e9d5420bbf79fd8ff118d8',
 '168c338b01b69fb367e56055ab8872719ae9eae450db8d17bcbc9bc5b46ed942',
 '2404683b9d674d8d9ff0afc59755a2c24325ea41ab25a68fc10b1cdf9ede427c',
 '8348e51fd09a5a9de6eb432a34cf64ad32850140b261509f4339157a9fb5eba1')
MODES=('DETERMINISTIC_EQUAL','NEW_ANCHORED_FIT','NEW_UNANCHORED_FIT',
 'NEW_ANCHORED_FIT','DETERMINISTIC_EQUAL','DETERMINISTIC_EQUAL')
SPECS=('equal_weight','constrained_fixed_shrinkage_turnover_anchor','constrained_fixed_shrinkage',
 'constrained_fixed_shrinkage_turnover_anchor','equal_weight','equal_weight')
HARD_CALENDAR=dict(path=str(ROOT/'data/cache/research/dynamic_frozen_v2/preference_retrospective_accounting_20260912.json'),
    sha256='3b0fd632ba5c53839b90199d7edf74dafdc73bdc9b3369d09bef24fdae177e59')


def expected_plan():
    return dict(schema=SCHEMA,lane_prepare=deepcopy(HARD_LANE),calendar=deepcopy(HARD_CALENDAR),
        selected_job_ids=list(JOBS),materialization_modes=list(MODES),weight_specs=list(SPECS))


def mode_counts(index):
    equal=MODES[index]=='DETERMINISTIC_EQUAL'
    return dict(materialization_mode=MODES[index],wrapper_call_attempt_count=1,
        deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0,
        optimizer_called_by_equal_branch=False if equal else None)


def planned_counts(index):
    counts=mode_counts(index)
    return dict(materialization_mode=counts.pop('materialization_mode'),
        optimizer_called_by_equal_branch=counts.pop('optimizer_called_by_equal_branch'),planned_operation_counts=counts)


def require(condition,message):
    if not condition:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read(reference,sources):
    require(type(reference) is dict and set(reference)=={'path','sha256'},'Exact external reference required')
    path=str(Path(reference['path']).resolve());raw=Path(path).read_bytes();actual=hashlib.sha256(raw).hexdigest()
    require(actual==reference['sha256'],'External source changed: '+path)
    require(path not in sources or sources[path]==actual,'Conflicting source hash')
    sources[path]=actual
    return json.loads(raw)


def verify(sources):
    for path,expected in sources.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected,'Source changed: '+path)


def publish(path,value):
    path=Path(path);raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as handle:
        handle.write(raw);handle.flush();os.fsync(handle.fileno())
    require(path.read_bytes()==raw,'Published bytes changed')
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest())


def complete_candidate(choice,queue,frontier,universe,sources):
    """Restore a hard lane choice from the full cohort, not the old fit subqueue."""
    complete=read(frontier['complete_date_artifact'],sources)
    independent=read(frontier['independent_full_diff_artifact'],sources)
    require(frontier['schema']=='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1' and
        frontier['coordinate']==queue['coordinate']==complete['coordinate'] and
        frontier['original_decision_data_end']==queue['historical_cutoff'],'Full cohort coordinate differs')
    records=complete['records'];diagnostics=frontier['candidate_diagnostics'];count=frontier['original_count']
    require(type(count) is int and len(records)==len(diagnostics)==complete['original_count']==queue['full_original_count']==count and
        len({r['task']['job_id'] for r in records})==len({r['job_id'] for r in diagnostics})==count and
        {r['task']['job_id'] for r in records}=={r['job_id'] for r in diagnostics} and
        complete['economic_inputs_complete'] is True and type(complete['pending_count']) is int and complete['pending_count']==0,
        'Complete original task denominator required')
    require(independent['schema']=='SELECTED_ARCHIVE_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1' and
        independent['date']==queue['coordinate']['selection_date'] and independent['original_count']==count and
        Path(independent['output_path']).resolve()==Path(frontier['complete_date_artifact']['path']).resolve() and
        independent['output_sha256']==frontier['complete_date_artifact']['sha256'] and
        all(independent[key] is True for key in ('whole_date_task_map_verified','ordered_full_record_diff_verified',
            'full_new_results_match_external_checkpoints','output_source_partitions_reverified')),'Full independent diff binding differs')
    matches=[r for r in records if r['task']['job_id']==choice['job_id']]
    rows=[r for r in diagnostics if r['job_id']==choice['job_id']]
    require(len(matches)==len(rows)==1,'Chosen job absent from full original records')
    record=matches[0];task=record['task'];result=record['result'];diagnostic=rows[0]
    require(record['status']=='AVAILABLE' and task['decision_data_end']==queue['historical_cutoff'] and
        all(task[k]==queue['coordinate'][k] for k in ('selection_date','source_batch','universe_track')),
        'Original chosen task cutoff/scope differs')
    require(all(type(task[k]) is type(choice[k]) and task[k]==choice[k]==result[k]==diagnostic[k]
        for k in ('tickers','holding_count','weight_spec')) and diagnostic['fractional_risk_liquidity_passed'] is True,
        'Original candidate identity or original eligibility differs')
    names=task['tickers'].split(';')
    require(len(names)==len(set(names))==task['holding_count'] and all(name in universe for name in names),
        'Full candidate cardinality or universe differs')
    selected={universe[name]['security_id']:{k:universe[name][k] for k in ('ticker','issuer_id','risk_chain')} for name in names}
    require(selected==choice['selected'] and all(result[k]==v for k,v in choice['metrics'].items()),
        'Hard training choice identity or ranking evidence differs')
    require(not any(row['task']['job_id']==choice['job_id'] for row in queue['candidates']),
        'Unexpected old fit-subqueue membership for fixed LEGACY jobs')
    return selected,dict(origin='HARD_COMPLETE_TRAINING_RECORD',complete_date_reference=deepcopy(frontier['complete_date_artifact']),
        independent_full_diff_reference=deepcopy(frontier['independent_full_diff_artifact']),original_task=deepcopy(task),
        old_queue_candidate_present=False)


def prepare_plan(plan_reference):
    """Restore only saved matrices; no optimizer or account engine invocation."""
    from backtest import ndx_corrected_cutoff_snapshot_research as snapshot
    from backtest import ndx_dynamic_refit_schedule_research as schedule
    from backtest import ndx_corrected_explicit_path_research as calendar_contract
    adapter=snapshot.adapter
    sources={str(SOURCE):LOADED_SHA}
    plan=read(plan_reference,sources)
    require(plan==expected_plan(),'Exact predeclared LEGACY_TARGET_DISTANCE-only plan required')
    require(Path(plan_reference['path']).resolve()==OUTPUT/'plan.json','Fixed plan coordinate required')
    lane=read(plan['lane_prepare'],sources)
    require(lane.get('schema')=='CUTOFF_TRAINING_LANE_DEPENDENCY_PREPARE_V1'
        and lane.get('fit_performed') is False and lane.get('continuous_target_schedule_built') is False,
        'Unexecuted source-bound lane preparation required')
    for path,sha in lane['prepare_source_hashes'].items():
        require(path not in sources or sources[path]==sha,'Conflicting preparation sources');sources[path]=sha
    verify(sources)
    require(plan['calendar']==calendar_contract.CALENDAR_SOURCE,'Hard observed full calendar reference required')
    calendar_document=read(plan['calendar'],sources)
    calendar=[row['session'] for row in calendar_document['execution']['daily']]
    require(calendar==sorted(set(calendar)) and all(schedule._day(day)==day for day in calendar),'Canonical complete observed calendar required')
    positions={day:index for index,day in enumerate(calendar)}
    require(len(lane['decisions'])==6 and [row['execution_date'] for row in lane['decisions']]==list(DATES)
        and [row['cutoff'] for row in lane['decisions']]==list(CUTOFFS),'Exact six-decision denominator required')
    require(type(plan['selected_job_ids']) is list and len(plan['selected_job_ids'])==6,'Explicit six LEGACY_TARGET_DISTANCE branch jobs required')
    periods=[];identity={};fixed_risk=None
    for index,decision in enumerate(lane['decisions']):
        cutoff,execution=CUTOFFS[index],DATES[index]
        require(cutoff in positions and execution in positions and positions[execution]==positions[cutoff]+1,
            'Execution must be next observed session after Close cutoff')
        choices=decision['lanes']['LEGACY_TARGET_DISTANCE'];selected=[row for row in choices if row['job_id']==plan['selected_job_ids'][index]]
        require(len(selected)==1,'Explicit branch must be one of all preserved LEGACY_TARGET_DISTANCE ties')
        choice=selected[0]
        nodes=[node for node in lane['dependencies'] if node['node_id']=='LEGACY_TARGET_DISTANCE:'+execution+':'+choice['job_id']]
        require(len(nodes)==1 and nodes[0]['ancestry_reachable'] is True,'Unreachable LEGACY_TARGET_DISTANCE ancestry')
        queue=read(decision['queue_reference'],sources)
        require(queue['historical_cutoff']==cutoff and queue['coordinate']['selection_date']==execution,'Queue decision mismatch')
        context=read(queue['context'],sources);frontier=read(queue['frontier'],sources)
        _,changed,universe,binding=adapter.correct_context(context,frontier,cutoff)
        require(binding==queue['input_binding'],'Corrected six-input matrix binding differs')
        restored_selected,provenance=complete_candidate(choice,queue,frontier,universe,sources)
        require(choice['weight_spec']==SPECS[index],'Fixed weight specification differs from mode')
        for sid,item in choice['selected'].items():
            require(sid not in identity or identity[sid]==item['issuer_id'],'Permanent SID issuer changed')
            identity[sid]=item['issuer_id']
        parameters=deepcopy(queue['fit_parameters'])
        risk={key:parameters[key] for key in schedule._RISK_PARAMETERS}
        require(fixed_risk is None or fixed_risk==risk,'Fixed five-risk contract changed');fixed_risk=risk
        period=dict(decision_date=cutoff,execution_date=execution,cutoff=cutoff,
            returns=changed['returns'],selected=deepcopy(restored_selected),weight_spec=choice['weight_spec'],
            parameters=parameters,source_hashes=deepcopy(decision['source_hashes']),
            universe_by_sid={row['security_id']:deepcopy(row) for row in universe.values()},
            context_reference=deepcopy(queue['context']),corrected_input_binding=deepcopy(binding),candidate_provenance=provenance)
        periods.append(period)
    numerical_sources=adapter.fitter._sources()
    helper_sources={str(snapshot.SOURCE):snapshot.LOADED,str(schedule._SOURCE):schedule._LOADED_SHA,
        str(calendar_contract.SOURCE):calendar_contract.LOADED[str(calendar_contract.SOURCE)],**adapter.LOADED}
    for path,sha in helper_sources.items():
        require(path not in sources or sources[path]==sha,'Conflicting helper sources');sources[path]=sha
    for path,sha in numerical_sources.items():
        require(path not in sources or sources[path]==sha,'Conflicting numerical sources');sources[path]=sha
    verify(sources)
    return dict(plan=plan,plan_reference=deepcopy(plan_reference),lane=lane,calendar=calendar,periods=periods,
        sources=sources,numerical_sources=numerical_sources,
        runtime=adapter.typed.current_runtime())


def validate_fit(state,index,fitted,previous):
    from backtest import ndx_dynamic_refit_schedule_research as schedule
    period=state['periods'][index]
    require(period['weight_spec']==SPECS[index],'Fixed materialization weight specification differs')
    checks=schedule._validate_refit(fitted,period,previous,state['numerical_sources'])
    names=[period['selected'][sid]['ticker'] for sid in sorted(period['selected'])]
    frame=period['returns'].iloc[-period['parameters']['fit_days']:][names]
    payload=dict(dates=[day.date().isoformat() for day in frame.index],tickers=names,returns=frame.to_numpy().tolist())
    require(fitted['fit_data_sha256']==digest(payload),'Exact cutoff fit matrix SHA differs')
    require(all(fitted.get(key) is False for key in ('point_in_time_verified','source_authenticity_verified',
        'promotion_allowed','historical_task_evaluation_performed','order_generation_allowed')),'Research fit boundary changed')
    if MODES[index]=='DETERMINISTIC_EQUAL':
        require(all(type(target['target_weight']) is float and target['target_weight']==1./len(period['selected'])
            for target in fitted['targets'].values()),'Deterministic equal targets must be exact wrapper 1/k values')
        audit=fitted['projection_reconstruction_audit']
        require(type(audit['attempt_count']) is int and audit['attempt_count']==0 and audit['attempts']==[],
            'Equal branch cannot contain numerical projection recovery')
    return checks


def lane_binding(state,index,previous):
    period=state['periods'][index]
    required=set(period['selected'])|set(previous or {})
    universe=period['universe_by_sid']
    require(required<=set(universe),'Current cutoff universe lacks prior/selected risk-chain identity')
    chains={sid:universe[sid]['risk_chain'] for sid in sorted(required)}
    require(all(type(v) is str and v.strip()==v and v for v in chains.values()),'Canonical complete risk chains required')
    for sid,item in period['selected'].items():
        require(all(universe[sid][key]==item[key] for key in ('ticker','issuer_id','risk_chain')),'Selected and cutoff universe differ')
    for sid in previous or {}:
        prior=state['periods'][index-1]['selected'].get(sid)
        require(prior is not None and universe[sid]['issuer_id']==prior['issuer_id'] and universe[sid]['ticker']==prior['ticker'],
            'Previous full target identity differs from current cutoff universe')
    return dict(lane_previous_target_weights=deepcopy(previous),fit_actual_previous_target_weights=deepcopy(previous) if previous is not None else {},
        fit_uses_lane_previous_target=True,original_fit_reference=None,original_fit_audit_reference=None,
        imported_no_anchor_fit=False,lane_risk_chains_by_security=chains,
        risk_chain_context_reference=deepcopy(period['context_reference']),
        risk_chain_corrected_input_binding=deepcopy(period['corrected_input_binding']),
        candidate_provenance=deepcopy(period['candidate_provenance']))


def fit_once(state,index,previous):
    require(type(index) is int and 0<=index<6,'Explicit six-period wrapper coordinate required')
    from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
    period=state['periods'][index]
    require(period['weight_spec']==SPECS[index],'Wrapper specification differs from fixed mode')
    return fitter.refit_dynamic_cutoff_weights(returns=period['returns'],cutoff=period['cutoff'],
        selected=deepcopy(period['selected']),weight_spec=period['weight_spec'],
        previous_target_weights=deepcopy(previous),**period['parameters'])


def verify_runtime(state):
    from backtest import ndx_corrected_cutoff_snapshot_research as snapshot
    require(snapshot.adapter.typed.current_runtime()==state['runtime'],'Numerical runtime changed')


def attempt_envelope(state,index,previous,previous_reference,sources):
    period=state['periods'][index]
    return dict(schema='LEGACY_TARGET_DISTANCE_TARGET_SINGLE_ATTEMPT_V1',plan_reference=deepcopy(state['plan_reference']),
        execution_date=DATES[index],cutoff=period['cutoff'],job_id=state['plan']['selected_job_ids'][index],
        previous_target_reference=deepcopy(previous_reference),previous_target_weights=deepcopy(previous),
        selected=deepcopy(period['selected']),parameters=deepcopy(period['parameters']),weight_spec=period['weight_spec'],
        source_hashes=deepcopy(sources),runtime=deepcopy(state['runtime']),order_generation_allowed=False,**planned_counts(index),
        numerical_and_lane_binding=lane_binding(state,index,previous))


def validate_raw_envelope(state,index,raw,previous,previous_reference,started):
    expected=dict(schema='LEGACY_TARGET_DISTANCE_TARGET_RAW_RESULT_V1',plan_reference=deepcopy(state['plan_reference']),
        execution_date=DATES[index],previous_target_reference=deepcopy(previous_reference),previous_target_weights=deepcopy(previous),
        started_reference=deepcopy(started),**mode_counts(index),numerical_and_lane_binding=lane_binding(state,index,previous))
    if raw.get('status')=='FIT_RETURNED':
        expected.update(status='FIT_RETURNED',fitted=raw['fitted'])
    else:
        require(raw.get('status')=='NUMERICAL_FAILURE_NOT_ECONOMIC_INFEASIBILITY' and raw.get('fitted') is None and
            type(raw.get('error_type')) is str and type(raw.get('error')) is str,'Invalid raw failure envelope')
        expected.update(status=raw['status'],fitted=None,error_type=raw['error_type'],error=raw['error'])
    require(digest(raw)==digest(expected),'Exact complete raw attempt envelope differs')


def run_step(*,plan_reference,output,execution_date,execute=False,recover_raw=False,completed_finalizations=None,runner_sources=None,
        recovery_raw_reference=None,recovery_started_reference=None):
    require(type(execute) is bool,'Explicit execution switch required')
    require(type(recover_raw) is bool and not (execute and recover_raw),'Recovery and numerical execution are mutually exclusive')
    require(Path(output).resolve()==OUTPUT.resolve(),'Fixed LEGACY_TARGET_DISTANCE namespace required; output copies cannot refit')
    require(Path(plan_reference['path']).resolve()==OUTPUT/'plan.json','Fixed LEGACY_TARGET_DISTANCE plan location required')
    state=prepare_plan(plan_reference)
    for path,sha in (runner_sources or {}).items():
        require(path not in state['sources'] or state['sources'][path]==sha,'Runner source conflict');state['sources'][path]=sha
    verify(state['sources'])
    verify_runtime(state)
    require(execution_date in DATES,'Explicit one-of-six execution date required')
    index=DATES.index(execution_date);folder=Path(output).resolve()
    completed_finalizations=[] if completed_finalizations is None else completed_finalizations
    require(type(completed_finalizations) is list and len(completed_finalizations)==index,
        'Exact externally SHA-bound prior finalization prefix required')
    state['completed_finalizations']=deepcopy(completed_finalizations)
    previous=None;previous_reference=None;verified_fits=[]
    for earlier in range(index):
        final_path=folder/DATES[earlier]/'finalization.json'
        require(final_path.parent.is_dir()
            and {path.name for path in final_path.parent.iterdir()}=={'started.json','raw.json','finalization.json'},
            'Previous target directory contains missing or orphan evidence')
        require(Path(completed_finalizations[earlier]['path']).resolve()==final_path,'Prior finalization path differs')
        earlier_sources=deepcopy(state['sources'])
        final=read(completed_finalizations[earlier],state['sources'])
        require(final['schema']=='LEGACY_TARGET_DISTANCE_TARGET_STEP_FINALIZATION_V1' and final['execution_date']==DATES[earlier]
            and final['plan_reference']==plan_reference and final['status']=='TARGET_FIVE_RISKS_PASSED'
            and all(final.get(key) is False for key in ('fallback_performed','whole_lot_execution_performed','promotion_allowed')),
            'Previous target unsuccessful or wrong plan; no fallback')
        require(all(key in final and digest(final[key])==digest(value) for key,value in mode_counts(earlier).items()),
            'Previous finalization mode or actual request counts differ')
        raw=read(final['raw_reference'],state['sources'])
        require(Path(final['raw_reference']['path']).resolve()==folder/DATES[earlier]/'raw.json','Prior raw target coordinate differs')
        require(raw['execution_date']==DATES[earlier] and raw['plan_reference']==plan_reference
            and raw['previous_target_reference']==previous_reference
            and raw['previous_target_weights']==previous,'Previous raw target chain differs')
        require(raw['status']=='FIT_RETURNED','Previous numerical failure cannot feed anchor')
        require(raw['numerical_and_lane_binding']==lane_binding(state,earlier,previous),'Previous numerical versus lane provenance differs')
        require(Path(raw['started_reference']['path']).resolve()==folder/DATES[earlier]/'started.json','Started coordinate differs')
        started_value=read(raw['started_reference'],state['sources'])
        validate_raw_envelope(state,earlier,raw,previous,previous_reference,raw['started_reference'])
        require(started_value==attempt_envelope(state,earlier,previous,previous_reference,earlier_sources),
            'Previous complete started/source/runtime/anchor envelope differs')
        checks=validate_fit(state,earlier,raw['fitted'],previous)
        require(all(checks.values()) and final['risk_checks']==checks and final['detail'] is None,
            'Previous target failed original five risks or finalization differs')
        previous={sid:target['target_weight'] for sid,target in raw['fitted']['targets'].items()}
        previous_reference=deepcopy(final['raw_reference'])
        verified_fits.append(deepcopy(raw['fitted']))
    destination=folder/execution_date
    started_path=destination/'started.json';raw_path=destination/'raw.json';final_path=destination/'finalization.json'
    if destination.exists():
        require(destination.is_dir(),'Target step path is not a directory')
        present={path.name for path in destination.iterdir()}
        require(present<={'started.json','raw.json','finalization.json'},'Orphan evidence blocks new attempts and recovery')
    require(not final_path.exists(),'Step already finalized; consume its saved target')
    if not execute and not recover_raw:
        return dict(schema='LEGACY_TARGET_DISTANCE_TARGET_STEP_PREFLIGHT_V1',execution_date=execution_date,
            **planned_counts(index),wrapper_would_be_called=True,previous_target_reference=previous_reference,
            unresolved_started=started_path.exists() and not raw_path.exists(),fit_performed=False,promotion_allowed=False)
    verify(state['sources'])
    period=state['periods'][index]
    attempt=attempt_envelope(state,index,previous,previous_reference,state['sources'])
    if recover_raw:
        require(started_path.exists() and raw_path.exists(),'Recovery requires saved started and raw files; never refit an unknown attempt')
        require(type(recovery_raw_reference) is dict and type(recovery_started_reference) is dict,
            'Externally bound raw and started references required for recovery')
        require(Path(recovery_raw_reference['path']).resolve()==raw_path
            and Path(recovery_started_reference['path']).resolve()==started_path,'Recovery coordinates differ')
        started=deepcopy(recovery_started_reference);raw_reference=deepcopy(recovery_raw_reference)
        require(read(started,{})==attempt,'Saved attempt differs from current exact plan, source or strategic anchor')
        raw=read(raw_reference,{})
        validate_raw_envelope(state,index,raw,previous,previous_reference,started)
        require(raw.get('schema')=='LEGACY_TARGET_DISTANCE_TARGET_RAW_RESULT_V1' and raw['plan_reference']==plan_reference
            and raw['execution_date']==execution_date and raw['previous_target_reference']==previous_reference
            and raw['previous_target_weights']==previous and raw['started_reference']==started,'Saved raw identity or anchor differs')
        require(raw['numerical_and_lane_binding']==lane_binding(state,index,previous),'Recovered numerical versus lane provenance differs')
        return finalize_step(state,index,previous,raw,raw_reference,final_path,verified_fits,recovered=True)
    require(not started_path.exists() and not raw_path.exists(),'Existing attempt: restore raw explicitly, never retry fitting')
    started=publish(started_path,attempt)
    verify_runtime(state)
    raw=dict(schema='LEGACY_TARGET_DISTANCE_TARGET_RAW_RESULT_V1',plan_reference=deepcopy(plan_reference),
        execution_date=execution_date,previous_target_reference=deepcopy(previous_reference),
        previous_target_weights=deepcopy(previous),started_reference=started,
        **mode_counts(index),
        numerical_and_lane_binding=lane_binding(state,index,previous))
    try:
        fitted=fit_once(state,index,previous)
    except (ValueError,ArithmeticError,RuntimeError) as error:
        raw.update(status='NUMERICAL_FAILURE_NOT_ECONOMIC_INFEASIBILITY',fitted=None,
            error_type=type(error).__name__,error=str(error))
    else:
        raw.update(status='FIT_RETURNED',fitted=fitted)
    raw_reference=publish(raw_path,raw)
    # Preserve the raw return before any validator can fail; a crash here is
    # recoverable by a read-only finalizer, never an implicit optimizer retry.
    verify(state['sources'])
    return finalize_step(state,index,previous,raw,raw_reference,final_path,verified_fits,recovered=False)


def finalize_step(state,index,previous,raw,raw_reference,final_path,verified_fits,*,recovered):
    plan_reference=state['plan_reference'];execution_date=DATES[index]
    verify(state['sources']);verify_runtime(state);read(raw_reference,{});read(raw['started_reference'],{})
    validate_raw_envelope(state,index,raw,previous,raw['previous_target_reference'],raw['started_reference'])
    require(raw['numerical_and_lane_binding']==lane_binding(state,index,previous),'Final numerical/lane binding differs')
    require({p.name for p in Path(final_path).parent.iterdir()}=={'started.json','raw.json'},'Unexpected current attempt evidence')
    if raw['status']=='FIT_RETURNED':
        try:
            checks=validate_fit(state,index,raw['fitted'],previous)
        except (ValueError,KeyError,TypeError,IndexError) as error:
            status='INVALID_FIT_RESULT_STOP';checks=None;detail=str(error)
        else:
            status='TARGET_FIVE_RISKS_PASSED' if all(checks.values()) else 'STRATEGY_FIVE_RISKS_FAILED_STOP'
            detail=None
    else:
        require(raw['status']=='NUMERICAL_FAILURE_NOT_ECONOMIC_INFEASIBILITY' and raw['fitted'] is None,
            'Unknown raw numerical status')
        status='NUMERICAL_FAILURE_STOP';checks=None;detail=raw['error']
    final=dict(schema='LEGACY_TARGET_DISTANCE_TARGET_STEP_FINALIZATION_V1',plan_reference=deepcopy(plan_reference),
        execution_date=execution_date,raw_reference=raw_reference,status=status,risk_checks=checks,detail=detail,
        fallback_performed=False,whole_lot_execution_performed=False,promotion_allowed=False,**mode_counts(index))
    final_reference=publish(final_path,final)
    verify(state['sources'])
    read(raw_reference,{})
    read(final_reference,{})
    read(raw['started_reference'],{});verify_runtime(state)
    require({p.name for p in Path(final_path).parent.iterdir()}=={'started.json','raw.json','finalization.json'},'Unexpected finalized attempt evidence')
    complete_reference=None
    if index==5 and status=='TARGET_FIVE_RISKS_PASSED':
        fits=verified_fits+[raw['fitted']]
        require(len(fits)==6,'Full six-target chain required')
        complete=dict(schema='LEGACY_TARGET_DISTANCE_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1',plan_reference=deepcopy(plan_reference),
            calendar=deepcopy(state['calendar']),schedule=[dict(decision_date=CUTOFFS[position],execution_date=DATES[position],
                targets=deepcopy(fitted['targets'])) for position,fitted in enumerate(fits)],
            risk_chains_by_decision={CUTOFFS[position]:lane_binding(state,position,
                None if position==0 else {sid:t['target_weight'] for sid,t in fits[position-1]['targets'].items()})['lane_risk_chains_by_security']
                for position in range(6)},
            completed_finalization_references=deepcopy(state['completed_finalizations'])+[final_reference],
            final_target_reference=raw_reference,all_six_targets_passed=True,target_anchor_uses_actual_holdings=False,
            whole_lot_execution_performed=False,member_point_in_time_verified=False,promotion_allowed=False)
        complete_reference=publish(Path(final_path).parent.parent/'schedule.json',complete)
        verify(state['sources']);read(complete_reference,{})
    return dict(final_reference=final_reference,status=status,**mode_counts(index),
        raw_recovered_without_refit=recovered,complete_six_period_schedule_published=complete_reference is not None,
        complete_schedule_reference=complete_reference,promotion_allowed=False)
