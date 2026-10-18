"""Complete saved/derived daily chain projection, with explicit numerical bases."""
from copy import deepcopy
from datetime import date
import json
import re

MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
TRACKS=('CONTINUOUS','WHOLE_LOT')
FALSE=('account_executed','risk_gate_recomputed','normalization_performed','point_in_time_verified','promotion_allowed','source_bytes_authenticated','historical_label_validity_verified','full_h_delivery_complete')


def require(value,message):
    if not value:raise ValueError(message)


def text(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def exact(a,b):require(text(a)==text(b),'Exact original evidence')


def build_chain_projection(*,supplement_document,diagnostics_document,references,aggregate_saved_weights):
    require(set(references)=={'supplement','diagnostics'},'Two projection references')
    for value in references.values():require(type(value)is dict and set(value)=={'path','sha256'}and type(value['path'])is str and bool(value['path'])and type(value['sha256'])is str and re.fullmatch('[0-9a-f]{64}',value['sha256']),'Explicit source reference')
    require(supplement_document['schema']=='MULTIDECISION_HOLDINGS_SUPPLEMENT_DOCUMENT_V1' and diagnostics_document['schema']=='CANDIDATE_SAVED_RISK_DIAGNOSTIC_DOCUMENT_V1','Input document roles')
    supplement=supplement_document['supplement'];require(supplement['schema']=='MULTIDECISION_SAVED_HOLDINGS_SUPPLEMENT_V1','Saved H role')
    for doc in (supplement,diagnostics_document):
        require(doc['point_in_time_verified']is False and doc['promotion_allowed']is False,'Conditional source scope')
    exact(diagnostics_document['input_references']['inputs'],supplement['references']['candidate_inputs'])
    exact(diagnostics_document['input_references']['execution'],supplement['references']['candidate_execution'])
    calendar=supplement['calendar'];require(len(calendar)==120 and calendar==sorted(set(calendar)),'Full ordered 120 sessions')
    require(all(type(d)is str and date.fromisoformat(d).isoformat()==d for d in calendar),'ISO calendar')
    diagnostic_paths=diagnostics_document['paths'];exact([p['track_index']for p in diagnostic_paths],[8,10,12,14])
    exact(diagnostics_document['blocked_track_indices'],list(range(8)))
    diagnostic_by_index={p['track_index']:p for p in diagnostic_paths}
    paths=[];counts={};table_days=[];table_chains=[];table_sources=[]
    blocked=supplement['tables'][5];require(blocked['name']=='未执行阻断轨道'and len(blocked['rows'])==8,'Eight original blocked slots')
    exact([r[1]for r in blocked['rows']],list(range(8)))
    for role in ('candidate','control'):
        bundles=supplement['original_raw_bundles_preserved'][role];require(len(bundles)==16,'Full original 16 slots')
        for index,bundle in enumerate(bundles):
            coordinate=[MODES[index//8],LANES[(index%8)//2],TRACKS[index%2]]
            if role=='candidate'and index<8:
                require(bundle is None,'Blocked has no RAW');paths.append(dict(role=role,track_index=index,coordinate=coordinate,status='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT',rows=None,original_blocked_row=deepcopy(blocked['rows'][index])));continue
            require(type(bundle)is dict,'Returned RAW required');raw=bundle['document']
            require(raw['returned']is True and raw['error']is None,'Successful original RAW')
            daily=raw['result']['daily'];exact([d['session']for d in daily],calendar)
            dp=diagnostic_by_index.get(index)if role=='candidate'and index%2==0 else None
            if dp is not None:
                exact(dp['coordinate'],coordinate);exact(dp['raw_reference'],bundle['reference'])
                exact([r['daily_index']for r in dp['projection']['rows']],list(range(120)))
            group=role+'_'+coordinate[2];summary=counts.setdefault(group,dict(days=0,numeric=0,undefined=0))
            rows=[]
            for n,day in enumerate(daily):
                source=dict(reference=deepcopy(bundle['reference']),json_pointer=f'/result/daily/{n}')
                if index%2:
                    basis='DERIVED_SUM_OF_SAVED_WHOLE_SID_WEIGHTS_NO_RENORMALIZATION'
                    require(type(day['shares'])is dict and all(type(q)is int and q>=0 for q in day['shares'].values()),'Original whole quantities')
                    held={sid for sid,q in day['shares'].items()if q>0}
                    weights=day['risk']['actual_weights']if held else day['risk'].get('actual_weights',{})
                    labels=day['risk_chains'];dates=day['risk_chain_observation_dates']
                    require(bool(weights)==bool(held),'Whole positive-holding state agrees with weights')
                    require(held<=set(weights),'Every held SID has saved weight')
                    saved=dict(weights=deepcopy(weights),chains=deepcopy(labels),observation_dates=deepcopy(dates))
                    aggregate=aggregate_saved_weights(session=day['session'],weights=weights,chains=labels,observation_dates=dates)if weights else None
                    if not weights:require(not labels and not dates,'Empty whole label evidence')
                    values=aggregate['chain_weights']if aggregate is not None else None
                elif role=='control':
                    basis='ORIGINAL_SAVED_CONTROL_CONTINUOUS_CHAIN_WEIGHTS'
                    weights=day['risk']['actual_weights'];require(bool(weights)==bool(day['holdings']),'Control empty state')
                    values=deepcopy(day['risk'].get('risk_chain_weights'))
                    require((type(values)is dict and bool(values))if weights else values is None,'Original control chain availability')
                    saved=dict(risk=deepcopy(day['risk']));aggregate=None
                else:
                    basis='PREVIOUSLY_AUDITED_CANDIDATE_CONTINUOUS_DERIVED_CHAIN_WEIGHTS'
                    original=dp['projection']['rows'][n];diag=original['diagnostic'];exact(diag['session'],day['session'])
                    require((diag['metrics']is not None)==bool(day['holdings']),'Candidate empty state')
                    values=deepcopy(diag['chain_weights'])if diag['metrics']is not None else None
                    if values is None:require(diag['chain_weights']=={},'Empty diagnostic chains')
                    saved=deepcopy(original);aggregate=None
                    source['diagnostic_locator']=dict(reference=deepcopy(references['diagnostics']),json_pointer=f'/paths/{[8,10,12,14].index(index)}/projection/rows/{n}')
                status='DEFINED'if values is not None else 'EMPTY_HOLDINGS_UNDEFINED'
                summary['days']+=1;summary['numeric']+=values is not None;summary['undefined']+=values is None
                row=dict(session=day['session'],daily_index=n,status=status,basis=basis,chain_weights=values,
                         original_evidence=saved,new_aggregation=aggregate,source_locator=source)
                rows.append(row);prefix=[role,index,*coordinate,day['session']]
                table_days.append(prefix+[status,basis,None if values is None else text(values),text(source)])
                if values is None:table_chains.append(prefix+[status,basis,None,None,text(source)])
                else:
                    for label,value in values.items():table_chains.append(prefix+[status,basis,label,text(value),text(source)])
                table_sources.append(prefix+[text(saved),None if aggregate is None else text(aggregate),text(source)])
            paths.append(dict(role=role,track_index=index,coordinate=coordinate,status='RETURNED',raw_reference=deepcopy(bundle['reference']),rows=rows))
    exact(counts,{'candidate_CONTINUOUS':dict(days=480,numeric=476,undefined=4),'candidate_WHOLE_LOT':dict(days=480,numeric=392,undefined=88),'control_CONTINUOUS':dict(days=960,numeric=952,undefined=8),'control_WHOLE_LOT':dict(days=960,numeric=952,undefined=8)})
    headers=['角色','轨道序号','FX','lane','账户轨','日期']
    tables=[dict(name='全部每日链口径',headers=headers+['状态','数值来源口径','链权重原值JSON','来源'],rows=table_days),
            dict(name='逐链每日权重',headers=headers+['状态','数值来源口径','风险链','权重精确原文','来源'],rows=table_chains),
            dict(name='链投影原证据',headers=headers+['原证据JSON','新聚合JSON','来源'],rows=table_sources),deepcopy(blocked)]
    return dict(schema='MULTIDECISION_DAILY_CHAIN_PROJECTION_V1',calendar=deepcopy(calendar),paths=paths,counts_by_role_track=counts,
        day_count=2880,numeric_day_count=2772,undefined_day_count=108,blocked_path_count=8,tables=tables,references=deepcopy(references),
        new_saved_weight_chain_addition_performed=True,original_saved_chain_aggregate_for_all_rows=False,
        remaining_gaps=['WORKBOOK_EXPORT_AND_FULL_CELL_READBACK','FORMAL_VISUAL_ACCEPTANCE_NOT_YET_PERFORMED'],**dict.fromkeys(FALSE,False))
