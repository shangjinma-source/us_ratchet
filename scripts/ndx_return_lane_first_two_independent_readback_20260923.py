"""Standard-library independent readback of two sealed RETURN targets. No fitting."""
import hashlib
import json
import math
import os
from decimal import Context,Decimal,localcontext
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/cache/research/return_lane_targets_20260923_v1'
PLAN_SHA='bb8e07498ae81de235630fa819d27682420ceb24a04cbaf4f9a1763190f19c7c'
LANE_SHA='b7eaff190f3b2225db87d14fd0f7afc0cd9420536e9a4661f986f8ac319a96ba'
FINAL_SHAS=('0de08ffabafc5a9ea5ed5e9828ff57c589bf1be292eccf35557410f69ff2c0ae',
    '419fc15600349c5b7a6fe2d9a4bf5aeb64798f67d3825311d603f185c9fea692')
DATES=('2023-04-03','2023-05-01');CUTOFFS=('2023-03-31','2023-04-28')


def require(condition,message):
    if not condition:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def number(value):
    require(type(value) in (int,float) and math.isfinite(value),'Finite nonboolean number required')
    return Decimal(str(value))


def decimal_risks(fitted,parameters,selected):
    with localcontext(Context(prec=70)):
        weights={sid:number(row['target_weight']) for sid,row in fitted['targets'].items()}
        require(set(weights)==set(selected) and all(weight>0 for weight in weights.values()),'Positive exact target SID set required')
        total=sum(weights.values(),Decimal(0));tolerance=Decimal('1e-9')
        require(abs(total-1)<=tolerance,'Target simplex differs')
        ordered=sorted(weights.values(),reverse=True);chains={}
        for sid,weight in weights.items():
            chain=selected[sid]['risk_chain'];chains[chain]=chains.get(chain,Decimal(0))+weight
        effective_n=Decimal(1)/sum(weight*weight for weight in weights.values())
        checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=number(parameters['max_single_weight'])+tolerance,
            MIN_SINGLE_WEIGHT=ordered[-1]>=number(parameters['min_single_weight'])-tolerance,
            SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=number(parameters['top_weight_cap'])+tolerance,
            MINIMUM_EFFECTIVE_N=effective_n>=len(weights)*number(parameters['minimum_effective_n_ratio'])-tolerance,
            RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=number(parameters['risk_chain_top1_cap'])+tolerance)
        return dict(checks=checks,weight_sum=str(total),effective_n=str(effective_n),
            top3_weight=str(sum(ordered[:3])),risk_chain_weights={key:str(value) for key,value in chains.items()},
            tolerance=str(tolerance))


