"""Copy audited path/risk evidence into display tables. No IO or aggregation."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib,json,math

MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
ROLES=('candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous')
FLAGS=dict.fromkeys(('source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','risk_chains_reaggregated','account_executed','winner_selected'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):require(enc(a)==enc(b),'Exact cross-source binding')
def sha(x):return hashlib.sha256(enc(x)).hexdigest()
def integer(n):require(type(n) is int and n>=0,'Nonnegative exact integer');return n

def display_number(value):
    if value is None:return dict(exact_value=None,display_value=None,display_status='MISSING_SAVED_VALUE')
    require(type(value) in (str,int,float,dict),'Saved numeric type, no bool')
    if type(value) is dict:
        require(set(value)=={'numerator','denominator'} and all(type(x) is str for x in value.values()),'Saved ratio')
        f=Fraction(int(value['numerator']),int(value['denominator']))
    else:
        require(type(value) is not float or math.isfinite(value),'Finite saved value');f=Fraction(str(value))
    try:n=float(f)
    except OverflowError:n=float('inf')
    status='FINITE_BINARY_FLOAT_DISPLAY'
    if not math.isfinite(n) or (n==0 and f!=0):n=None;status='OUTSIDE_DISPLAY_PRECISION'
    return dict(exact_value=deepcopy(value),display_value=n,display_status=status)

def ref(r):
    require(type(r) is dict and set(r)=={'path','sha256','json_pointer'},'Explicit path/SHA/pointer')
    require(type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Source reference')
    require(type(r['json_pointer']) is str and r['json_pointer'].startswith('/'),'Source pointer')

def project_task_display(path_row,chain_row,shared_paths,shared_chain_aggregates):
    require(path_row['schema']=='DATED_SAVED_PATH_RISK_DISPLAY_PROJECTION_V1' and chain_row['schema']=='SAVED_RISK_CHAIN_DISPLAY_AGGREGATES_V1','Saved projection schemas')
    tid=path_row['numerical_task_id'];exact(tid,chain_row['numerical_task_id'])
    cal=path_row['calendar'];exact(cal,chain_row['calendar'])
    require(type(cal) is list and len(cal)==127 and cal==sorted(set(cal)) and cal[:2]==['2026-03-20','2026-03-23'] and cal[-1]=='2026-09-21','Complete fixed calendar')
    for d in cal:require(date.fromisoformat(d).isoformat()==d,'Canonical date')
    for doc in (path_row,chain_row):
        for k in ('source_bytes_authenticated','economics_recomputed','point_in_time_verified','promotion_allowed','future_independent_oos'):require(doc[k] is False,'No authority upgrade')
        require(doc['evaluation_interval_previously_used_for_fitting'] is True,'Previously consumed historical window')
    require(path_row['formal_comparison_passed'] is False,'Formal comparison remains false')
    exact(path_row['preserved_evidence_sidecars'],chain_row['preserved_evidence_sidecars'])
    exact(path_row['input_limitations'],chain_row['limitations_preserved'])
    for k in ('risk_recomputed','chain_totals_computed','weights_normalized','account_executed','fit_performed','winner_selected'):require(path_row[k] is False,'Path authority')
    for k in ('risk_gate_recomputed','original_targets_changed'):require(chain_row[k] is False,'Chain authority')
    require(chain_row['chain_display_addition_performed'] is True,'Saved addition input')
    exact(path_row['original_provenance_and_missing'],chain_row['original_provenance_and_missing'])
    exact(path_row['original_task_summary_row'],chain_row['original_task_summary_row'])
    require(path_row['original_task_summary_row']['numerical_task_id']==tid,'Task summary identity')
    exact(path_row['input_references'],chain_row['input_references']);exact(path_row['input_references'],chain_row['projection_input_references'])
    exact(path_row['candidate_normalization_evidence'],chain_row['candidate_engine_normalization_evidence'])
    sources={};series={};risk={};resolved={}
    for role in (*ROLES,*MODES):
        container=path_row['tracks'] if role in ROLES else path_row['nav_modes'];payload=container[role]
        if role.startswith('incumbent') or role in MODES:
            require(set(payload)=={'shared_path_id','value_encoding_preserved'},'Shared link shape')
            key=payload['shared_path_id'];item=shared_paths[key];identity=item['identity']
            require(identity['role']==role and sha(identity)==key,'Shared role and identity hash');payload=item['payload'];exact(identity['source_reference'],payload['source_reference'])
        resolved[role]=payload
        if role in ROLES:
            status=payload['status']
            if status!='AVAILABLE':
                require(role=='candidate_integer' and status in ('NOT_EXECUTED_NONPOSITIVE_TARGET','TECHNICAL_MISSING') and payload['path'] is None,'Explicit missing integer only')
                exact(payload['calendar_slots'],[dict(session=d,value=None) for d in cal]);values=[None]*127;source=None
            else:
                require([r['session'] for r in payload['path']]==cal,'Full source path');values=payload['saved_normalized_values_exact'];source=payload['source_reference'];ref(source)
                exact(values,payload['metrics']['normalized_values_exact'])
        else:
            require(payload['mode']==role and [r['session'] for r in payload['observations']]==cal,'Mode and observation calendar')
            source=payload['source_reference'];ref(source);values=[r['normalized_value_exact'] for r in payload['observations']]
            if payload['metrics'] is not None:exact(values,payload['metrics']['normalized_values_exact'])
            status='SAVED_NAV_REFERENCE'
        require(type(values) is list and len(values)==127,'Full normalized slots')
        if source is not None:
            require(all(r['path']!=source['path'] or r['sha256']==source['sha256'] for r in sources.values()),'Conflicting source hashes')
            sources[role]=deepcopy(source)
        series[role]=dict(status=status,source_reference=deepcopy(source),slots=[dict(session=d,**display_number(v)) for d,v in zip(cal,values)],missing_evidence=deepcopy(payload.get('missing_evidence')),transformation='COPY_SAVED_NORMALIZED_VALUES_NO_RETURN_RECALCULATION')
    for role in ROLES:
        aggregate=chain_row['tracks'][role]
        if role.startswith('incumbent'):
            require(set(aggregate)=={'shared_aggregate_id'},'Shared aggregate link')
            key=aggregate['shared_aggregate_id'];exact(key,path_row['tracks'][role]['shared_path_id'])
            item=shared_chain_aggregates[key];exact(item['identity'],shared_paths[key]['identity']);aggregate=item['aggregation']
        exact(aggregate['status'],resolved[role]['status'])
        if aggregate['status']=='AVAILABLE':
            require([r['session'] for r in aggregate['rows']]==cal,'All risk dates');exact(aggregate['source_reference'],sources[role])
        else:require(aggregate['rows'] is None,'Missing risk cannot become cash')
        risk[role]=deepcopy(aggregate)
    for role in ('candidate','incumbent'):exact(chain_row['targets'][role]['source_evidence'],path_row['target_evidence'][role])
    return dict(schema='DATED_WORKBOOK_TASK_EXTENSION_TABLES_V1',numerical_task_id=tid,calendar=deepcopy(cal),original_task_summary_row=deepcopy(path_row['original_task_summary_row']),series=series,risk_tracks=risk,original_target_chain_evidence=deepcopy(chain_row['targets']),engine_normalization_evidence=deepcopy(path_row['candidate_normalization_evidence']),original_target_evidence=deepcopy(path_row['target_evidence']),source_index=sources,input_references=deepcopy(path_row['input_references']),original_provenance_and_missing=deepcopy(path_row['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(path_row['preserved_evidence_sidecars']),evaluation_interval_previously_used_for_fitting=True,risk_copy_semantics='ALL_SAVED_GROUPS_RAW_TARGET_ENGINE_AND_ACTUAL_KEPT_SEPARATE_NO_AGGREGATION',**FLAGS)

def project_classification(coverage):
    require(coverage['schema']=='SAVED_CONDITIONAL_CLASSIFICATION_COVERAGE_V1','Classification schema')
    for k in ('point_in_time_verified','source_bytes_authenticated','formal_classification_verified','historical_pool_eligibility_verified','legal_training_input_admitted','execution_authorized','promotion_allowed','fit_performed','risk_reclassified','future_independent_oos'):require(coverage[k] is False,'Conditional classification')
    rows=coverage['rows'];require(type(rows) is list and len(rows)==101 and len({r['ticker'] for r in rows})==101,'Full 101 unique rows')
    for r in rows:
        require(type(r['conditional_label_present']) is bool and type(r['training_selected']) is bool and r['formally_verified'] is False,'Exact row classification flags')
        ref(r['wiring_row_reference']);ref(r['training_provenance_reference'])
    coordinates=[r['security_id'] for r in rows if r['security_id'] is not None]
    selected=[r for r in rows if r['training_selected']]
    require(all(type(s) is str and s for s in coordinates) and len(coordinates)==len(set(coordinates)),'Unique complete coordinate SIDs')
    require(len({r['security_id'] for r in selected})==77 and len({r['issuer_id'] for r in selected})==76,'Unique selected SID and issuer denominator')
    require(type(coverage['counts']['coordinate_security_count']) is int and coverage['counts']['coordinate_security_count']==len(coordinates),'Coordinate count')
    require(type(coverage['counts']['coordinate_issuer_count']) is int and coverage['counts']['coordinate_issuer_count']==len({r['issuer_id'] for r in rows if r['security_id'] is not None}),'Coordinate issuer count')
    for row in rows:
        label=row['saved_risk_chain'];known=label is not None and label!='unclassified'
        require(type(label) is str or label is None,'Saved label type')
        require(row['conditional_label_present'] is known,'Actual saved label and presence agree')
        if row['training_selected']:require(known and type(row['security_id']) is str and bool(row['security_id']) and type(row['issuer_id']) is str and bool(row['issuer_id']),'Selected known coordinates')
    observed=dict(observed_security_rows=101,conditional_labeled_security_count=sum(r['conditional_label_present'] for r in rows),unknown_label_rows=sum(not r['conditional_label_present'] for r in rows),training_selected_security_count=sum(r['training_selected'] for r in rows),training_selected_issuer_count=len({r['issuer_id'] for r in rows if r['training_selected']}),formally_verified_rows=0)
    exact(observed,dict(observed_security_rows=101,conditional_labeled_security_count=78,unknown_label_rows=23,training_selected_security_count=77,training_selected_issuer_count=76,formally_verified_rows=0))
    for k,v in observed.items():require(type(coverage['counts'][k]) is int and coverage['counts'][k]==v,'Declared classification counts')
    return dict(schema='DATED_WORKBOOK_CLASSIFICATION_TABLE_V1',rows=deepcopy(rows),counts=deepcopy(coverage['counts']),issuer_label_reviews=deepcopy(coverage['issuer_label_reviews']),source_index=deepcopy(coverage['input_references']),saved_wiring_scope=deepcopy(coverage['saved_wiring_scope']),saved_training_scope=deepcopy(coverage['saved_training_scope']),**FLAGS)

def plan_display_packages(task_descriptors,limits=None,*,expected_task_ids):
    require(type(expected_task_ids) is list and len(expected_task_ids)==len(set(expected_task_ids)),'Explicit complete original task index')
    limits=dict(max_rows_per_sheet=100000,max_rows_per_package=250000,max_estimated_bytes_per_package=50*1024*1024) if limits is None else limits
    require(set(limits)=={'max_rows_per_sheet','max_rows_per_package','max_estimated_bytes_per_package'},'Explicit engineering limits')
    for n in limits.values():require(integer(n)>0,'Positive capacity')
    packages=[];seen=set();current=None
    for ordinal,d in enumerate(task_descriptors):
        require(integer(d['task_ordinal'])==ordinal,'Full original order; no omission')
        tid=d['numerical_task_id'];require(ordinal<len(expected_task_ids) and tid==expected_task_ids[ordinal],'Original external index order');require(type(tid) is str and len(tid)==64 and all(c in '0123456789abcdef' for c in tid) and tid not in seen,'Unique exact task ID');seen.add(tid)
        rows=integer(d['data_row_count']);size=integer(d['estimated_bytes'])
        require(rows<=limits['max_rows_per_package'] and size<=limits['max_estimated_bytes_per_package'],'BLOCKED_DELIVERY_LAYOUT_LIMIT single task')
        if current is None or current['data_row_count']+rows>limits['max_rows_per_package'] or current['estimated_bytes']+size>limits['max_estimated_bytes_per_package']:
            current=dict(package_index=len(packages),start_task_ordinal=ordinal,stop_task_ordinal=ordinal,data_row_count=0,estimated_bytes=0,tasks=[]);packages.append(current)
        current['tasks'].append(deepcopy(d));current['stop_task_ordinal']=ordinal+1;current['data_row_count']+=rows;current['estimated_bytes']+=size
    require(len(seen)==len(expected_task_ids),'Incomplete task descriptors; no truncated success')
    for p in packages:p['data_page_row_counts']=[min(limits['max_rows_per_sheet'],p['data_row_count']-i) for i in range(0,p['data_row_count'],limits['max_rows_per_sheet'])]
    return dict(schema='DATED_WORKBOOK_EXTENSION_PACKAGE_PLAN_V1',packages=packages,task_count=len(seen),limits=deepcopy(limits),counts_are_engineering_not_pool_limits=True,exported_byte_limit_verified=False,unprocessed_task_count=0,**FLAGS)
