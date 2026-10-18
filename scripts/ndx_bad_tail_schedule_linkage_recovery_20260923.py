"""Read-only six-target linkage; publish a missing schedule without fitting."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
FOLDER=ROOT/'data/cache/research/bad_tail_lane_targets_20260923_v1'
PLAN=dict(path=str(FOLDER/'plan.json'),sha256='c31be419263ec985518be5d74435a671698a4a116bf8b8842963ca1db8328795')
READER=ROOT/'scripts/ndx_bad_tail_lane_prefix_independent_readback_20260923.py'
READER_SHA='e6a27a7cf485c7e6c4681346efe6dd3c85552b9fd7de17739b1eeaf3acbcd2d6'
DATES=('2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01')
CUTOFFS=('2023-03-31','2023-04-28','2023-05-31','2023-06-30','2023-07-31','2023-08-31')


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
    require(audit['schema']=='BAD_TAIL_COMPLETE_PREFIX_INDEPENDENT_READBACK_V1' and audit['status']=='PASSED' and
        audit['plan_reference']==PLAN and type(audit['completed_prefix_count']) is int and audit['completed_prefix_count']==6 and
        len(audit['details'])==len(audit['finalization_references'])==6,'Complete independently audited six-target prefix required')
    require(all(type(audit[key]) is int for key in ('first_import_count','last_no_anchor_import_count','new_fit_observed_count')) and
        audit['first_import_count']==1 and audit['last_no_anchor_import_count']==1 and audit['new_fit_observed_count']==4 and
        all(audit[key] is False for key in ('optimizer_called','owner_validator_called','account_engine_called',
            'point_in_time_verified','promotion_allowed','next_step_execution_authorized')),'Independent readback scope differs')
    require(audit['source_hashes'].get(str(READER))==READER_SHA and audit['source_hashes'].get(PLAN['path'])==PLAN['sha256'],
        'Hard independent reader/plan source lock required')
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
        require(final['schema']=='BAD_TAIL_TARGET_STEP_FINALIZATION_V1' and final['plan_reference']==PLAN and
            final['execution_date']==DATES[index] and final['status']=='TARGET_FIVE_RISKS_PASSED' and final['detail'] is None and
            all(final[key] is False for key in ('fallback_performed','whole_lot_execution_performed','promotion_allowed')),
            'Unsuccessful finalization cannot publish a schedule')
        require(final['raw_reference']==detail['raw_reference'] and detail['raw_reference']['path']==str(directory/'raw.json'),
            'Raw reference differs from independent audit')
        raw=read(detail['raw_reference'],sources)
        require(raw['started_reference']==detail['started_reference'] and detail['started_reference']['path']==str(directory/'started.json'),
            'Started reference differs from independent audit')
        started=read(detail['started_reference'],sources)
        require(raw['schema']=='BAD_TAIL_TARGET_RAW_RESULT_V1' and raw['status']=='FIT_RETURNED' and raw['plan_reference']==PLAN and
            raw['execution_date']==DATES[index] and raw['fitted']['targets']==detail['targets'] and
            raw['previous_target_weights']==previous and raw['previous_target_reference']==previous_raw and
            type(raw['new_fit_attempt_count']) is int and type(detail['new_fit_attempt_count']) is int and
            raw['new_fit_attempt_count']==detail['new_fit_attempt_count']==(0 if index in (0,5) else 1),
            'Saved raw target and independently audited chain differ')
        binding=detail['numerical_and_lane_binding']
        require(encoded(raw['numerical_and_lane_binding'])==encoded(started['numerical_and_lane_binding'])==encoded(binding) and
            binding['lane_previous_target_weights']==previous and binding['lane_risk_chains_by_security']==detail['lane_risk_chains_by_security'],
            'Independent risk/provenance binding differs')
        require(raw['fitted']['previous_target_weights']==binding['fit_actual_previous_target_weights'] and
            binding['fit_actual_previous_target_weights']==({} if index in (0,5) else previous),
            'Original numerical prior and strategic prior were mixed')
        selected=set(detail['targets']);chains=detail['lane_risk_chains_by_security']
        require(set(chains)==selected|set(previous or {}) and all(type(v) is str and v and v==v.strip() for v in chains.values()),
            'Complete selected and prior SID risk-chain union required')
        require(CUTOFFS[index] in calendar and DATES[index] in calendar and calendar.index(DATES[index])==calendar.index(CUTOFFS[index])+1,
            'Next observed execution clock differs')
        rows.append(dict(decision_date=CUTOFFS[index],execution_date=DATES[index],targets=detail['targets']))
        risk_chains[CUTOFFS[index]]=chains
        previous={sid:target['target_weight'] for sid,target in detail['targets'].items()};previous_raw=detail['raw_reference']
    value=dict(schema='BAD_TAIL_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1',plan_reference=PLAN,calendar=calendar,schedule=rows,
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
    linkage=dict(schema='BAD_TAIL_SIX_PERIOD_SCHEDULE_INDEPENDENT_LINKAGE_V1',schedule_reference=schedule_ref,
        independent_target_audit_reference=audit_reference,plan_reference=PLAN,exact_schedule_reconstruction=True,
        decision_count=6,source_hashes=sources,fitter_called=False,account_engine_called=False,
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
