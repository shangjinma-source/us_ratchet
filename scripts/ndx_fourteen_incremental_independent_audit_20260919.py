"""Independent completed-new-prefix readback; old 764 remain audited references."""
import argparse,hashlib,json,sys,itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_latest_all_k_completed_independent_audit_20260919 as scalar
archive=scalar.archive;BASE=scalar.BASE
PLAN=BASE/'latest_fourteen_incremental_refit_20260919_v1/plan.json'
PLAN_SHA='b604b6f5ca1385c83d4fea3fb930b0ddc6e3a1bb30eeab665261f4b53ed5b563'
RUNNER=ROOT/'scripts/ndx_fourteen_incremental_bounded_refit_20260919.py'
RUNNER_SHA='e774eca2fa9ada9276330493e8bfa7df9a8a44971626536b32171442cb9a2670'
PRODUCER=ROOT/'scripts/ndx_latest_fourteen_incremental_plan_20260919.py'
PRODUCER_SHA='ff789ced2e2892b12d8cf9fc5bbda640a8afce748381c6c427c9b424c2c8756b'
FALSE=scalar.FALSE
SCHEMA='FOURTEEN_INCREMENTAL_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1'
LOADED=dict(scalar.LOADED)
LOADED[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
RESULT_KEYS={'schema','weight_spec','cutoff','fit_start','fit_end','fit_row_count','fit_data_sha256','targets','risk_chains_by_security','previous_target_weights','surviving_anchor_mass','anchor_by_security','effective_anchor_strength','anchor_policy','declared_parameters','declared_constraint_checks','declared_constraints_passed','risk_chain_projection_relaxed','single_name_projection_relaxed','top3_projection_semantics_relaxed','checkpoint_weights_used','point_in_time_verified','source_authenticity_verified','promotion_allowed','source_hashes','numerical_projection','projection_reconstruction_audit','historical_task_evaluation_performed','order_generation_allowed'}


def result_schema(result,task):
    if set(result)!=RESULT_KEYS or result['anchor_policy']!='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED' or result['numerical_projection']!='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE':raise ValueError('Complete original numerical result schema required')
    names=('risk_chain_projection_relaxed','single_name_projection_relaxed','top3_projection_semantics_relaxed')
    if any(type(result[k]) is not bool for k in names):raise ValueError('Explicit boolean projection diagnostics required')
    k=len(task['selected']);non_equal=task['weight_spec']!='equal_weight';p=task['parameters']
    if result['single_name_projection_relaxed'] is not (non_equal and p['max_single_weight']<1./k) or result['top3_projection_semantics_relaxed'] is not (non_equal and (k<=3 or p['top_weight_cap']<min(3,k-1)/k)):raise ValueError('Original cardinality projection flags differ')
    audit=result['projection_reconstruction_audit']
    if set(audit)!={'schema','scope','attempt_count','attempts','prior_results_reused','promotion_allowed'} or audit['scope']!='NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION':raise ValueError('Complete projection reconstruction disclosure required')


def tasks_from_plan(plan):
    rows=plan['delta']['tasks'];new=[];old=[];seen=set()
    if len(rows)!=31828:raise ValueError('Complete 31828 task denominator required')
    for row in rows:
        task=dict(row['task'],task_id=row['task_id'])
        if task['task_id']!=scalar.digest(row['task']) or task['task_id'] in seen or row['result_reused'] is not False:raise ValueError('Unique unimported tasks required')
        seen.add(task['task_id'])
        if row['input_equivalent_to_old_task'] is True:
            if row['old_equivalent_task_id']!=task['task_id'] or row['completed_old_result_verified'] is not True or row['status']!='OLD_INPUT_EQUIVALENT_RESULT_REFERENCE_VERIFIED_NOT_IMPORTED' or not row['completed_old_result_reference']:raise ValueError('Exact old reference required')
            old.append(row)
        else:
            if row['input_equivalent_to_old_task'] is not False or row['completed_old_result_verified'] is not False or row['completed_old_result_reference'] is not None or row['old_equivalent_task_id'] is not None or row['status']!='PENDING_OLD_OR_NEW':raise ValueError('Exact new input required')
            new.append(task)
    if len(old)!=764 or len(new)!=31064:raise ValueError('764 old references and 31064 new inputs required')
    return sorted(new,key=lambda t:t['task_id']),old


def inspect_plan(plan,panel,old_panel):
    """Independent hard-envelope combination and SID/risk proof, no producer code."""
    def universe(document,count):
        frame=document['universe'];rows=[dict(zip(frame['columns'],r)) for r in frame['data']]
        mapping={r['security_id']:r for r in rows}
        if len(rows)!=count or len(mapping)!=count or len({r['issuer_id'] for r in rows})!=count or len({r['ticker'] for r in rows})!=count:
            raise ValueError('Actual unique security/issuer/ticker denominator differs')
        return mapping
    by_sid=universe(panel,14);old_sid=universe(old_panel,9)
    if not set(old_sid)<=set(by_sid):raise ValueError('Original nine securities not retained')
    if any(not scalar.exact(row,by_sid[sid]) for sid,row in old_sid.items()):raise ValueError('Original nine universe metadata changed')
    if panel['cutoff']!='2026-09-17' or old_panel['cutoff']!=panel['cutoff']:raise ValueError('Same latest cutoff required')
    expected=set();old_expected=set()
    # At the fixed original Top3 .8 envelope, k<=3 necessarily totals 1>.8.
    # k4..14 satisfy cardinality-only min/max/effective-N necessary conditions;
    # chain and fitted-weight feasibility remains a numerical diagnostic.
    for k in range(4,15):
        for group in itertools.combinations(sorted(by_sid),k):
            for spec in ('equal_weight','constrained_fixed_shrinkage'):
                key=(group,spec);expected.add(key)
                if set(group)<=set(old_sid):old_expected.add(key)
    new,old=tasks_from_plan(plan);observed=set();observed_old=set()
    for row in plan['delta']['tasks']:
        task=row['task'];selected=task['selected'];sids=tuple(sorted(selected))
        if not scalar.exact(task['parameters'],scalar.PARAMS) or task['previous_target_weights'] is not None or task['cutoff']!=panel['cutoff'] or type(task['holding_count']) is not int or task['holding_count']!=len(sids):raise ValueError('Original task parameters/prior/date differ')
        for sid,identity in selected.items():
            if sid not in by_sid or not scalar.exact(identity,{k:by_sid[sid][k] for k in ('ticker','issuer_id','risk_chain')}):raise ValueError('Task selected coordinates differ from actual panel')
        key=(sids,task['weight_spec'])
        if key in observed:raise ValueError('Duplicate combination/spec')
        observed.add(key)
        if row['input_equivalent_to_old_task'] is True:observed_old.add(key)
    if observed!=expected or observed_old!=old_expected or len(old_expected)!=764 or len(expected)!=31828:raise ValueError('Complete actual 14/9 combination/spec partitions differ')
    return new,old


def validate_index(index,tasks):
    entries=index['entries'];count=len(entries);folder=Path(index['output_directory']).resolve()
    expected=dict(schema='FOURTEEN_INCREMENTAL_BOUNDED_INDEX_V1',plan_reference=dict(path=str(PLAN),sha256=PLAN_SHA),output_directory=str(folder),
        original_reference_count=764,new_input_planned=31064,new_input_completed=count,new_input_pending=31064-count,
        status='COMPLETE' if count==31064 else 'PARTIAL',finalized_after_full_source_verification=True,entries=entries,old_results_imported=0,**dict.fromkeys(FALSE,False))
    if not scalar.exact(index,expected) or not 0<=count<=31064 or [e['task_id'] for e in entries]!=[t['task_id'] for t in tasks[:count]]:raise ValueError('Exact finalized new-task prefix required')
    return folder


def build(index_path,index_sha256,*,completed_prefix_confirmed=False):
    if PLAN_SHA is None or RUNNER_SHA is None or completed_prefix_confirmed is not True:raise ValueError('Sealed plan/runner and confirmed completed run required')
    sources=dict(LOADED);planref=dict(path=str(PLAN),sha256=PLAN_SHA)
    plan=scalar.read(planref,sources)
    archive.merge(sources,plan['historical_expected_source_hashes'])
    paneldoc=scalar.read(plan['new_panel_reference'],sources);panel=paneldoc['panel']
    olddoc=scalar.read(plan['old_panel_reference'],sources)
    tasks,old=inspect_plan(plan,panel,olddoc['panel'])
    indexref=dict(path=str(Path(index_path).resolve()),sha256=index_sha256);index=scalar.read(indexref,sources);folder=validate_index(index,tasks)
    numerical=scalar.numerical_sources._sources()
    # Reconstruct the runner's prepare source map without importing its code.
    task_sources={str(RUNNER):RUNNER_SHA,str(PRODUCER):PRODUCER_SHA,str(scalar.OWNER):scalar.OWNER_SHA,str(PLAN):PLAN_SHA}
    archive.merge(task_sources,plan['historical_expected_source_hashes'])
    archive.merge(task_sources,{plan['new_panel_reference']['path']:plan['new_panel_reference']['sha256']});archive.merge(task_sources,numerical)
    archive.merge(sources,task_sources);contract=archive.load_contract();archive.verify_expected_sources(sources,contract)
    details=[]
    for entry,task in zip(index['entries'],tasks):
        path=folder/(task['task_id']+'.json');marker=Path(str(path)+'.started.json')
        if set(entry)!={'task_id','path','sha256','started_sha256'} or entry['path']!=str(path):raise ValueError('Exact checkpoint address required')
        value=scalar.read(dict(path=str(path),sha256=entry['sha256']),sources)
        attempt=scalar.read(dict(path=str(marker),sha256=entry['started_sha256']),sources)
        if not scalar.exact(attempt,dict(schema='FOURTEEN_INCREMENTAL_SINGLE_ATTEMPT_V1',plan_reference=planref,task_id=task['task_id'],attempt_count=1)):raise ValueError('Exact exclusive attempt required')
        keys={'schema','plan_reference','task','result','attempt_count','old_results_imported','status','historical_expected_source_hashes','archive_resolution'}|set(FALSE)
        if set(value)!=keys or value['schema']!='FOURTEEN_INCREMENTAL_SINGLE_REFIT_V1' or not scalar.exact(value['task'],task) or not scalar.exact(value['plan_reference'],planref) or type(value['attempt_count']) is not int or value['attempt_count']!=1 or type(value['old_results_imported']) is not int or value['old_results_imported']!=0 or any(value[k] is not False for k in FALSE):raise ValueError('Checkpoint scope/identity differs')
        expected=dict(task_sources);archive.merge(expected,{str(marker):entry['started_sha256']})
        if not scalar.exact(value['historical_expected_source_hashes'],expected) or not scalar.exact(value['archive_resolution'],scalar.declared_partition(expected,contract)):raise ValueError('Complete task source partition differs')
        if not scalar.exact(value['result']['source_hashes'],numerical):raise ValueError('Frozen numerical sources differ')
        result_schema(value['result'],task)
        detail=scalar.inspect_result(value['result'],task,panel)
        if value['status']!=('FITTED_ORIGINAL_FIVE_RISKS_PASSED' if detail['risk_pass'] else 'FITTED_ORIGINAL_FIVE_RISKS_FAILED'):raise ValueError('Saved risk verdict differs')
        detail['checkpoint_reference']=dict(path=str(path),sha256=entry['sha256']);details.append(detail)
        archive.merge(sources,expected)
    return dict(schema=SCHEMA,plan_reference=planref,index_reference=indexref,total_canonical=31828,old_references=764,new_planned=31064,new_completed=len(details),new_pending=31064-len(details),
        old_result_imported_count=0,old_result_numerical_audit_repeated=False,old_independent_audit_reference=plan['old_independent_audit_reference'],
        details=details,risk_pass_count=sum(d['risk_pass'] for d in details),risk_fail_count=sum(not d['risk_pass'] for d in details),
        all_completed_126_matrices_and_decimal_risks_verified=True,solver_called=False,owner_check_result_called=False,constrained_projection_optimality_independently_verified=False,risk_chain_projection_metadata_independently_recomputed=False,
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()),**dict.fromkeys(FALSE,False))


def verify(value):
    if value.get('schema')!=SCHEMA or any(value.get(k) is not False for k in (*FALSE,'old_result_numerical_audit_repeated','solver_called','owner_check_result_called','constrained_projection_optimality_independently_verified','risk_chain_projection_metadata_independently_recomputed')):raise ValueError('Independent audit scope differs')
    ref=value['index_reference'];expected=build(ref['path'],ref['sha256'],completed_prefix_confirmed=True)
    if not scalar.exact(value,expected):raise ValueError('Entire independent audit does not reproduce')


def publish_verified(path,value):
    verify(value);saved=scalar.exclusive_publish(path,value)
    if not scalar.exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Sources changed after publication')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--index',required=True);parser.add_argument('--index-sha256',required=True);parser.add_argument('--completed-prefix-confirmed',action='store_true');parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(publish_verified(args.output,build(args.index,args.index_sha256,completed_prefix_confirmed=args.completed_prefix_confirmed))))
