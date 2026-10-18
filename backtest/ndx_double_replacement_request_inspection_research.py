"""Independent complete ordinal accounting for saved compressed requests.

No worker, lifecycle, evaluator, producer codec or filesystem imports. Numeric
outcomes must already come from the separate arithmetic inspector at the IO
boundary. Non-numeric attempts cannot be promoted by this accounting layer.
"""
import hashlib
import json

STATUS_KEYS=('inspected_feasible','inspected_infeasible','evaluation_exception',
             'supplied_not_evaluated_technical','supplied_not_evaluated_budget',
             'validation_failure_returned','unresolved_dispatch_or_raw')
RAW_STATUS={'FEASIBLE':'inspected_feasible','INFEASIBLE':'inspected_infeasible',
            'EVALUATION_EXCEPTION':'evaluation_exception',
            'NOT_EVALUATED_TECHNICAL_STOP':'supplied_not_evaluated_technical',
            'NOT_EVALUATED_BUDGET':'supplied_not_evaluated_budget'}
PLAN_FLAGS=dict(source_bytes_authenticated=False,execution_authorized=False,evaluation_called=False,point_in_time_verified=False,promotion_allowed=False)


def require(condition,message):
    if not condition:raise ValueError(message)


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def digest(value):return hashlib.sha256(encode(value)).hexdigest()


def integer(value):
    require(type(value)is int and value>=0,'Exact nonnegative integer')
    return value


