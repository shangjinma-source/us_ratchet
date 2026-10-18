"""Hash-bound historical training lanes; no fitting or account-outcome inputs."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()

ORDERS={
    'RETURN':(('return_p50',-1),('return_p10',-1),('max_drawdown_p90',1),('target_012922_distance',1)),
    'BAD_TAIL':(('return_p10',-1),('return_p50',-1),('max_drawdown_p90',1),('target_012922_distance',1)),
    'DRAWDOWN':(('max_drawdown_p90',1),('max_drawdown_p50',1),('return_p10',-1),('target_012922_distance',1)),
    'LEGACY_TARGET_DISTANCE':(('target_012922_distance',1),('return_p10',-1),('max_drawdown_p90',1),('return_p50',-1)),
}


def require(condition,message):
    if not condition:
        raise ValueError(message)


def read(reference,sources):
    require(type(reference) is dict and set(reference)=={'path','sha256'},'Exact path and SHA reference required')
    path=Path(reference['path']).resolve();raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    require(digest==reference['sha256'],'Source SHA mismatch: '+str(path))
    require(str(path) not in sources or sources[str(path)]==digest,'Conflicting source reference')
    sources[str(path)]=digest
    return json.loads(raw)


def day(value):
    require(type(value) is str and date.fromisoformat(value).isoformat()==value,'Canonical date required')
    return value


def prepare_decision(queue_reference):
    sources={};queue=read(queue_reference,sources)
    require(queue.get('schema')=='CORRECTED_FRONTIER_HISTORICAL_CUTOFF_QUEUE_V1','Corrected queue required')
    cutoff=day(queue['historical_cutoff']);execution=day(queue['coordinate']['selection_date'])
    require(cutoff<execution,'Cutoff must precede execution')
    context=read(queue['context'],sources);frontier=read(queue['frontier'],sources)
    complete=read(frontier['complete_date_artifact'],sources)
    independent=read(frontier['independent_full_diff_artifact'],sources)
    require(independent.get('schema')=='SELECTED_ARCHIVE_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1'
        and independent.get('date')==execution
        and Path(independent['output_path']).resolve()==Path(frontier['complete_date_artifact']['path']).resolve()
        and independent['output_sha256']==frontier['complete_date_artifact']['sha256']
        and independent['original_count']==complete['original_count']
        and all(independent.get(key) is True for key in ('whole_date_task_map_verified','ordered_full_record_diff_verified',
            'full_new_results_match_external_checkpoints','output_source_partitions_reverified')),
        'Independent full-record diff does not bind this complete overlay')
    require(frontier.get('schema')=='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1','Complete training frontier required')
    require(frontier['coordinate']==queue['coordinate']==complete['coordinate'],'Mixed decision coordinates')
    require(frontier['original_decision_data_end']==cutoff,'Frontier cutoff differs')
    require(complete.get('economic_inputs_complete') is True and complete.get('pending_count')==0,'Incomplete training records')
    contract=queue['original_fourteen_parameter_contract']
    encoded_contract=context['prepared_inputs']['contract']['payload']['mapping']
    decoded_contract={key:float.fromhex(value['float_hex']) if type(value) is dict and set(value)=={'float_hex'} else value
        for key,value in encoded_contract.items()}
    require(decoded_contract==contract,'Original context and queue contracts differ')
    calendars=[]
    for key in ('returns','nominal_prices','target_returns'):
        panel=context['prepared_inputs'][key]['payload']['mapping']
        calendar=[]
        for encoded in panel['index']['items']:
            timestamp=encoded['timestamp']
            require(type(timestamp) is str and timestamp.endswith('T00:00:00'),'Canonical midnight training date required')
            calendar.append(day(timestamp[:10]))
        require(calendar and calendar==sorted(set(calendar)) and calendar[-1]==cutoff,'Training calendar exceeds or misses cutoff')
        calendars.append(calendar)
    require(calendars[0]==calendars[1]==calendars[2],'Three training calendars differ')
    calendar=calendars[0]
    fit,window,step=(contract[key] for key in ('fit_days','window_days','step_days'))
    require(all(type(value) is int and value>0 for value in (fit,window,step)),'Positive exact window contract required')
    windows=[dict(fit_start=calendar[start-fit],fit_end=calendar[start-1],
        evaluation_start=calendar[start],evaluation_end=calendar[start+window-1])
        for start in range(fit,len(calendar)-window+1,step)]
    require(windows,'No matured inner training evaluation window')
    require(all(row['fit_end']<row['evaluation_start']<=row['evaluation_end']<=cutoff for row in windows),'Unmatured training window')
    universe=context['prepared_inputs']['universe']['payload']['mapping']
    columns=universe['columns']['items'];values=universe['column_values']['items']
    require(len(columns)==len(set(columns))==len(values),'Ambiguous universe columns')
    identity_columns={key:values[columns.index(key)]['items'] for key in ('ticker','security_id','issuer_id','risk_chain')}
    require(len({len(value) for value in identity_columns.values()})==1,'Universe columns differ in length')
    identities={}
    for index,ticker in enumerate(identity_columns['ticker']):
        identity={key:column[index] for key,column in identity_columns.items()}
        require(all(type(value) is str and value and value==value.strip() for value in identity.values()),'Invalid security identity')
        require(ticker not in identities,'Duplicate universe ticker')
        identities[ticker]=identity
    require(len({value['security_id'] for value in identities.values()})==len(identities),'Duplicate universe SID')
    diagnostics={row['job_id']:row for row in frontier['candidate_diagnostics']}
    records=complete['records'];count=frontier['original_count']
    require(type(count) is int and len(diagnostics)==len(frontier['candidate_diagnostics'])==len(records)==count==complete['original_count'],'Incomplete task denominator')
    seen=set();eligible=[];rejected=[];preference=[]
    for record in records:
        task=record['task'];job=task['job_id'];result=record['result']
        require(job not in seen and job in diagnostics,'Duplicate or missing task identity');seen.add(job)
        diagnostic=diagnostics[job]
        require(record['status']=='AVAILABLE' and task['decision_data_end']==cutoff,'Incomplete or future training record')
        require(all(task[key]==queue['coordinate'][key] for key in ('selection_date','source_batch','universe_track')),'Record date/scope differs')
        require(all(task[key]==result[key]==diagnostic[key] for key in ('tickers','holding_count','weight_spec')),'Portfolio identity differs')
        names=task['tickers'].split(';')
        require(type(task['holding_count']) is int and len(names)==task['holding_count']==len(set(names)),'Cardinality differs')
        require(all(name in identities for name in names),'Security missing from bound universe')
        selected={identities[name]['security_id']:{key:identities[name][key] for key in ('ticker','issuer_id','risk_chain')} for name in names}
        require(len({value['issuer_id'] for value in selected.values()})==len(names),'Duplicate issuer')
        require(task['weight_spec'] in ('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor'),'Unsupported weight spec')
        window_metadata_present=any(key in result for key in ('rolling_fit_window_count',
            'fit_strictly_before_evaluation','last_fit_evaluation_boundary'))
        if task['weight_spec']!='equal_weight' or window_metadata_present:
            require(type(result.get('rolling_fit_window_count')) is int
                and result['rolling_fit_window_count']==len(windows)
                and result.get('fit_strictly_before_evaluation') is True
                and result.get('last_fit_evaluation_boundary')==windows[-1]['fit_end']+'<'+windows[-1]['evaluation_start'],
                'Saved fitted-window metadata differs from bound calendar')
        require(all(result[key]==value for key,value in diagnostic['absolute_metrics'].items()),'Frontier/result metric mismatch')
        metrics={key:result[key] for key in {name for order in ORDERS.values() for name,_ in order}}
        require(all(type(value) in (float,int) and Decimal(str(value)).is_finite() for value in metrics.values()),'Invalid training metric')
        candidate=dict(job_id=job,holding_count=task['holding_count'],tickers=task['tickers'],
            weight_spec=task['weight_spec'],selected=selected,metrics=metrics,
            saved_fit_window_metadata_verified=window_metadata_present,
            equal_weight_saved_fit_metadata_absent=task['weight_spec']=='equal_weight' and not window_metadata_present)
        if task['weight_spec']=='equal_weight' and set(names)=={'AMAT','AVGO','CDNS','GOOG'}:
            preference.append(dict(candidate=deepcopy(candidate),role='USER_PREFERENCE',
                original_fractional_risk_liquidity_passed=diagnostic.get('fractional_risk_liquidity_passed') is True))
        if diagnostic.get('fractional_risk_liquidity_passed') is True:
            eligible.append(candidate)
        else:
            rejected.append(job)
    require(seen==set(diagnostics),'Task denominator differs')
    require(len(preference)<=1,'Ambiguous user-preference reference')
    lanes={}
    for role,order in ORDERS.items():
        # Negating Decimal depends on caller precision; compare raw floats with
        # signed ordering instead (the sealed statistics are binary floats).
        key=lambda row:tuple(row['metrics'][field]*direction for field,direction in order)
        best=min((key(row) for row in eligible),default=None)
        lanes[role]=sorted([deepcopy(row) for row in eligible if key(row)==best],key=lambda row:row['job_id'])
    return dict(queue_reference=deepcopy(queue_reference),execution_date=execution,cutoff=cutoff,
        source_hashes=sources,original_scope=queue['coordinate'],scope='ORIGINAL_RESEARCHED_SUBPOOL_NOT_FULL_NDX',
        original_task_count=count,eligible_task_count=len(eligible),rejected_job_ids=sorted(rejected),
        training_calendar=calendar,inner_windows=windows,contract=deepcopy(contract),lanes=lanes,
        user_preference_reference=dict(status='AVAILABLE_RESEARCH_REFERENCE' if preference else 'UNAVAILABLE_IN_BOUND_COHORT',
            records=preference,optimization_winner=False,missing_reference_substituted=False),
        prior_fit_queue_candidate_count=queue['candidate_count'],new_fits_performed=False,
        ranking_scope='ALL_COMPLETE_TRAINING_RECORDS_PASSING_ORIGINAL_FRACTIONAL_RISK_AND_LIQUIDITY',
        minimum_weight_and_five_risk_cutoff_admission_verified=False)


def prepare_lanes(queue_references):
    require(type(queue_references) is list and queue_references,'Explicit chronological queue references required')
    decisions=[prepare_decision(reference) for reference in queue_references]
    require([row['execution_date'] for row in decisions]==sorted({row['execution_date'] for row in decisions}),'Duplicate or unordered decisions')
    for previous,current in zip(decisions,decisions[1:]):
        require(previous['execution_date']<=current['cutoff'],'Overlapping decision times')
    issuer_by_security={}
    for decision in decisions:
        for choices in decision['lanes'].values():
            for choice in choices:
                for sid,identity in choice['selected'].items():
                    require(sid not in issuer_by_security or issuer_by_security[sid]==identity['issuer_id'],
                        'Permanent SID issuer changed across decisions')
                    issuer_by_security[sid]=identity['issuer_id']
    dependencies=[]
    for role in ORDERS:
        previous=[];previous_reachable=False
        for index,decision in enumerate(decisions):
            current=[];reachable=index==0 or previous_reachable
            for row in decision['lanes'][role]:
                node=f"{role}:{decision['execution_date']}:{row['job_id']}"
                dependencies.append(dict(node_id=node,previous_choice_nodes=deepcopy(previous),
                    first_decision=index==0,cutoff=decision['cutoff'],execution_date=decision['execution_date'],
                    candidate=deepcopy(row),
                    previous_target_binding='NONE_FIRST_DECISION' if index==0 else 'UNRESOLVED_PREVIOUS_SUCCESSFUL_STRATEGIC_TARGET_SHA_AND_SID',
                    anchor_uses_actual_fills=False,unanchored_saved_fit_is_continuous_target=False,
                    dependency_status='NEEDS_TARGET_MATERIALIZATION' if reachable else 'BLOCKED_UNREACHABLE_PREVIOUS_LANE',
                    ancestry_reachable=reachable))
                current.append(node)
            previous=current;previous_reachable=reachable and bool(current)
    return dict(schema='CUTOFF_TRAINING_LANE_DEPENDENCY_PREPARE_V1',decisions=decisions,dependencies=dependencies,
        declared_lane_orders=deepcopy(ORDERS),economic_tie_policy='KEEP_ALL_EXACT_METRIC_TIES_NO_K_TICKER_TIEBREAK',
        legacy_target_distance_semantics='SUM_ABSOLUTE_RETURN_P50_P10_AND_DRAWDOWN_P50_P90_DIFFERENCES_NOT_ONE_SIDED_ADMISSION',
        observed_calendar_exchange_certified=False,external_expected_decision_denominator_verified=False,
        source_authenticity_verified=False,member_point_in_time_verified=False,
        fit_performed=False,whole_lot_execution_performed=False,continuous_target_schedule_built=False,
        historical_account_outcomes_used_for_selection=False,full_ndx_pool_coverage_verified=False,
        selection_scope='CONDITIONAL_ARCHIVED_TRAINING_LANES_NOT_LIVE_ADMISSION',promotion_allowed=False)
