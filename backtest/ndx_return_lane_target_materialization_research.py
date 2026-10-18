"""One explicit RETURN-lane target at a time; durable raw-first, never trades."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
DATES=('2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01')
CUTOFFS=('2023-03-31','2023-04-28','2023-05-31','2023-06-30','2023-07-31','2023-08-31')
SCHEMA='RETURN_SIX_PERIOD_STRATEGIC_TARGET_PLAN_V1'
ROOT=SOURCE.parents[1]
HARD_LANE=dict(path=str(ROOT/'data/cache/research/cutoff_training_lanes_20260923_v2/prepare.json'),
    sha256='b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba')
HARD_FIRST=dict(path=str(ROOT/'data/cache/research/corrected_cutoff_snapshot_20260919_v1/20230403/2b8ea25b96db524424132d39adb618ae5950a1596bb25722d33112a9d5377a5f.json'),
    sha256='fd837f382f255b49ca80d1a26c10ac358afbfbe019cca3b0fabd969af5d52e48')
HARD_AUDIT=dict(path=str(ROOT/'data/cache/research/corrected_cutoff_snapshot_20260919_v1/20230403_completed150_independent_audit_v2.json'),
    sha256='105dba955ce529093a267c20b9b52dc0773de6bc327d9a4de7005c325b541e31')


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


def prepare_plan(plan_reference):
    """Restore only saved matrices; no optimizer or account engine invocation."""
    from backtest import ndx_corrected_cutoff_snapshot_research as snapshot
    from backtest import ndx_dynamic_refit_schedule_research as schedule
    from backtest import ndx_corrected_explicit_path_research as calendar_contract
    adapter=snapshot.adapter
    sources={str(SOURCE):LOADED_SHA}
    plan=read(plan_reference,sources)
    require(set(plan)=={'schema','lane_prepare','calendar','first_fit','first_fit_audit','selected_job_ids'}
        and plan['schema']==SCHEMA,'Exact RETURN six-period plan required')
    require(plan['lane_prepare']==HARD_LANE and plan['first_fit']==HARD_FIRST and plan['first_fit_audit']==HARD_AUDIT,
        'Hard reviewed lane, first-fit and audit references required')
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
    require(type(plan['selected_job_ids']) is list and len(plan['selected_job_ids'])==6,'Explicit six RETURN branch jobs required')
    periods=[];states=[];identity={};fixed_risk=None
    for index,decision in enumerate(lane['decisions']):
        cutoff,execution=CUTOFFS[index],DATES[index]
        require(cutoff in positions and execution in positions and positions[execution]==positions[cutoff]+1,
            'Execution must be next observed session after Close cutoff')
        choices=decision['lanes']['RETURN'];selected=[row for row in choices if row['job_id']==plan['selected_job_ids'][index]]
        require(len(selected)==1,'Explicit branch must be one of all preserved RETURN ties')
        choice=selected[0]
        nodes=[node for node in lane['dependencies'] if node['node_id']=='RETURN:'+execution+':'+choice['job_id']]
        require(len(nodes)==1 and nodes[0]['ancestry_reachable'] is True,'Unreachable RETURN ancestry')
        queue=read(decision['queue_reference'],sources)
        require(queue['historical_cutoff']==cutoff and queue['coordinate']['selection_date']==execution,'Queue decision mismatch')
        context=read(queue['context'],sources);frontier=read(queue['frontier'],sources)
        _,changed,_,binding=adapter.correct_context(context,frontier,cutoff)
        require(binding==queue['input_binding'],'Corrected six-input matrix binding differs')
        entries=[entry for entry in queue['candidates'] if entry['task']['job_id']==choice['job_id']]
        require(len(entries)==1,'Chosen RETURN job absent from bound cutoff queue')
        entry=entries[0]
        require(entry['selected']==choice['selected'] and entry['task']['weight_spec']==choice['weight_spec'],
            'Cutoff selected identity/spec differs from lane')
        for sid,item in choice['selected'].items():
            require(sid not in identity or identity[sid]==item['issuer_id'],'Permanent SID issuer changed')
            identity[sid]=item['issuer_id']
        parameters=deepcopy(queue['fit_parameters'])
        risk={key:parameters[key] for key in schedule._RISK_PARAMETERS}
        require(fixed_risk is None or fixed_risk==risk,'Fixed five-risk contract changed');fixed_risk=risk
        period=dict(decision_date=cutoff,execution_date=execution,cutoff=cutoff,
            returns=changed['returns'],selected=deepcopy(entry['selected']),weight_spec=choice['weight_spec'],
            parameters=parameters,source_hashes=deepcopy(decision['source_hashes']))
        periods.append(period)
        states.append(dict(queue=queue,queue_digest=adapter.digest(queue),rows={choice['job_id']:entry},changed=changed))
    wrapper=read(plan['first_fit'],sources);audit=read(plan['first_fit_audit'],sources)
    first_job=plan['selected_job_ids'][0]
    matches=[row for row in audit['details'] if row['job_id']==first_job]
    require(len(matches)==1 and matches[0]['result_reference']==plan['first_fit']
        and matches[0]['status']=='FITTED_FIVE_RISKS_PASSED','Same-job independently audited first fit required')
    require(wrapper.get('schema')=='CORRECTED_CUTOFF_SNAPSHOT_TASK_V1'
        and wrapper['job_id']==first_job and wrapper['queue']==lane['decisions'][0]['queue_reference'],
        'First fit wrapper identity/queue differs')
    snapshot.validate_result(states[0],wrapper['result'])
    require(wrapper['result']['status']=='FITTED_FIVE_RISKS_PASSED','First strategic target failed five risks')
    require(matches[0]['typed_decimal']['selected']==periods[0]['selected']
        and matches[0]['typed_decimal']['fit_data_sha256']==wrapper['result']['refit']['fit_data_sha256']
        and all(value is True for value in matches[0]['typed_decimal']['decimal_risks']['checks'].values()),
        'Independent first-fit identity/matrix/risk payload differs')
    numerical_sources=adapter.fitter._sources()
    helper_sources={str(snapshot.SOURCE):snapshot.LOADED,str(schedule._SOURCE):schedule._LOADED_SHA,
        str(calendar_contract.SOURCE):calendar_contract.LOADED[str(calendar_contract.SOURCE)],**adapter.LOADED}
    for path,sha in helper_sources.items():
        require(path not in sources or sources[path]==sha,'Conflicting helper sources');sources[path]=sha
    for path,sha in numerical_sources.items():
        require(path not in sources or sources[path]==sha,'Conflicting numerical sources');sources[path]=sha
    verify(sources)
    return dict(plan=plan,plan_reference=deepcopy(plan_reference),lane=lane,calendar=calendar,periods=periods,
        first_refit=deepcopy(wrapper['result']['refit']),sources=sources,numerical_sources=numerical_sources,
        runtime=adapter.typed.current_runtime())


def validate_fit(state,index,fitted,previous):
    from backtest import ndx_dynamic_refit_schedule_research as schedule
    period=state['periods'][index]
    checks=schedule._validate_refit(fitted,period,previous,state['numerical_sources'])
    names=[period['selected'][sid]['ticker'] for sid in sorted(period['selected'])]
    frame=period['returns'].iloc[-period['parameters']['fit_days']:][names]
    payload=dict(dates=[day.date().isoformat() for day in frame.index],tickers=names,returns=frame.to_numpy().tolist())
    require(fitted['fit_data_sha256']==digest(payload),'Exact cutoff fit matrix SHA differs')
    require(all(fitted.get(key) is False for key in ('point_in_time_verified','source_authenticity_verified',
        'promotion_allowed','historical_task_evaluation_performed','order_generation_allowed')),'Research fit boundary changed')
    return checks


def fit_once(state,index,previous):
    from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
    period=state['periods'][index]
    return fitter.refit_dynamic_cutoff_weights(returns=period['returns'],cutoff=period['cutoff'],
        selected=deepcopy(period['selected']),weight_spec=period['weight_spec'],
        previous_target_weights=deepcopy(previous),**period['parameters'])


def verify_runtime(state):
    from backtest import ndx_corrected_cutoff_snapshot_research as snapshot
    require(snapshot.adapter.typed.current_runtime()==state['runtime'],'Numerical runtime changed')


def attempt_envelope(state,index,previous,previous_reference,sources):
    period=state['periods'][index]
    return dict(schema='RETURN_TARGET_SINGLE_ATTEMPT_V1',plan_reference=deepcopy(state['plan_reference']),
        execution_date=DATES[index],cutoff=period['cutoff'],job_id=state['plan']['selected_job_ids'][index],
        previous_target_reference=deepcopy(previous_reference),previous_target_weights=deepcopy(previous),
        selected=deepcopy(period['selected']),parameters=deepcopy(period['parameters']),weight_spec=period['weight_spec'],
        source_hashes=deepcopy(sources),runtime=deepcopy(state['runtime']),new_fit_attempt=index>0,order_generation_allowed=False)


def run_step(*,plan_reference,output,execution_date,execute=False,recover_raw=False,completed_finalizations=None,runner_sources=None,
        recovery_raw_reference=None,recovery_started_reference=None):
    require(type(execute) is bool,'Explicit execution switch required')
    require(type(recover_raw) is bool and not (execute and recover_raw),'Recovery and numerical execution are mutually exclusive')
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
        require(final['schema']=='RETURN_TARGET_STEP_FINALIZATION_V1' and final['execution_date']==DATES[earlier]
            and final['plan_reference']==plan_reference and final['status']=='TARGET_FIVE_RISKS_PASSED'
            and all(final.get(key) is False for key in ('fallback_performed','whole_lot_execution_performed','promotion_allowed')),
            'Previous target unsuccessful or wrong plan; no fallback')
        raw=read(final['raw_reference'],state['sources'])
        require(Path(final['raw_reference']['path']).resolve()==folder/DATES[earlier]/'raw.json','Prior raw target coordinate differs')
        require(raw['execution_date']==DATES[earlier] and raw['plan_reference']==plan_reference
            and raw['previous_target_reference']==previous_reference
            and raw['previous_target_weights']==previous,'Previous raw target chain differs')
        require(raw['status']=='FIT_RETURNED','Previous numerical failure cannot feed anchor')
        require(raw['schema']=='RETURN_TARGET_RAW_RESULT_V1'
            and type(raw['new_fit_attempt_count']) is int and raw['new_fit_attempt_count']==(1 if earlier>0 else 0)
            and raw['first_fit_imported_without_refit'] is (earlier==0),'Previous raw execution semantics differ')
        require(Path(raw['started_reference']['path']).resolve()==folder/DATES[earlier]/'started.json','Started coordinate differs')
        started_value=read(raw['started_reference'],state['sources'])
        require(started_value==attempt_envelope(state,earlier,previous,previous_reference,earlier_sources),
            'Previous complete started/source/runtime/anchor envelope differs')
        require(earlier!=0 or digest(raw['fitted'])==digest(state['first_refit']),'Imported first target differs from hard raw')
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
        return dict(schema='RETURN_TARGET_STEP_PREFLIGHT_V1',execution_date=execution_date,
            imports_first_fit=index==0,new_fit_would_be_called=index>0,previous_target_reference=previous_reference,
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
        require(raw.get('schema')=='RETURN_TARGET_RAW_RESULT_V1' and raw['plan_reference']==plan_reference
            and raw['execution_date']==execution_date and raw['previous_target_reference']==previous_reference
            and raw['previous_target_weights']==previous and raw['started_reference']==started
            and type(raw['new_fit_attempt_count']) is int and raw['new_fit_attempt_count']==(1 if index>0 else 0)
            and raw['first_fit_imported_without_refit'] is (index==0),'Saved raw identity or anchor differs')
        require(index!=0 or digest(raw['fitted'])==digest(state['first_refit']),'Recovered first target differs from hard raw')
        return finalize_step(state,index,previous,raw,raw_reference,final_path,verified_fits,recovered=True)
    require(not started_path.exists() and not raw_path.exists(),'Existing attempt: restore raw explicitly, never retry fitting')
    started=publish(started_path,attempt)
    verify_runtime(state)
    raw=dict(schema='RETURN_TARGET_RAW_RESULT_V1',plan_reference=deepcopy(plan_reference),
        execution_date=execution_date,previous_target_reference=deepcopy(previous_reference),
        previous_target_weights=deepcopy(previous),started_reference=started,
        new_fit_attempt_count=1 if index>0 else 0,first_fit_imported_without_refit=index==0)
    try:
        fitted=deepcopy(state['first_refit']) if index==0 else fit_once(state,index,previous)
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
    final=dict(schema='RETURN_TARGET_STEP_FINALIZATION_V1',plan_reference=deepcopy(plan_reference),
        execution_date=execution_date,raw_reference=raw_reference,status=status,risk_checks=checks,detail=detail,
        fallback_performed=False,whole_lot_execution_performed=False,promotion_allowed=False)
    final_reference=publish(final_path,final)
    verify(state['sources'])
    read(raw_reference,{})
    read(final_reference,{})
    read(raw['started_reference'],{});verify_runtime(state)
    complete_reference=None
    if index==5 and status=='TARGET_FIVE_RISKS_PASSED':
        fits=verified_fits+[raw['fitted']]
        require(len(fits)==6,'Full six-target chain required')
        complete=dict(schema='RETURN_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1',plan_reference=deepcopy(plan_reference),
            calendar=deepcopy(state['calendar']),schedule=[dict(decision_date=CUTOFFS[position],execution_date=DATES[position],
                targets=deepcopy(fitted['targets'])) for position,fitted in enumerate(fits)],
            risk_chains_by_decision={CUTOFFS[position]:deepcopy(fitted['risk_chains_by_security']) for position,fitted in enumerate(fits)},
            completed_finalization_references=deepcopy(state['completed_finalizations'])+[final_reference],
            final_target_reference=raw_reference,all_six_targets_passed=True,target_anchor_uses_actual_holdings=False,
            whole_lot_execution_performed=False,member_point_in_time_verified=False,promotion_allowed=False)
        complete_reference=publish(Path(final_path).parent.parent/'schedule.json',complete)
        verify(state['sources']);read(complete_reference,{})
    return dict(final_reference=final_reference,status=status,new_fit_attempt_count=raw['new_fit_attempt_count'],
        raw_recovered_without_refit=recovered,complete_six_period_schedule_published=complete_reference is not None,
        complete_schedule_reference=complete_reference,promotion_allowed=False)
