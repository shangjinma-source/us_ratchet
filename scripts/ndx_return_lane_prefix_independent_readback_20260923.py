"""Independent standard-library readback of an externally pinned RETURN prefix."""
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
FOLDER=ROOT/'data/cache/research/return_lane_targets_20260923_v1'
DATES=('2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01')
CUTOFFS=('2023-03-31','2023-04-28','2023-05-31','2023-06-30','2023-07-31','2023-08-31')
PLAN=dict(path=str(FOLDER/'plan.json'),sha256='bb8e07498ae81de235630fa819d27682420ceb24a04cbaf4f9a1763190f19c7c')
LANE_SHA='b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba'
FROZEN_SOURCES={
    str(ROOT/'backtest/ndx_return_lane_target_materialization_research.py'):'62147379ccbd828c9f79c43d5471134a4336a137018a0192af71df6df11299cd',
    str(ROOT/'scripts/ndx_return_lane_target_materialization_20260923.py'):'6ebbbd1cf1f15fd06b271290795ce209baa5a747ccd217d82395b70e83469106',
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


def validate_step(*,index,started,raw,final,selected,parameters,weight_spec,previous,previous_reference):
    execution,cutoff=DATES[index],CUTOFFS[index]
    require(final['schema']=='RETURN_TARGET_STEP_FINALIZATION_V1' and raw['schema']=='RETURN_TARGET_RAW_RESULT_V1'
        and started['schema']=='RETURN_TARGET_SINGLE_ATTEMPT_V1','Unexpected step schema')
    require(all(value['plan_reference']==PLAN for value in (final,raw,started)),'Foreign plan binding')
    require(all(value['execution_date']==execution for value in (final,raw,started)) and started['cutoff']==cutoff,'Decision coordinate differs')
    require(final['status']=='TARGET_FIVE_RISKS_PASSED' and final['detail'] is None and raw['status']=='FIT_RETURNED','Unsuccessful prefix step')
    require(all(final[key] is False for key in ('fallback_performed','whole_lot_execution_performed','promotion_allowed'))
        and started['order_generation_allowed'] is False,'Authority escalation')
    require(type(raw['new_fit_attempt_count']) is int and raw['new_fit_attempt_count']==(1 if index else 0)
        and raw['first_fit_imported_without_refit'] is (index==0) and started['new_fit_attempt'] is (index>0),'Import/new-fit semantics differ')
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
    require(fitted['previous_target_weights']==(previous or {}) and fitted['checkpoint_weights_used'] is False,
        'Fitted anchor dropped or changed previous strategic SID weights')
    for value in (previous or {}).values():arithmetic.number(value)
    mass=sum((previous or {}).get(sid,0.) for sid in sorted(selected))
    anchor={sid:(previous or {}).get(sid,0.)/mass if mass>0 else 0. for sid in selected}
    strength=parameters['turnover_anchor_strength'] if mass>0 and weight_spec=='constrained_fixed_shrinkage_turnover_anchor' else 0.
    require(type(fitted['anchor_by_security']) is dict and set(fitted['anchor_by_security'])==set(anchor),
        'Exact anchor SID denominator required')
    for value in fitted['anchor_by_security'].values():arithmetic.number(value)
    require(type(fitted['surviving_anchor_mass']) in (int,float) and fitted['surviving_anchor_mass']==mass
        and fitted['anchor_by_security']==anchor and type(fitted['effective_anchor_strength']) in (int,float)
        and fitted['effective_anchor_strength']==strength,'Survivor normalization or weight-spec anchor strength differs')
    require(fitted['risk_chains_by_security']=={sid:row['risk_chain'] for sid,row in selected.items()},'Target risk identities differ')
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
        effective_anchor_strength=strength,complete_previous_strategic_target_exact=True)