def audit():
    sources={};documents={}
    def read(path,sha):
        path=str(Path(path).resolve())
        require(path not in sources or sources[path]==sha,'Conflicting immutable source')
        if path not in documents:
            raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==sha,'Source SHA mismatch: '+path)
            documents[path]=json.loads(raw);sources[path]=sha
        return documents[path]
    def reference(ref):return read(ref['path'],ref['sha256'])
    plan=read(FOLDER/'plan.json',PLAN_SHA)
    require(plan['lane_prepare']['sha256']==LANE_SHA,'Hard lane differs');lane=reference(plan['lane_prepare'])
    original=reference(plan['first_fit']);original_audit=reference(plan['first_fit_audit'])
    calendar=[row['session'] for row in reference(plan['calendar'])['execution']['daily']]
    require(calendar==sorted(set(calendar)),'Observed execution calendar differs')
    previous=None;previous_ref=None;details=[];declared_sources={}
    for index,(execution,cutoff,sha) in enumerate(zip(DATES,CUTOFFS,FINAL_SHAS)):
        directory=FOLDER/execution
        require({path.name for path in directory.iterdir()}=={'started.json','raw.json','finalization.json'},'Missing or orphan step evidence')
        final=read(directory/'finalization.json',sha);raw=reference(final['raw_reference']);started=reference(raw['started_reference'])
        require(Path(final['raw_reference']['path']).resolve()==directory/'raw.json'
            and Path(raw['started_reference']['path']).resolve()==directory/'started.json','Wrong raw/started coordinate')
        require(final['schema']=='RETURN_TARGET_STEP_FINALIZATION_V1' and raw['schema']=='RETURN_TARGET_RAW_RESULT_V1'
            and started['schema']=='RETURN_TARGET_SINGLE_ATTEMPT_V1','Unexpected step schema')
        require(all(value['plan_reference']==dict(path=str(FOLDER/'plan.json'),sha256=PLAN_SHA) for value in (final,raw,started)),
            'Plan binding differs')
        require(all(value['execution_date']==execution for value in (final,raw,started)) and started['cutoff']==cutoff,'Decision dates differ')
        require(calendar.index(execution)==calendar.index(cutoff)+1,'Not next observed execution session')
        require(final['status']=='TARGET_FIVE_RISKS_PASSED' and final['detail'] is None and raw['status']=='FIT_RETURNED','Unsuccessful step')
        require(all(final[key] is False for key in ('fallback_performed','whole_lot_execution_performed','promotion_allowed'))
            and started['order_generation_allowed'] is False,'Authority escalation')
        require(type(raw['new_fit_attempt_count']) is int and raw['new_fit_attempt_count']==index
            and raw['first_fit_imported_without_refit'] is (index==0) and started['new_fit_attempt'] is (index>0),'Import/fit attempt semantics differ')
        require(raw['previous_target_reference']==started['previous_target_reference']==previous_ref
            and raw['previous_target_weights']==started['previous_target_weights']==previous,'Complete strategic anchor differs')
        decision=lane['decisions'][index];queue=reference(decision['queue_reference']);context=reference(queue['context'])
        job=plan['selected_job_ids'][index]
        entries=[entry for entry in queue['candidates'] if entry['task']['job_id']==job]
        choices=[choice for choice in decision['lanes']['RETURN'] if choice['job_id']==job]
        require(len(entries)==len(choices)==1 and started['job_id']==job,'Exact chosen job missing')
        selected=entries[0]['selected'];fitted=raw['fitted'];parameters=queue['fit_parameters']
        require(selected==choices[0]['selected']==started['selected'],'SID identities differ')
        require(started['parameters']==parameters and fitted['declared_parameters']=={key:value for key,value in parameters.items() if key!='fit_days'},
            'Original eight parameters differ')
        require(started['weight_spec']==entries[0]['task']['weight_spec']==fitted['weight_spec'],'Weight specification differs')
        require(started['runtime']==queue['original_runtime']==context['runtime'],'Runtime binding differs')
        for sid,target in fitted['targets'].items():
            require(set(target)=={'ticker','issuer_id','target_weight'}
                and all(target[key]==selected[sid][key] for key in ('ticker','issuer_id')),'Target security identity differs')
        require(fitted['risk_chains_by_security']=={sid:item['risk_chain'] for sid,item in selected.items()},'Risk-chain mapping differs')
        require(fitted['previous_target_weights']==(previous or {})
            and fitted['checkpoint_weights_used'] is False,'Fitted strategic anchor differs')
        mass=sum((previous or {}).get(sid,0.) for sid in sorted(selected))
        expected_anchor={sid:(previous or {}).get(sid,0.)/mass if mass>0 else 0. for sid in selected}
        require(fitted['surviving_anchor_mass']==mass and fitted['anchor_by_security']==expected_anchor
            and fitted['effective_anchor_strength']==(parameters['turnover_anchor_strength'] if mass>0 else 0.),'Survivor target renormalization differs')
        mapping=context['prepared_inputs']['returns']['payload']['mapping']
        dates=[row['timestamp'][:10] for row in mapping['index']['items']]
        require(dates==sorted(set(dates)) and dates[-1]==cutoff,'Training calendar exceeds cutoff')
        for key in ('nominal_prices','target_returns'):
            require([row['timestamp'][:10] for row in context['prepared_inputs'][key]['payload']['mapping']['index']['items']]==dates,
                'Three training calendars differ')
        fit_dates=dates[-parameters['fit_days']:];names=[selected[sid]['ticker'] for sid in sorted(selected)]
        require(fit_dates[0]>'2022-07-18','Old corrected cells require explicit correction in this reader')
        columns=mapping['columns']['items'];series=[]
        for name in names:
            values=mapping['column_values']['items'][columns.index(name)]['items'][-parameters['fit_days']:]
            require(all(type(value) is dict and set(value)=={'float_hex'} for value in values),'Unexpected typed scalar')
            series.append([float.fromhex(value['float_hex']) for value in values])
        payload=dict(dates=fit_dates,tickers=names,returns=[list(row) for row in zip(*series)])
        require(fitted['fit_data_sha256']==digest(payload) and fitted['fit_start']==fit_dates[0]
            and fitted['fit_end']==fitted['cutoff']==cutoff and type(fitted['fit_row_count']) is int
            and fitted['fit_row_count']==parameters['fit_days']==126,'Exact 126-row matrix differs')
        risks=decimal_risks(fitted,parameters,selected)
        require(all(risks['checks'].values()) and risks['checks']==fitted['declared_constraint_checks']==final['risk_checks']
            and all(type(value) is bool for value in fitted['declared_constraint_checks'].values())
            and fitted['declared_constraints_passed'] is True,'Independent Decimal risks differ')
        require(all(fitted[key] is False for key in ('point_in_time_verified','source_authenticity_verified','promotion_allowed',
            'historical_task_evaluation_performed','order_generation_allowed')),'Fitted authority differs')
        if index==0:
            require(digest(fitted)==digest(original['result']['refit']),'First fit was changed rather than reused')
            audited=[row for row in original_audit['details'] if row['job_id']==job]
            require(len(audited)==1 and audited[0]['result_reference']==plan['first_fit']
                and audited[0]['typed_decimal']['fit_data_sha256']==fitted['fit_data_sha256'],'Independent first-fit lineage differs')
        for path,expected in {**started['source_hashes'],**fitted['source_hashes']}.items():
            require(path not in declared_sources or declared_sources[path]==expected,'Conflicting source closure')
            declared_sources[path]=expected
        details.append(dict(execution_date=execution,cutoff=cutoff,job_id=job,raw_reference=final['raw_reference'],
            finalization_reference=dict(path=str(directory/'finalization.json'),sha256=sha),
            fit_start=fit_dates[0],fit_end=cutoff,fit_data_sha256=fitted['fit_data_sha256'],
            targets=fitted['targets'],previous_target_sid_count=len(previous or {}),
            exited_previous_sids=sorted(set(previous or {})-set(selected)),
            new_selected_sids=sorted(set(selected)-set(previous or {})) if previous else [],
            complete_previous_strategic_target_exact=True,decimal_risks=risks,
            new_fit_attempt_count=raw['new_fit_attempt_count']))
        previous={sid:target['target_weight'] for sid,target in fitted['targets'].items()};previous_ref=final['raw_reference']
    for path,expected in {**declared_sources,**sources}.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected,'Final source readback drift: '+path)
    return dict(schema='RETURN_FIRST_TWO_INDEPENDENT_READBACK_V1',status='PASSED',details=details,
        reader_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_hashes=sources,declared_source_count=len(declared_sources),
        first_import_count=1,new_fit_observed_count=1,optimizer_called=False,owner_validator_called=False,
        account_engine_called=False,third_step_technically_ready=True,third_step_execution_authorized=False,
        actual_exiting_sid_case_present=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    report=audit();path=FOLDER/'first_two_independent_readback.json'
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as handle:
        handle.write(raw);handle.flush();os.fsync(handle.fileno())
    require(path.read_bytes()==raw,'Published audit differs')
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),status=report['status'],
        third_step_technically_ready=True,third_step_execution_authorized=False)))
