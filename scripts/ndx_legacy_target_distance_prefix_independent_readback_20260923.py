"""Independent standard-library readback of an externally pinned LEGACY_TARGET_DISTANCE prefix."""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_return_lane_first_two_independent_readback_20260923 as arithmetic

SOURCE=Path(__file__).resolve()
FOLDER=ROOT/'data/cache/research/legacy_target_distance_targets_20260923_v1'
DATES=('2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01')
CUTOFFS=('2023-03-31','2023-04-28','2023-05-31','2023-06-30','2023-07-31','2023-08-31')
PLAN=dict(path=str(FOLDER/'plan.json'),sha256='bb37f768133e9c90e66bd7d0838a51f8a14b3bba0a662390bf9b4fe31484b0d9')
MODES=('DETERMINISTIC_EQUAL','NEW_ANCHORED_FIT','NEW_UNANCHORED_FIT','NEW_ANCHORED_FIT','DETERMINISTIC_EQUAL','DETERMINISTIC_EQUAL')
SPECS=('equal_weight','constrained_fixed_shrinkage_turnover_anchor','constrained_fixed_shrinkage',
    'constrained_fixed_shrinkage_turnover_anchor','equal_weight','equal_weight')
NUMERICAL_REFERENCE=dict(path=str(ROOT/'data/cache/research/corrected_cutoff_snapshot_20260919_v1/20230403/cd47b2fa9d5047a86fab01d011f0b779546a98a88366aeb32bc0b975ef38439c.json'),
    sha256='2e5bdb8d0e20e1e238c92694f9e09b16a3cd14b139a85f2acddeb599af5581f0')
LANE_SHA='b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba'
FROZEN_SOURCES={
    str(ROOT/'backtest/ndx_legacy_target_distance_materialization_research.py'):'92ee160e0599452e5ff9ca8bf5faa7b3408b807ed9dbcf8995ee244f1b72aa0d',
    str(ROOT/'scripts/ndx_legacy_target_distance_materialization_20260923.py'):'ade664ddc7257a540e9f351054c06823007226bf3b47b19ad07ae6a72d226bcc',
}
LOADED_SOURCES={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    str(Path(arithmetic.__file__).resolve()):'58253dc1e8d7e1db260e1fb482f1a1df08c6619130eec6d6d670cd30d35f6020'}
require=arithmetic.require
digest=arithmetic.digest


def verify_sources(sources):
    for path,sha in sources.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,'Source drift: '+path)


def merge_sources(destination,incoming):
    for path,sha in incoming.items():
        require(type(path) is str and Path(path).is_absolute() and type(sha) is str and len(sha)==64
            and set(sha)<=set('0123456789abcdef'),'Canonical absolute source and SHA required')
        require(path not in destination or destination[path]==sha,'Conflicting source SHA: '+path)
        destination[path]=sha


def prefix_references(references):
    require(type(references) is list and 1<=len(references)<=6,'Explicit complete prefix of one through six finalizations required')
    for index,reference in enumerate(references):
        require(type(reference) is dict and set(reference)=={'path','sha256'},'Exact external finalization reference required')
        require(Path(reference['path']).resolve()==FOLDER/DATES[index]/'finalization.json','Skipped, repeated or foreign finalization coordinate')
        require(type(reference['sha256']) is str and len(reference['sha256'])==64
            and set(reference['sha256'])<=set('0123456789abcdef'),'External finalization SHA required')
    return deepcopy(references)


def check_directory(directory):
    require(directory.is_dir() and {path.name for path in directory.iterdir()}=={'started.json','raw.json','finalization.json'}
        and all(path.is_file() for path in directory.iterdir()),'Missing or extra evidence in target directory')


