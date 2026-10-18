"""Pure complete-subqueue overlay for the 614 DELTA incumbent-paired repairs."""
from collections import Counter
from copy import deepcopy
import math
from backtest.ndx_corrected_cohort_overlay_research import digest,PAIRED_KEYS


def extend_delta_paired_overlay(*,parent,replacements,expected_tasks):
    if parent['schema'] not in ('ndx_corrected_cohort_overlay_v1','ndx_corrected_base_overlay_v2'):
        raise ValueError('Existing researched date overlay required')
    if parent['promotion_allowed'] is not False or parent['selection_performed'] is not False:
        raise ValueError('Unselected nonpromoted parent required')
    expected={task['job_id']:task for task in expected_tasks}
    if not expected or len(expected)!=len(expected_tasks):raise ValueError('Complete unique planned date subqueue required')
    supplied={}
    for row in replacements:
        job=row['task']['job_id']
        if job in supplied or expected.get(job)!=row['task']:raise ValueError('Unknown/duplicate replacement task')
        supplied[job]=row
    if set(supplied)!=set(expected):raise ValueError('Whole planned paired-only date subqueue required')
    output=deepcopy(parent);seen=set();changed=set()
    for record in output['records']:
        job=record['task']['job_id']
        if job in seen:raise ValueError('Duplicate original record job')
        seen.add(job)
        if job not in supplied:continue
        row=supplied[job]
        if (record['origin']!='DELTA' or record['status']!='PENDING_NUMERICAL_DELTA' or record['result'] is not None or
            record['task']!=row['task']):raise ValueError('Planned DELTA task is not the matching original pending record')
        original,corrected=row['original_result'],row['result']
        if set(original)!=set(corrected):raise ValueError('Complete original result field set required')
        if any(original.get(key)!=row['task'][key] or corrected.get(key)!=row['task'][key] for key in ('tickers','holding_count','weight_spec')):
            raise ValueError('Original/corrected numerical identity differs')
        if any(type(result.get(key)) not in (int,float) or not math.isfinite(result[key]) for result in (original,corrected) for key in PAIRED_KEYS):
            raise ValueError('Finite complete paired four metrics required')
        if {k:v for k,v in original.items() if k not in PAIRED_KEYS}!={k:v for k,v in corrected.items() if k not in PAIRED_KEYS}:
            raise ValueError('Candidate/012922/risk/whole-lot or other original field changed')
        if (row['original_historical_provenance_verified'] is not False or row['point_in_time_verified'] is not False or
            row['promotion_allowed'] is not False or row['reconstruction_scope']!='NUMERICAL_RECONSTRUCTION_WITH_HISTORICAL_LOADER_PROVENANCE_GAP'):
            raise ValueError('Explicit limited historical-gap semantics required')
        gaps=row['historical_loader_provenance_gaps']
        if (type(gaps) is not list or len(gaps)!=1 or gaps[0]['original_pointer_preserved'] is not True or
            gaps[0]['used_as_current_numerical_input'] is not False or gaps[0]['status'] not in ('HISTORICAL_SOURCE_DRIFT','UNAVAILABLE')):
            raise ValueError('Original declared historical loader gap must be preserved')
        record.update(result=deepcopy(corrected),status='AVAILABLE',overlay_mode='DELTA_PAIRED_COMPLETE_SUBQUEUE',
            original_historical_provenance_verified=False)
        record['lineage']=dict(record['lineage'],completed_delta_paired=dict(deepcopy(row['lineage']),historical_loader_provenance_gaps=deepcopy(gaps)))
        changed.add(job)
    if changed!=set(expected):raise ValueError('Planned date subqueue absent from parent')
    available=Counter(r['origin'] for r in output['records'] if r['status']=='AVAILABLE')
    pending=Counter(r['origin'] for r in output['records'] if r['status']=='PENDING_NUMERICAL_DELTA')
    planned=Counter(r['origin'] for r in output['records'])
    if (len(seen)!=parent['original_count'] or sum(available.values())+sum(pending.values())!=len(seen) or
        sum(available.values())!=parent['available_count']+len(changed) or sum(pending.values())!=parent['pending_count']-len(changed)):
        raise ValueError('Complete original date counts differ')
    if any(r['result'] is not None for r in output['records'] if r['status']=='PENDING_NUMERICAL_DELTA'):
        raise ValueError('Pending economic results must remain None')
    output.update(schema='ndx_corrected_delta_paired_overlay_v1',available_count=sum(available.values()),pending_count=sum(pending.values()),
        counts={origin:dict(planned=count,available=available[origin],pending=pending[origin]) for origin,count in planned.items()},
        records_sha256=digest(output['records']),delta_paired_added=len(changed),economic_inputs_complete=not pending,
        input_artifact_binding_verified=False,original_historical_provenance_verified=False,
        point_in_time_verified=False,promotion_allowed=False,selection_performed=False,winner=None)
    return output
