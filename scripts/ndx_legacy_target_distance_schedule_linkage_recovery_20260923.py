"""Read-only six-target linkage; publish a missing schedule without fitting."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
FOLDER=ROOT/'data/cache/research/legacy_target_distance_targets_20260923_v1'
PLAN=dict(path=str(FOLDER/'plan.json'),sha256='bb37f768133e9c90e66bd7d0838a51f8a14b3bba0a662390bf9b4fe31484b0d9')
READER=ROOT/'scripts/ndx_legacy_target_distance_prefix_independent_readback_20260923.py'
READER_SHA='8c6e33375808a10f5556e15e04feca6d0238d09b2a96f6ca7854f5b56f290970'
DATES=('2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01')
CUTOFFS=('2023-03-31','2023-04-28','2023-05-31','2023-06-30','2023-07-31','2023-08-31')
MODES=('DETERMINISTIC_EQUAL','NEW_ANCHORED_FIT','NEW_UNANCHORED_FIT','NEW_ANCHORED_FIT','DETERMINISTIC_EQUAL','DETERMINISTIC_EQUAL')
SPECS=('equal_weight','constrained_fixed_shrinkage_turnover_anchor','constrained_fixed_shrinkage',
    'constrained_fixed_shrinkage_turnover_anchor','equal_weight','equal_weight')


def counts(index):
    equal=MODES[index]=='DETERMINISTIC_EQUAL'
    return dict(materialization_mode=MODES[index],wrapper_call_attempt_count=1,
        deterministic_generation_request_count=int(equal),numerical_fit_request_count=int(not equal),import_count=0,
        optimizer_called_by_equal_branch=False if equal else None)


def require(condition,message):
    if not condition:raise ValueError(message)


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON field');result[key]=value
    return result


def loads(raw):
    def invalid(value):raise ValueError('Nonfinite JSON number: '+value)
    return json.loads(raw,object_pairs_hook=unique,parse_constant=invalid)


def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def merge(sources,addition):
    for path,sha in addition.items():
        require(type(path) is str and str(Path(path).resolve())==path and type(sha) is str and len(sha)==64 and
            set(sha)<=set('0123456789abcdef'),'Canonical absolute source/SHA required')
        require(path not in sources or sources[path]==sha,'Source SHA conflict');sources[path]=sha


def read(reference,sources):
    require(type(reference) is dict and set(reference)=={'path','sha256'},'Exact external reference required')
    merge(sources,{reference['path']:reference['sha256']})
    raw=Path(reference['path']).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==reference['sha256'],'Reference changed')
    return loads(raw)


def verify(sources):
    for path,sha in sources.items():require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,'Source drift: '+path)


def evidence_directories():
    for day in DATES:
        directory=FOLDER/day
        require(directory.is_dir() and {p.name for p in directory.iterdir()}=={'started.json','raw.json','finalization.json'} and
            all(p.is_file() for p in directory.iterdir()),'Missing or orphan period evidence')


def reconstruct(audit_reference):
    """Consume a completed independently audited chain; do not rerun numeric audits."""
    sources=dict(LOADED);merge(sources,{str(READER):READER_SHA});verify(sources)
    require(Path(audit_reference['path']).resolve().parent==FOLDER,'Audit must be a direct fixed-namespace artifact')
    audit=read(audit_reference,sources);plan=read(PLAN,sources)
    require(audit['schema']=='LEGACY_TARGET_DISTANCE_COMPLETE_PREFIX_INDEPENDENT_READBACK_V1' and audit['status']=='PASSED' and
        audit['plan_reference']==PLAN and type(audit['completed_prefix_count']) is int and audit['completed_prefix_count']==6 and
        len(audit['details'])==len(audit['finalization_references'])==6,'Complete independently audited six-target prefix required')
    require(all(type(audit[key]) is int for key in ('wrapper_call_attempt_count','deterministic_generation_request_count','numerical_fit_request_count','import_count')) and
        audit['wrapper_call_attempt_count']==6 and audit['deterministic_generation_request_count']==3 and
        audit['numerical_fit_request_count']==3 and audit['import_count']==0 and
        all(audit[key] is False for key in ('optimizer_called','owner_validator_called','account_engine_called',
            'point_in_time_verified','promotion_allowed','next_step_execution_authorized')),'Independent readback scope differs')
    require(audit['source_hashes'].get(str(READER))==READER_SHA and audit['source_hashes'].get(PLAN['path'])==PLAN['sha256'],
        'Hard independent reader/plan source lock required')
    require(plan['schema']=='LEGACY_TARGET_DISTANCE_SIX_PERIOD_STRATEGIC_TARGET_PLAN_V1' and
        plan['materialization_modes']==list(MODES) and plan['weight_specs']==list(SPECS),'Hard six-mode plan differs')
    merge(sources,audit['source_hashes'])
    calendar=[row['session'] for row in read(plan['calendar'],sources)['execution']['daily']]
    require(calendar==sorted(set(calendar)),'Complete observed calendar differs')
    evidence_directories();rows=[];risk_chains={};previous=None;previous_raw=None
    for index,(detail,ref) in enumerate(zip(audit['details'],audit['finalization_references'],strict=True)):
        directory=FOLDER/DATES[index]
        require(ref['path']==str(directory/'finalization.json') and detail['finalization_reference']==ref and
            detail['execution_date']==DATES[index] and detail['cutoff']==CUTOFFS[index] and
            detail['job_id']==plan['selected_job_ids'][index],'Six-period audit coordinates differ')
        final=read(ref,sources)
        require(final['schema']=='LEGACY_TARGET_DISTANCE_TARGET_STEP_FINALIZATION_V1' and final['plan_reference']==PLAN and
            final['execution_date']==DATES[index] and final['status']=='TARGET_FIVE_RISKS_PASSED' and final['detail'] is None and
            all(final[key] is False for key in ('fallback_performed','whole_lot_execution_performed','promotion_allowed')),
            'Unsuccessful finalization cannot publish a schedule')
        require(final['raw_reference']==detail['raw_reference'] and detail['raw_reference']['path']==str(directory/'raw.json'),
            'Raw reference differs from independent audit')
        raw=read(detail['raw_reference'],sources)
        require(raw['started_reference']==detail['started_reference'] and detail['started_reference']['path']==str(directory/'started.json'),
            'Started reference differs from independent audit')
        started=read(detail['started_reference'],sources)
        require(raw['schema']=='LEGACY_TARGET_DISTANCE_TARGET_RAW_RESULT_V1' and raw['status']=='FIT_RETURNED' and raw['plan_reference']==PLAN and
            raw['execution_date']==DATES[index] and raw['fitted']['targets']==detail['targets'] and
            raw['previous_target_weights']==previous and raw['previous_target_reference']==previous_raw,
            'Saved raw target and independently audited chain differ')
        operation=counts(index)
        require(encoded(detail['operation_counts'])==encoded(operation) and
            all(encoded({key:doc[key] for key in operation})==encoded(operation) for doc in (raw,final)),
            'Actual wrapper/generation/numerical/import request counts differ')
        planned={key:value for key,value in operation.items() if key not in ('materialization_mode','optimizer_called_by_equal_branch')}
        require(encoded(started['planned_operation_counts'])==encoded(planned) and
            started['materialization_mode']==MODES[index] and
            started['optimizer_called_by_equal_branch'] is operation['optimizer_called_by_equal_branch'] and
            not any(key in started for key in planned),'Started planned versus actual count semantics differ')
        require(started['schema']=='LEGACY_TARGET_DISTANCE_TARGET_SINGLE_ATTEMPT_V1' and
            started['plan_reference']==PLAN and started['execution_date']==DATES[index] and started['cutoff']==CUTOFFS[index] and
            started['job_id']==detail['job_id'] and started['previous_target_reference']==previous_raw and
            started['previous_target_weights']==previous and started['weight_spec']==raw['fitted']['weight_spec']==SPECS[index],
            'Started provenance or mode specification differs')
        binding=detail['numerical_and_lane_binding']
        require(encoded(raw['numerical_and_lane_binding'])==encoded(started['numerical_and_lane_binding'])==encoded(binding) and
            binding['lane_previous_target_weights']==previous and binding['lane_risk_chains_by_security']==detail['lane_risk_chains_by_security'],
            'Independent risk/provenance binding differs')
        require(raw['fitted']['previous_target_weights']==binding['fit_actual_previous_target_weights'] and
            binding['fit_actual_previous_target_weights']==(previous or {}) and
            binding['fit_uses_lane_previous_target'] is True and binding['original_fit_reference'] is None and
            binding['original_fit_audit_reference'] is None and binding['imported_no_anchor_fit'] is False,
            'Original numerical prior and strategic prior were mixed')
        provenance=binding['candidate_provenance']
        require(provenance['origin']=='HARD_COMPLETE_TRAINING_RECORD' and provenance['old_queue_candidate_present'] is False and
            provenance['original_task']['job_id']==detail['job_id'],'Independent complete-candidate provenance differs')
        for refkey in ('complete_date_reference','independent_full_diff_reference'):
            ref=provenance[refkey]
            require(audit['source_hashes'].get(ref['path'])==ref['sha256'],'Full candidate evidence absent from independent source closure')
        selected=set(detail['targets']);chains=detail['lane_risk_chains_by_security']
        require(set(chains)==selected|set(previous or {}) and all(type(v) is str and v and v==v.strip() for v in chains.values()),
            'Complete selected and prior SID risk-chain union required')
        require(CUTOFFS[index] in calendar and DATES[index] in calendar and calendar.index(DATES[index])==calendar.index(CUTOFFS[index])+1,
            'Next observed execution clock differs')
        rows.append(dict(decision_date=CUTOFFS[index],execution_date=DATES[index],targets=detail['targets']))
        risk_chains[CUTOFFS[index]]=chains
        previous={sid:target['target_weight'] for sid,target in detail['targets'].items()};previous_raw=detail['raw_reference']
    value=dict(schema='LEGACY_TARGET_DISTANCE_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1',plan_reference=PLAN,calendar=calendar,schedule=rows,
        risk_chains_by_decision=risk_chains,completed_finalization_references=audit['finalization_references'],
        final_target_reference=previous_raw,all_six_targets_passed=True,target_anchor_uses_actual_holdings=False,
        whole_lot_execution_performed=False,member_point_in_time_verified=False,promotion_allowed=False)
    verify(sources);evidence_directories()
    return value,sources


def publish(path,value):
    raw=encoded(value)
    with path.open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
    require(path.read_bytes()==raw,'Publication readback changed')
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


def publish_or_compare(path,value):
    if path.exists():
        raw=path.read_bytes();require(encoded(loads(raw))==encoded(value),'Existing artifact differs; never overwrite')
        return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()),False
    return publish(path,value),True


def run(audit_path,audit_sha256):
    audit_reference=dict(path=str(Path(audit_path).resolve()),sha256=audit_sha256)
    schedule,sources=reconstruct(audit_reference)
    verify(sources);evidence_directories()
    schedule_ref,created=publish_or_compare(FOLDER/'schedule.json',schedule)
    merge(sources,{schedule_ref['path']:schedule_ref['sha256']});verify(sources);evidence_directories()
    linkage=dict(schema='LEGACY_TARGET_DISTANCE_SIX_PERIOD_SCHEDULE_INDEPENDENT_LINKAGE_V1',schedule_reference=schedule_ref,
        independent_target_audit_reference=audit_reference,plan_reference=PLAN,exact_schedule_reconstruction=True,
        decision_count=6,source_hashes=sources,fitter_called=False,account_engine_called=False,
        observed_wrapper_call_attempt_count=6,observed_deterministic_generation_request_count=3,
        observed_numerical_fit_request_count=3,observed_import_count=0,
        target_numerical_audit_repeated=False,original_producer_schedule_creation_claimed=False,
        schedule_content_reconstruction_only=True,point_in_time_verified=False,promotion_allowed=False)
    linked,_=publish_or_compare(FOLDER/'schedule_independent_linkage.json',linkage)
    verify(sources);read(linked,{});evidence_directories()
    return dict(schedule_reference=schedule_ref,linkage_reference=linked,schedule_created=created,
        fitter_called=False,account_engine_called=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--audit-path',required=True)
    parser.add_argument('--audit-sha256',required=True)
    print(json.dumps(run(**vars(parser.parse_args()))))