def matrix_check(context,selected,parameters,cutoff,fitted):
    calendars=[]
    for key in ('returns','nominal_prices','target_returns'):
        mapping=context['prepared_inputs'][key]['payload']['mapping']
        calendar=[]
        for row in mapping['index']['items']:
            require(type(row) is dict and set(row)=={'timestamp'} and type(row['timestamp']) is str
                and row['timestamp'].endswith('T00:00:00'),'Canonical typed midnight required')
            day=row['timestamp'][:10]
            require(date.fromisoformat(day).isoformat()==day and row['timestamp']==day+'T00:00:00','Canonical training date required')
            calendar.append(day)
        require(calendar and calendar==sorted(set(calendar)) and calendar[-1]==cutoff,'Training calendar differs from cutoff')
        calendars.append(calendar)
    require(calendars[0]==calendars[1]==calendars[2],'Three training calendars differ')
    calendar=calendars[0];fit_days=parameters['fit_days']
    require(type(fit_days) is int and fit_days==126 and len(calendar)>=fit_days,'Exact 126-row training contract required')
    fit_dates=calendar[-fit_days:]
    require(fit_dates[0]>'2022-07-18','Known corrected cells overlap fit; explicit new reader required')
    mapping=context['prepared_inputs']['returns']['payload']['mapping']
    columns=mapping['columns']['items'];values=mapping['column_values']['items']
    require(len(columns)==len(set(columns))==len(values),'Duplicate or malformed matrix columns')
    names=[selected[sid]['ticker'] for sid in sorted(selected)];series=[]
    require(len(names)==len(set(names)),'Duplicate selected ticker')
    for name in names:
        require(name in columns,'Selected ticker missing from matrix')
        entire=values[columns.index(name)]['items']
        require(len(entire)==len(calendar),'Matrix column length differs')
        portion=entire[-fit_days:]
        require(all(type(value) is dict and set(value)=={'float_hex'} for value in portion),'Typed finite floats required')
        decoded=[float.fromhex(value['float_hex']) for value in portion]
        for value in decoded:arithmetic.number(value)
        series.append(decoded)
    payload=dict(dates=fit_dates,tickers=names,returns=[list(row) for row in zip(*series)])
    require(fitted['fit_data_sha256']==digest(payload) and fitted['fit_start']==fit_dates[0]
        and fitted['fit_end']==fitted['cutoff']==cutoff and type(fitted['fit_row_count']) is int
        and fitted['fit_row_count']==fit_days,'Exact cutoff fit matrix/date binding differs')
    return dict(fit_start=fit_dates[0],fit_end=cutoff,fit_row_count=fit_days,fit_data_sha256=digest(payload))


def universe_rows(context):
    mapping=context['prepared_inputs']['universe']['payload']['mapping']
    columns=mapping['columns']['items'];values=mapping['column_values']['items']
    require(len(columns)==len(set(columns))==len(values),'Malformed universe columns')
    required=('ticker','security_id','issuer_id','risk_chain')
    require(set(required)<=set(columns),'Missing universe identity fields')
    rows=[values[columns.index(key)]['items'] for key in required]
    require(len({len(row) for row in rows})==1,'Universe dimensions differ')
    result={}
    for values in zip(*rows):
        require(all(type(v) is str and v and v.strip()==v for v in values),'Canonical universe identities required')
        row=dict(zip(required,values));sid=row['security_id']
        require(sid not in result,'Duplicate universe SID');result[sid]=row
    return result


def lane_binding(*,index,previous,previous_selected,selected,universe,context_reference,input_binding,candidate_provenance):
    required=set(selected)|set(previous or {})
    require(required<=set(universe),'Missing selected or exited SID in current universe')
    for sid,row in selected.items():
        require(all(universe[sid][key]==row[key] for key in ('ticker','issuer_id','risk_chain')),'Selected universe identity differs')
    for sid in previous or {}:
        require(sid in previous_selected and all(universe[sid][key]==previous_selected[sid][key]
            for key in ('ticker','issuer_id')),'Exited/current previous identity differs')
    return dict(lane_previous_target_weights=deepcopy(previous),fit_actual_previous_target_weights=deepcopy(previous or {}),
        fit_uses_lane_previous_target=True,original_fit_reference=None,
        original_fit_audit_reference=None,imported_no_anchor_fit=False,
        lane_risk_chains_by_security={sid:universe[sid]['risk_chain'] for sid in sorted(required)},
        risk_chain_context_reference=context_reference,risk_chain_corrected_input_binding=input_binding,
        candidate_provenance=deepcopy(candidate_provenance))


def mode_counts(index):
    equal=MODES[index]=='DETERMINISTIC_EQUAL'
    return dict(materialization_mode=MODES[index],wrapper_call_attempt_count=1,
        deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0,
        optimizer_called_by_equal_branch=False if equal else None)