def check_numerical_sources(fitted,expected):
    require(type(expected) is dict and expected and fitted.get('source_hashes')==expected,
        'Exact hard first-fit numerical source closure required')


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
    require(plan['schema']=='RETURN_SIX_PERIOD_STRATEGIC_TARGET_PLAN_V1' and plan['lane_prepare']['sha256']==LANE_SHA,'Hard plan/lane differs')
    lane=read(plan['lane_prepare']);original=read(plan['first_fit']);original_audit=read(plan['first_fit_audit'])
    calendar=[row['session'] for row in read(plan['calendar'])['execution']['daily']]
    require(calendar==sorted(set(calendar)),'Observed execution calendar differs')
    require(len(lane['decisions'])==6 and [row['execution_date'] for row in lane['decisions']]==list(DATES)
        and [row['cutoff'] for row in lane['decisions']]==list(CUTOFFS),'Hard six-date denominator differs')
    previous=None;previous_reference=None;details=[];issuer_by_sid={}
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
        entries=[row for row in queue['candidates'] if row['task']['job_id']==job]
        choices=[row for row in decision['lanes']['RETURN'] if row['job_id']==job]
        require(len(entries)==len(choices)==1 and started['job_id']==job,'Exact RETURN chosen job differs')
        entry=entries[0];selected=entry['selected'];parameters=queue['fit_parameters'];fitted=raw['fitted']
        check_numerical_sources(fitted,original['result']['refit']['source_hashes'])
        require(queue['historical_cutoff']==cutoff and queue['coordinate']['selection_date']==execution
            and selected==choices[0]['selected'],'Queue/selection identities differ')
        require(started['runtime']==queue['original_runtime']==context['runtime'],'Original runtime binding differs')
        for sid,row in selected.items():
            require(sid not in issuer_by_sid or issuer_by_sid[sid]==row['issuer_id'],'Permanent SID issuer changed')
            issuer_by_sid[sid]=row['issuer_id']
        observed=validate_step(index=index,started=started,raw=raw,final=final,selected=selected,parameters=parameters,
            weight_spec=entry['task']['weight_spec'],previous=previous,previous_reference=previous_reference)
        matrix=matrix_check(context,selected,parameters,cutoff,fitted)
        if index==0:
            require(digest(fitted)==digest(original['result']['refit']),'First fit not exact imported raw')
            audited=[row for row in original_audit['details'] if row['job_id']==job]
            require(len(audited)==1 and audited[0]['result_reference']==plan['first_fit']
                and audited[0]['typed_decimal']['fit_data_sha256']==matrix['fit_data_sha256'],'First-fit independent audit binding differs')
        for path,sha in FROZEN_SOURCES.items():
            require(started['source_hashes'].get(path)==sha,'Original core/CLI source lock absent or different')
        require(started['source_hashes'].get(PLAN['path'])==PLAN['sha256'],'Hard plan source lock missing')
        merge_sources(sources,started['source_hashes']);merge_sources(sources,fitted['source_hashes'])
        details.append(dict(execution_date=execution,cutoff=cutoff,job_id=job,finalization_reference=reference,
            raw_reference=final['raw_reference'],started_reference=raw['started_reference'],targets=fitted['targets'],
            new_fit_attempt_count=raw['new_fit_attempt_count'],**observed,**matrix))
        previous={sid:row['target_weight'] for sid,row in fitted['targets'].items()};previous_reference=final['raw_reference']
    verify_sources(sources)
    return dict(schema='RETURN_COMPLETE_PREFIX_INDEPENDENT_READBACK_V1',status='PASSED',plan_reference=PLAN,
        completed_prefix_count=len(references),finalization_references=references,details=details,source_hashes=sources,
        first_import_count=1,new_fit_observed_count=len(references)-1,
        any_actual_exiting_sid_case=any(row['exited_previous_sids'] for row in details),
        observed_calendar_exchange_certified=False,optimizer_called=False,owner_validator_called=False,account_engine_called=False,
        next_step_technically_ready=len(references)<6,next_step_execution_authorized=False,
        point_in_time_verified=False,promotion_allowed=False)


def run(*,finalization_paths,finalization_sha256,output):
    require(type(finalization_paths) is list and type(finalization_sha256) is list
        and len(finalization_paths)==len(finalization_sha256),'Matching externally declared prefix paths and SHAs required')
    destination=Path(output).resolve();require(not destination.exists(),'Create-only readback output')
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