def checked_plan(plan):
    require(type(plan)is dict and set(plan)=={'document','content_sha256'},'Original complete plan envelope')
    document=plan['document'];require(plan['content_sha256']==digest(document),'Plan content hash')
    keys={'schema','preparation_reference','prepared_content_sha256','scenario_count','pair_count',
          'financial_integer_count_before_issuer','structurally_excluded_integer_count','integer_count','batch_size','batch_count',*PLAN_FLAGS}
    require(set(document)==keys and document['schema']=='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_PLAN_V1','Exact plan shape')
    for key in ('scenario_count','pair_count','financial_integer_count_before_issuer','structurally_excluded_integer_count','integer_count','batch_size','batch_count'):integer(document[key])
    require(document['scenario_count']>0 and document['batch_size']in(512,10000),'Full scenarios and supported engineering batch size')
    require(document['financial_integer_count_before_issuer']==document['structurally_excluded_integer_count']+document['integer_count'],'Original issuer partition')
    require(document['batch_count']==(document['integer_count']+document['batch_size']-1)//document['batch_size'],'Exact batch count')
    for key,value in PLAN_FLAGS.items():require(document[key]is value,'False plan authority')
    for value in (document['content_sha256'] if 'content_sha256'in document else document['prepared_content_sha256'],document['preparation_reference']['sha256']):
        require(type(value)is str and len(value)==64 and set(value)<=set('0123456789abcdef'),'Bound declared SHA')
    require(set(document['preparation_reference'])=={'path','sha256'} and type(document['preparation_reference']['path'])is str and document['preparation_reference']['path'],'Preparation reference')
    return document


def expected_descriptor(plan,index):
    document=checked_plan(plan);integer(index);require(index<document['batch_count'],'Batch in complete original domain')
    start=index*document['batch_size'];stop=min(start+document['batch_size'],document['integer_count'])
    return dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_DESCRIPTOR_V1',plan_sha256=plan['content_sha256'],batch_index=index,start=start,stop=stop,point_count=stop-start)


def numeric_runs(descriptor,plans,saved_result,inspection):
    """Translate a independently accepted complete raw result, preserving order."""
    require(inspection['status']=='PASS_SAVED_RESULT_EVIDENCE','Independent arithmetic report')
    require(type(plans)is list and len(plans)==descriptor['point_count'],'Full batch tasks')
    require(len(saved_result['results'])==len(plans),'All original returned rows')
    require(inspection['supplied_plan_count']==len(plans),'Inspector full denominator')
    runs=[];stopped=False
    for index,(plan,row)in enumerate(zip(plans,saved_result['results'])):
        ordinal=descriptor['start']+index
        require(type(plan['global_ordinal'])is int and plan['global_ordinal']==ordinal,'Original global ordinal')
        require(type(row['supplied_index'])is int and row['supplied_index']==index,'Original supplied index')
        exact(row['plan'],plan,'Saved task identity')
        status=RAW_STATUS[row['status']]
        require(not stopped or status not in ('inspected_feasible','inspected_infeasible'),'No numerical row after stop')
        stopped=stopped or status not in ('inspected_feasible','inspected_infeasible')
        if runs and runs[-1]['status']==status:runs[-1]['stop']=ordinal+1
        else:runs.append(dict(start=ordinal,stop=ordinal+1,status=status))
    return runs


def partition(plan,verified_batch_outcomes):
    document=checked_plan(plan);counts=dict.fromkeys(STATUS_KEYS,0);end=0;stopped=False
    require(type(verified_batch_outcomes)is list,'Saved ordered batches')
    for index,item in enumerate(verified_batch_outcomes):
        require(not stopped and set(item)=={'descriptor','point_runs'},'No batch beyond technical stop')
        desc=expected_descriptor(plan,index);exact(item['descriptor'],desc,'Contiguous complete original batch')
        cursor=desc['start'];require(type(item['point_runs'])is list and item['point_runs'],'Explicit complete point runs')
        for run in item['point_runs']:
            require(set(run)=={'start','stop','status'} and run['status']in STATUS_KEYS,'Exact point partition role')
            start,stop=integer(run['start']),integer(run['stop'])
            require(start==cursor<stop<=desc['stop'],'No skipped, overlapping, reordered or missing ordinal')
            numeric=run['status']in ('inspected_feasible','inspected_infeasible')
            require(not stopped or not numeric,'No numeric classification after technical boundary')
            stopped=stopped or not numeric;counts[run['status']]+=stop-start;cursor=stop
        require(cursor==desc['stop'],'Complete last batch tail');end=cursor
    counts['undispatched']=document['integer_count']-end
    require(sum(counts.values())==document['integer_count'],'Complete original integer denominator')
    full=counts['inspected_feasible']+counts['inspected_infeasible']==document['integer_count']
    return dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_PARTITION_V1',plan_sha256=plan['content_sha256'],full_integer_count=document['integer_count'],counts=counts,undispatched_interval=dict(start=end,stop=document['integer_count']),full_domain_complete=full,status='COMPLETE_INSPECTED_DOMAIN'if full else'TECHNICAL_STOP'if stopped else'PREFIX_ONLY',counts_are_caller_supplied_not_authenticated=True,**PLAN_FLAGS)


def inspect_request_partition(*,plan,verified_batch_outcomes,saved_request):
    calculated=partition(plan,verified_batch_outcomes)
    exact(saved_request['plan'],plan,'Original plan')
    exact(saved_request['batch_outcomes'],verified_batch_outcomes,'Saved evidence outcomes')
    exact(saved_request['partition'],calculated,'Saved complete request partition')
    if calculated['full_domain_complete']:
        require(saved_request.get('stopped') is None,'Full domain cannot retain a technical stop')
    if any(calculated['counts'][key]for key in STATUS_KEYS if key not in ('inspected_feasible','inspected_infeasible')):
        require(type(saved_request.get('stopped'))is dict,'Technical partition requires its actual saved stop state')
    return dict(schema='DOUBLE_REPLACEMENT_REQUEST_PARTITION_INSPECTION_V1',status='PASS',
                full_integer_count=calculated['full_integer_count'],full_domain_complete=calculated['full_domain_complete'],
                counts=calculated['counts'],verified_batch_count=len(verified_batch_outcomes),
                worker_called=False,evaluator_called=False,source_bytes_authenticated=False)