def validate_step(*,index,started,raw,final,selected,parameters,weight_spec,previous,previous_reference,binding):
    execution,cutoff=DATES[index],CUTOFFS[index]
    require(set(started)=={'schema','plan_reference','execution_date','cutoff','job_id','previous_target_reference',
        'previous_target_weights','selected','parameters','weight_spec','source_hashes','runtime','planned_operation_counts',
        'materialization_mode','optimizer_called_by_equal_branch',
        'order_generation_allowed','numerical_and_lane_binding'},'Exact started fields required')
    require(set(raw)=={'schema','plan_reference','execution_date','previous_target_reference','previous_target_weights',
        'started_reference','numerical_and_lane_binding','status','fitted'}|set(mode_counts(index)),
        'Exact successful raw fields required')
    require(set(final)=={'schema','plan_reference','execution_date','raw_reference','status','risk_checks','detail',
        'fallback_performed','whole_lot_execution_performed','promotion_allowed'}|set(mode_counts(index)),'Exact finalization fields required')
    require(final['schema']=='LEGACY_TARGET_DISTANCE_TARGET_STEP_FINALIZATION_V1' and raw['schema']=='LEGACY_TARGET_DISTANCE_TARGET_RAW_RESULT_V1'
        and started['schema']=='LEGACY_TARGET_DISTANCE_TARGET_SINGLE_ATTEMPT_V1','Unexpected step schema')
    require(all(value['plan_reference']==PLAN for value in (final,raw,started)),'Foreign plan binding')
    require(all(value['execution_date']==execution for value in (final,raw,started)) and started['cutoff']==cutoff,'Decision coordinate differs')
    require(final['status']=='TARGET_FIVE_RISKS_PASSED' and final['detail'] is None and raw['status']=='FIT_RETURNED','Unsuccessful prefix step')
    require(all(final[key] is False for key in ('fallback_performed','whole_lot_execution_performed','promotion_allowed'))
        and started['order_generation_allowed'] is False,'Authority escalation')
    counts=mode_counts(index)
    planned={key:value for key,value in counts.items() if key not in ('materialization_mode','optimizer_called_by_equal_branch')}
    require(digest(started['planned_operation_counts'])==digest(planned)
        and started['materialization_mode']==counts['materialization_mode']
        and started['optimizer_called_by_equal_branch'] is counts['optimizer_called_by_equal_branch'],
        'Planned operation counts differ')
    for document in (raw,final):
        require(digest({key:document[key] for key in counts})==digest(counts),'Actual request count or equal branch differs')
    require(weight_spec==SPECS[index],'Mode and weight specification differ')
    require(digest(raw['numerical_and_lane_binding'])==digest(binding)==digest(started['numerical_and_lane_binding']),
        'Numerical provenance and strategic lane chain differ')
    require(raw['previous_target_reference']==started['previous_target_reference']==previous_reference
        and raw['previous_target_weights']==started['previous_target_weights']==previous,'Full previous strategic target reference/map differs')
    fitted=raw['fitted']
    require(started['selected']==selected and started['parameters']==parameters,'Started identity/parameter contract differs')
    require(started['weight_spec']==fitted['weight_spec']==weight_spec
        and weight_spec in ('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor'),'Weight specification differs')
    require(fitted['declared_parameters']=={key:value for key,value in parameters.items() if key!='fit_days'},'Declared fit/risk contract differs')
    require(set(fitted['targets'])==set(selected) and len({row['issuer_id'] for row in selected.values()})==len(selected),'Target SID/issuer denominator differs')
    for sid,target in fitted['targets'].items():
        require(set(target)=={'ticker','issuer_id','target_weight'}
            and all(target[key]==selected[sid][key] for key in ('ticker','issuer_id')),'Target identity differs')
    numerical_previous=previous or {}
    require(fitted['previous_target_weights']==numerical_previous and fitted['checkpoint_weights_used'] is False,
        'Fitted anchor dropped or changed previous strategic SID weights')
    for value in (previous or {}).values():arithmetic.number(value)
    mass=sum(numerical_previous.get(sid,0.) for sid in sorted(selected))
    anchor={sid:numerical_previous.get(sid,0.)/mass if mass>0 else 0. for sid in selected}
    strength=parameters['turnover_anchor_strength'] if mass>0 and weight_spec=='constrained_fixed_shrinkage_turnover_anchor' else 0.
    require(type(fitted['anchor_by_security']) is dict and set(fitted['anchor_by_security'])==set(anchor),
        'Exact anchor SID denominator required')
    for value in fitted['anchor_by_security'].values():arithmetic.number(value)
    require(type(fitted['surviving_anchor_mass']) in (int,float) and fitted['surviving_anchor_mass']==mass
        and fitted['anchor_by_security']==anchor and type(fitted['effective_anchor_strength']) in (int,float)
        and fitted['effective_anchor_strength']==strength,'Survivor normalization or weight-spec anchor strength differs')
    require(fitted['risk_chains_by_security']=={sid:row['risk_chain'] for sid,row in selected.items()},'Target risk identities differ')
    if weight_spec=='equal_weight':
        require(all(type(target['target_weight']) is float and target['target_weight']==1./len(selected)
            for target in fitted['targets'].values()),'Equal targets are not the exact frozen 1/k construction')
        recovery=fitted['projection_reconstruction_audit']
        require(type(recovery['attempt_count']) is int and recovery['attempt_count']==0 and recovery['attempts']==[],
            'Equal branch cannot claim numerical projection recovery')
    risks=arithmetic.decimal_risks(fitted,parameters,selected)
    require(all(risks['checks'].values()) and risks['checks']==fitted['declared_constraint_checks']==final['risk_checks']
        and all(type(value) is bool for value in fitted['declared_constraint_checks'].values())
        and all(type(value) is bool for value in final['risk_checks'].values())
        and fitted['declared_constraints_passed'] is True,'Independent Decimal five risks differ')
    require(all(fitted[key] is False for key in ('point_in_time_verified','source_authenticity_verified','promotion_allowed',
        'historical_task_evaluation_performed','order_generation_allowed')),'Fitted research authority differs')
    return dict(decimal_risks=risks,previous_target_sid_count=len(previous or {}),
        exited_previous_sids=sorted(set(previous or {})-set(selected)),
        new_selected_sids=sorted(set(selected)-set(previous or {})) if previous else [],
        effective_anchor_strength=strength,complete_previous_strategic_target_exact=True,
        imported_original_fit=False,lane_risk_chains_by_security=binding['lane_risk_chains_by_security'])


def check_numerical_sources(fitted,expected):
    require(type(expected) is dict and expected and fitted.get('source_hashes')==expected,
        'Exact hard frozen numerical source closure required')


def recover_full_candidate(choice,queue,frontier,complete,independent,universe):
    require(frontier['schema']=='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1'
        and frontier['coordinate']==complete['coordinate']==queue['coordinate']
        and frontier['original_decision_data_end']==queue['historical_cutoff'], 'Full cohort coordinates differ')
    records=complete['records'];diagnostics=frontier['candidate_diagnostics']
    by_job={row['task']['job_id']:row for row in records}
    by_diagnostic={row['job_id']:row for row in diagnostics}
    count=frontier['original_count']
    require(type(count) is int and len(records)==len(diagnostics)==len(by_job)==len(by_diagnostic)==count
        and count==complete['original_count']==queue['full_original_count'] and set(by_job)==set(by_diagnostic)
        and complete['economic_inputs_complete'] is True and type(complete['pending_count']) is int
        and complete['pending_count']==0, 'Full cohort task denominator differs')
    require(independent['schema']=='SELECTED_ARCHIVE_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1'
        and independent['date']==queue['coordinate']['selection_date'] and independent['original_count']==count
        and dict(path=str(Path(independent['output_path']).resolve()),sha256=independent['output_sha256'])
            ==frontier['complete_date_artifact']
        and all(independent[key] is True for key in ('whole_date_task_map_verified','ordered_full_record_diff_verified',
            'full_new_results_match_external_checkpoints','output_source_partitions_reverified')), 'Full diff does not bind complete cohort')
    job=choice['job_id'];require(job in by_job,'Hard lane job absent from full records')
    record=by_job[job];task=record['task'];result=record['result'];diagnostic=by_diagnostic[job]
    require(record['status']=='AVAILABLE' and task['decision_data_end']==queue['historical_cutoff']
        and {key:task[key] for key in ('selection_date','source_batch','universe_track')}==queue['coordinate'],
        'Original task scope or cutoff differs')
    for key in ('tickers','holding_count','weight_spec'):
        require(digest(task[key])==digest(result[key])==digest(choice[key])==digest(diagnostic[key]),
            'Candidate identity/spec/cardinality differs')
    require(diagnostic['fractional_risk_liquidity_passed'] is True
        and all(result[key]==value for key,value in choice['metrics'].items()), 'Original eligibility/ranking evidence differs')
    names=task['tickers'].split(';');require(len(names)==len(set(names))==task['holding_count'],'Duplicate target ticker')
    matching={sid:{key:row[key] for key in ('ticker','issuer_id','risk_chain')}
        for sid,row in universe.items() if row['ticker'] in names}
    require(matching==choice['selected'] and len(matching)==len(names),'Typed selected identity differs')
    old_present=any(row['task']['job_id']==job for row in queue['candidates'])
    require(not old_present,'Unexpected old subqueue membership for hard LEGACY jobs')
    provenance=dict(origin='HARD_COMPLETE_TRAINING_RECORD',complete_date_reference=frontier['complete_date_artifact'],
        independent_full_diff_reference=frontier['independent_full_diff_artifact'],original_task=task,
        old_queue_candidate_present=False)
    return matching,provenance


def audit_prefix(finalization_references):
    references=prefix_references(finalization_references)
    verify_sources(LOADED_SOURCES);verify_sources(FROZEN_SOURCES)
    sources=dict(LOADED_SOURCES);merge_sources(sources,FROZEN_SOURCES);documents={}
    def read(reference):
        require(type(reference) is dict and set(reference)=={'path','sha256'},'Exact artifact reference required')
        path=str(Path(reference['path']).resolve());sha=reference['sha256']
        merge_sources(sources,{path:sha})
        if path not in documents:
            raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==sha,'Artifact SHA differs: '+path)
            documents[path]=json.loads(raw)
        return documents[path]
    plan=read(PLAN)
    require(plan['schema']=='LEGACY_TARGET_DISTANCE_SIX_PERIOD_STRATEGIC_TARGET_PLAN_V1' and plan['lane_prepare']['sha256']==LANE_SHA,'Hard plan/lane differs')
    require(plan['materialization_modes']==list(MODES) and plan['weight_specs']==list(SPECS),'Hard mode/spec sequence differs')
    lane=read(plan['lane_prepare']);numerical_source_witness=read(NUMERICAL_REFERENCE)
    calendar=[row['session'] for row in read(plan['calendar'])['execution']['daily']]
    require(calendar==sorted(set(calendar)),'Observed execution calendar differs')
    require(len(lane['decisions'])==6 and [row['execution_date'] for row in lane['decisions']]==list(DATES)
        and [row['cutoff'] for row in lane['decisions']]==list(CUTOFFS),'Hard six-date denominator differs')
    previous=None;previous_reference=None;previous_selected={};details=[];issuer_by_sid={}
    for index,reference in enumerate(references):
        execution,cutoff=DATES[index],CUTOFFS[index];directory=FOLDER/execution
        check_directory(directory)
        final=read(reference);raw=read(final['raw_reference']);started=read(raw['started_reference'])
        require(Path(final['raw_reference']['path']).resolve()==directory/'raw.json'
            and Path(raw['started_reference']['path']).resolve()==directory/'started.json','Raw/started artifact coordinate differs')
        require(cutoff in calendar and execution in calendar and calendar.index(execution)==calendar.index(cutoff)+1,
            'Execution is not next observed session')
        decision=lane['decisions'][index];queue=read(decision['queue_reference']);context=read(queue['context'])
        job=plan['selected_job_ids'][index]
        choices=[row for row in decision['lanes']['LEGACY_TARGET_DISTANCE'] if row['job_id']==job]
        require(len(choices)==1 and started['job_id']==job,'Exact LEGACY_TARGET_DISTANCE chosen job differs')
        frontier=read(queue['frontier']);complete=read(frontier['complete_date_artifact'])
        full_diff=read(frontier['independent_full_diff_artifact']);universe=universe_rows(context)
        selected,provenance=recover_full_candidate(choices[0],queue,frontier,complete,full_diff,universe)
        parameters=queue['fit_parameters'];fitted=raw['fitted']
        check_numerical_sources(fitted,numerical_source_witness['result']['refit']['source_hashes'])
        require(queue['historical_cutoff']==cutoff and queue['coordinate']['selection_date']==execution
            and selected==choices[0]['selected'],'Queue/selection identities differ')
        require(started['runtime']==queue['original_runtime']==context['runtime'],'Original runtime binding differs')
        for sid,row in selected.items():
            require(sid not in issuer_by_sid or issuer_by_sid[sid]==row['issuer_id'],'Permanent SID issuer changed')
            issuer_by_sid[sid]=row['issuer_id']
        binding=lane_binding(index=index,previous=previous,previous_selected=previous_selected,selected=selected,
            universe=universe,context_reference=queue['context'],input_binding=queue['input_binding'],candidate_provenance=provenance)
        observed=validate_step(index=index,started=started,raw=raw,final=final,selected=selected,parameters=parameters,
            weight_spec=choices[0]['weight_spec'],previous=previous,previous_reference=previous_reference,binding=binding)
        matrix=matrix_check(context,selected,parameters,cutoff,fitted)
        for path,sha in FROZEN_SOURCES.items():
            require(started['source_hashes'].get(path)==sha,'Original core/CLI source lock absent or different')
        require(started['source_hashes'].get(PLAN['path'])==PLAN['sha256'],'Hard plan source lock missing')
        merge_sources(sources,started['source_hashes']);merge_sources(sources,fitted['source_hashes'])
        details.append(dict(execution_date=execution,cutoff=cutoff,job_id=job,finalization_reference=reference,
            raw_reference=final['raw_reference'],started_reference=raw['started_reference'],targets=fitted['targets'],
            operation_counts=mode_counts(index),numerical_and_lane_binding=binding,**observed,**matrix))
        previous={sid:row['target_weight'] for sid,row in fitted['targets'].items()};previous_reference=final['raw_reference']
        previous_selected=deepcopy(selected)
    verify_sources(sources)
    return dict(schema='LEGACY_TARGET_DISTANCE_COMPLETE_PREFIX_INDEPENDENT_READBACK_V1',status='PASSED',plan_reference=PLAN,
        completed_prefix_count=len(references),finalization_references=references,details=details,source_hashes=sources,
        wrapper_call_attempt_count=len(references),import_count=0,
        deterministic_generation_request_count=sum(mode=='DETERMINISTIC_EQUAL' for mode in MODES[:len(references)]),
        numerical_fit_request_count=sum(mode!='DETERMINISTIC_EQUAL' for mode in MODES[:len(references)]),
        any_actual_exiting_sid_case=any(row['exited_previous_sids'] for row in details),
        observed_calendar_exchange_certified=False,optimizer_called=False,owner_validator_called=False,account_engine_called=False,
        next_step_technically_ready=len(references)<6,next_step_execution_authorized=False,
        point_in_time_verified=False,promotion_allowed=False)


def run(*,finalization_paths,finalization_sha256,output):
    require(type(finalization_paths) is list and type(finalization_sha256) is list
        and len(finalization_paths)==len(finalization_sha256),'Matching externally declared prefix paths and SHAs required')
    destination=Path(output).resolve();require(not destination.exists(),'Create-only readback output')
    require(not any(destination.is_relative_to(FOLDER/day) for day in DATES),'Readback cannot pollute target evidence directories')
    references=[dict(path=str(Path(path).resolve()),sha256=sha) for path,sha in zip(finalization_paths,finalization_sha256)]
    report=audit_prefix(references);verify_sources(report['source_hashes'])
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as handle:
        handle.write(raw);handle.flush();os.fsync(handle.fileno())
    verify_sources(report['source_hashes']);require(destination.read_bytes()==raw,'Published readback bytes differ')
    return dict(path=str(destination),sha256=hashlib.sha256(raw).hexdigest(),status=report['status'],
        completed_prefix_count=report['completed_prefix_count'],optimizer_called=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finalization-path',dest='finalization_paths',required=True,action='append')
    parser.add_argument('--finalization-sha256',required=True,action='append')
    parser.add_argument('--output',required=True)
    print(json.dumps(run(**vars(parser.parse_args()))))
