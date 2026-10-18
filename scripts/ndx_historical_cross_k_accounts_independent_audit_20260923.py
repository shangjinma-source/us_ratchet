"""Source-bound saved account-prefix audit; no producer, runner, engine or fit calls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_historical_cross_k_account_independent_research as pure
from scripts import ndx_historical_cross_k_prefix_independent_audit_20260923 as prefix
from scripts import ndx_single_window_account_comparison_20260920 as shared
archive=prefix.archive;publish=prefix.publish
BASE=ROOT/'data/cache/research';PLAN=prefix.PLAN;INPUT=shared.INPUT
RUNNER=ROOT/'scripts/ndx_historical_cross_k_candidate_accounts_20260923.py'
RUNNER_SHA='80e8e1119d5153a563915f09c284c091329a322a8149a63a857609c7a3d22155'
BINDING=ROOT/'backtest/ndx_historical_cross_k_account_arguments_research.py'
BINDING_SHA='4df53abfe9e236a157fde6146a8b28036e41b8ee3b9e315354783ea99074db63'
PURE_SHA='aa177721eee55407922d8c62b46f1402f234ee4709d782a53ccf5f9edbe23bc8'
PREFIX_SHA='833bd9064e9384f67896b7cf78a7cadcb04db9dfe8a650854a3b5592c70f9244'
COMPARISON=dict(path=str(BASE/'historical_single_window_comparison_20260923_v1/comparison.json'),sha256='3723fa35291478f426d74b3b1226c92ad207b1d58be0dbca24fc577c8b158c6e')
EXTERNAL=dict(path=str(shared.ACCOUNT_BASE/'candidate/account.json'),sha256=shared.ACCOUNT_SHA['candidate'])
CONTROL=dict(path=str(shared.RECOVERY_PATH),sha256=shared.ACCOUNT_SHA['incumbent'])
FALSE=('fit_performed','result_imported','control_executed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','winner_selected','provider_identity_verified','corporate_action_completeness_verified')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(pure.__file__).resolve(),Path(prefix.__file__).resolve(),Path(shared.__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(publish.__code__.co_filename).resolve())}


def exact(a,b):return pure.exact(a,b)
def digest(v):return pure.digest(v)
def read(ref,sources):return prefix.read(ref,sources)


def independent_binding(inputs,task,result,numerical,detail):
    """Reconstruct the producer's declaration, without importing its binder."""
    checked,calendar,labels=pure.task_view(inputs,task,result,numerical,detail)
    failures=checked['risk_failures']
    value=dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_BINDING_V1',task_id=task['task_id'],task=task,fit_matrix_sha256=checked['fit_data_sha256'],independent_numerical_detail=checked,
        failed_original_risk_checks=failures,original_risk_parameters=task['parameters'],external_source_bytes_authenticated=False,execution_performed=False,fit_performed=False,result_reused=False,control_executed=False,
        order_acceptance_proven=False,all_ndx_legal_pool_verified=False,historical_identity_interval_verified=False,point_in_time_verified=False,promotion_allowed=False,winner_selected=False)
    if failures:return dict(value,status='NOT_EXECUTED_ORIGINAL_FIVE_RISK_FAILURE',account=None,normalization_evidence=None)
    schedule=[dict(decision_date=calendar[0],execution_date=calendar[1],targets=copy.deepcopy(result['targets']))]
    effective,evidence=pure.normalization.normalized_schedule(schedule)
    prices=pure.marks(inputs,calendar,labels);columns={s:'SID_'+s.upper().replace(':','_') for s in labels};translated=copy.deepcopy(schedule)
    for sid,r in translated[0]['targets'].items():r['ticker']=columns[sid]
    chains={calendar[0]:{s:labels[s]['risk_chain'] for s in labels}}
    frames={kind:dict(type='dataframe',index_type='DatetimeIndex',index=[d+'T00:00:00' for d in calendar],columns=[columns[s] for s in sorted(labels)],dtypes=['float64']*len(labels),data=[[prices[d][s][field] for s in sorted(labels)] for d in calendar]) for kind,field in (('opens','open'),('closes','close'))}
    arguments=dict(**frames,schedule=translated,risk_chains_by_decision=chains,corporate_actions=[],valuation_end_date=calendar[-1],**pure.CONTRACT,identity_events=[],max_repair_evaluations=262144)
    selected=dict(arguments=arguments,original_schedule=schedule,columns=columns,labels=labels,prices=prices,restore_actual_ticker_by_security={s:r['ticker'] for s,r in labels.items()},risk_is_order_gate=True,original_weights_normalized_by_assembler=False)
    account=dict(calendar=calendar,contract=pure.CONTRACT,selected=selected,effective_schedule=effective,scope='CONDITIONAL_HISTORICAL_CANDIDATE_NO_ORDER_ACCEPTANCE_CLAIM')
    return dict(value,status='READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT',account=account,normalization_evidence=evidence)


def inspect_entry(entry,documents,task,fit_result,detail,auth_ref,auth_sources,inputs,numerical,control_execution,nav_csv):
    prepared=independent_binding(inputs,task,fit_result,numerical,detail);identifier=task['task_id']
    if identifier==prefix.plan_reader.target_reader.JOB:raise ValueError('Existing historical account is external, never a new account entry')
    if entry['task_id']!=identifier:raise ValueError('Account entry task differs')
    saved=documents['result'];fitref=saved['fit_checkpoint_reference'];ready=prepared['account'] is not None
    marker=dict(schema='HISTORICAL_CROSS_K_ACCOUNT_ATTEMPT_V1',task_id=identifier,plan_reference=PLAN,fit_prefix_audit_reference=auth_ref,fit_checkpoint_reference=fitref,attempt_count=1,runtime=prefix.runtime())
    if not exact(documents['started'],marker):raise ValueError('Exact account attempt/runtime required')
    sources=dict(auth_sources);archive.merge(sources,{entry['started_reference']['path']:entry['started_reference']['sha256']})
    args=None;raw=None
    if ready:
        if entry['raw_reference'] is None or documents['raw'] is None:raise ValueError('Executed task needs preserved raw receipt')
        account=prepared['account'];selected=account['selected'];raw=documents['raw']['execution']
        expected_raw=dict(schema='HISTORICAL_CROSS_K_RAW_CANDIDATE_ACCOUNT_V1',task_id=identifier,plan_reference=PLAN,fit_prefix_audit_reference=auth_ref,fit_checkpoint_reference=fitref,
            started_reference=entry['started_reference'],parameter_digest=digest(prepared),execution=raw,original_schedule=selected['original_schedule'],internal_columns=selected['columns'],calendar=account['calendar'],contract=account['contract'],
            independent_accounting_completed=False,execution_performed=True,**dict.fromkeys(FALSE,False))
        if not exact(documents['raw'],expected_raw):raise ValueError('Whole raw account declaration differs')
        archive.merge(sources,{entry['raw_reference']['path']:entry['raw_reference']['sha256']})
        args=dict(calendar=account['calendar'],contract=account['contract'],schedule=selected['original_schedule'],effective_schedule=account['effective_schedule'],normalization_evidence=prepared['normalization_evidence'],internal_columns=selected['columns'])
    elif entry['raw_reference'] is not None or documents['raw'] is not None:raise ValueError('Skipped original risk failure must not have raw execution')
    report=pure.audit_candidate(inputs=inputs,task=task,result=fit_result,numerical_sources=numerical,audited_detail=detail,raw_execution=raw,execution=saved['execution'],
        effective_schedule=args['effective_schedule'] if args else None,normalization_evidence=prepared['normalization_evidence'],control_execution=control_execution,nav_csv=nav_csv)
    expected=dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_V1',task_id=identifier,plan_reference=PLAN,fit_prefix_audit_reference=auth_ref,fit_checkpoint_reference=fitref,
        started_reference=entry['started_reference'],raw_reference=entry['raw_reference'],parameter_digest=digest(prepared),status='ACCOUNT_EXECUTED_AND_INDEPENDENTLY_AUDITED' if ready else 'SKIPPED_RISK',
        failed_original_risk_checks=prepared['failed_original_risk_checks'],arguments=args,execution=saved['execution'],independent_decimal_accounting=report['candidate_accounting'],execution_performed=ready,
        historical_expected_source_hashes=sources,source_partition_verified_at_invocation_start=True,**dict.fromkeys(FALSE,False))
    if not exact(saved,expected):raise ValueError('Complete account checkpoint/scope/source differs')
    return dict(task_id=identifier,holding_count=task['holding_count'],weight_spec=task['weight_spec'],fit_checkpoint_reference=fitref,result_reference=entry['result_reference'],raw_reference=entry['raw_reference'],
        status=expected['status'],independent_result=report)


def runner_loaded_sources():
    sources={str(RUNNER):RUNNER_SHA,str(BINDING):BINDING_SHA,str(Path(prefix.__file__).resolve()):PREFIX_SHA,str(shared.OWNER):shared.OWNER_SHA}
    names=('ndx_conditional_single_window_account_arguments_research','ndx_dynamic_frozen_execution_research','ndx_dynamic_frozen_incumbent_control','ndx_frozen_accounting_independent_audit_research',
        'ndx_fixed_control_accounting_independent_audit_research','ndx_frozen_target_normalization_audit_research','ndx_dynamic_whole_lot_path','ndx_dynamic_whole_lot_repair_path','ndx_whole_lot_repair_diagnostic','ndx_split_accounting_research')
    for name in names:
        path=(ROOT/'backtest'/f'{name}.py').resolve();archive.merge(sources,{str(path):hashlib.sha256(path.read_bytes()).hexdigest()})
    reader=Path(shared.target_reader.__file__).resolve();archive.merge(sources,{str(reader):shared.TARGET_READER_SHA})
    archive.merge(sources,shared.target_reader.LOADED);archive.merge(sources,prefix.LOADED)
    return sources


def validate_index(index,queue,required):
    folder=Path(index['folder']);entries=index['entries']
    if not folder.is_absolute() or str(folder.resolve())!=index['folder'] or type(entries) is not list or len(entries)>len(queue) or [r['task_id'] for r in entries]!=[r['task_id'] for r in queue[:len(entries)]]:raise ValueError('Absolute exact account prefix required')
    for entry in entries:
        if set(entry)!={'task_id','started_reference','raw_reference','result_reference'}:raise ValueError('Exact account entry schema required')
        for key,name in (('started_reference','started.json'),('raw_reference','raw.json'),('result_reference','result.json')):
            ref=entry[key]
            if key=='raw_reference' and ref is None:continue
            if set(ref)!={'path','sha256'} or ref['path']!=str(folder/entry['task_id']/name):raise ValueError('Exact account artifact address required')
            archive.merge(required,{ref['path']:ref['sha256']})
    expected=dict(schema='HISTORICAL_CROSS_K_CANDIDATE_ACCOUNT_INDEX_V1',plan_reference=PLAN,fit_prefix_audit_reference=index['fit_prefix_audit_reference'],folder=str(folder),
        audited_fit_task_count=len(queue),completed_account_task_count=len(entries),pending_account_task_count=len(queue)-len(entries),entries=entries,finalized_after_full_source_verification=True,
        external_completed_account_reference=EXTERNAL,external_account_imported=False,historical_expected_source_hashes=index['historical_expected_source_hashes'],archive_resolution=index['archive_resolution'],**dict.fromkeys(FALSE,False))
    if not exact(index,expected):raise ValueError('Complete finalized account index/count/scope differs')
    declared=index['historical_expected_source_hashes']
    if any(declared.get(p)!=h for p,h in required.items()):raise ValueError('Index omitted invocation/receipt/external source')


def build(index_path,index_sha256,*,completed_prefix_confirmed=False):
    if completed_prefix_confirmed is not True:raise ValueError('Caller must confirm bounded account invocation completed')
    if RUNNER_SHA is None:raise ValueError('Await sealed account runner and actual external finalized index')
    if LOADED[str(Path(pure.__file__).resolve())]!=PURE_SHA or LOADED[str(Path(prefix.__file__).resolve())]!=PREFIX_SHA:raise ValueError('Sealed independent audit dependency differs')
    sources=dict(LOADED);reference=dict(path=str(Path(index_path).resolve()),sha256=index_sha256);index=read(reference,sources)
    comparison=read(COMPARISON,sources);shared.verify(comparison)
    control=read(CONTROL,sources)
    if comparison['account_references']['incumbent']!=CONTROL or comparison['account_references']['candidate']!=EXTERNAL:raise ValueError('Shared two-account comparison lineage differs')
    archive.merge(sources,comparison['historical_expected_source_hashes'])
    inputs=read(INPUT,sources);plan=read(PLAN,sources);numerical=plan['numerical_source_hashes'];tasks={r['task_id']:dict(r['task'],task_id=r['task_id']) for r in plan['tasks']}
    navref=comparison['nav_reference'];navbytes=Path(navref['path']).read_bytes()
    if hashlib.sha256(navbytes).hexdigest()!=navref['sha256']:raise ValueError('Hard shared original NAV changed')
    nav_csv=navbytes.decode('utf-8-sig');archive.merge(sources,{navref['path']:navref['sha256']})
    external_sources={};external=read(EXTERNAL,external_sources);target=read(shared.TARGET,external_sources);read(shared.TARGET_AUDIT,external_sources)
    for value in (external,target):archive.merge(external_sources,value['historical_expected_source_hashes'])
    for key in ('started_reference','raw_execution_reference'):read(external[key],external_sources)
    archive.merge(sources,external_sources)
    authorities={}
    def authority(ref):
        key=digest(ref)
        if key in authorities:return authorities[key]
        local=runner_loaded_sources();read(PLAN,local);read(INPUT,local);audit=read(ref,local)
        prefix.verify(audit)
        if audit['plan_reference']!=PLAN:raise ValueError('Historical fit audit plan differs')
        for value in (plan,inputs,audit):archive.merge(local,value['historical_expected_source_hashes'])
        fit_index=read(audit['index_reference'],local)
        if [r['task_id'] for r in fit_index['entries']]!=[d['task_id'] for d in audit['details']]:raise ValueError('Fit index and independent audit detail order differs')
        queue=[dict(task_id=e['task_id'],fit_checkpoint_reference=e['result_reference'],detail=d) for e,d in zip(fit_index['entries'],audit['details'],strict=True)]
        if any(r['task_id']==prefix.plan_reader.target_reader.JOB for r in queue):raise ValueError('External historical task cannot be newly executed')
        archive.merge(sources,local);authorities[key]=dict(reference=ref,queue=queue,sources=local);return authorities[key]
    current=authority(index['fit_prefix_audit_reference']);folder=Path(index['folder']);pending={reference['path']:reference['sha256']};seen={};edges={};all_required={}
    while pending:
        path,sha=pending.popitem()
        if path in seen:
            if seen[path]!=sha:raise ValueError('Conflicting account index lineage')
            continue
        value=index if path==reference['path'] else read(dict(path=path,sha256=sha),sources)
        if Path(path).parent!=folder or Path(path).name!='index_'+digest(value)+'.json':raise ValueError('Account index digest address differs')
        auth=authority(value['fit_prefix_audit_reference']);required=dict(auth['sources']);archive.merge(required,external_sources)
        if [r['task_id'] for r in auth['queue']]!=[r['task_id'] for r in current['queue'][:len(auth['queue'])]] or value['entries']!=index['entries'][:len(value['entries'])]:raise ValueError('Ancestor fit/account prefix does not extend monotonically')
        validate_index(value,auth['queue'],required);archive.merge(all_required,required);archive.merge(sources,value['historical_expected_source_hashes'])
        if any(index['historical_expected_source_hashes'].get(p)!=h for p,h in value['historical_expected_source_hashes'].items()):raise ValueError('Current index omitted ancestor source')
        ancestors={p:h for p,h in value['historical_expected_source_hashes'].items() if Path(p).parent==folder and Path(p).name.startswith('index_') and Path(p).suffix=='.json'}
        seen[path]=sha;edges[path]=tuple(ancestors)
        for p,h in ancestors.items():
            if (p in seen and seen[p]!=h) or (p in pending and pending[p]!=h):raise ValueError('Conflicting ancestor account index digest')
            if p not in seen:pending[p]=h
        del value
    done=set();active=set();todo=[(reference['path'],False)]
    while todo:
        p,finished=todo.pop()
        if finished:active.remove(p);done.add(p);continue
        if p in active:raise ValueError('Cyclic account index lineage')
        if p in done:continue
        active.add(p);todo.append((p,True));todo.extend((v,False) for v in edges[p])
    contract=archive.load_contract();archive.verify_expected_sources(sources,contract)
    results=[]
    for entry in index['entries']:
        documents={k:(read(entry[k+'_reference'],sources) if entry[k+'_reference'] is not None else None) for k in ('started','raw','result')}
        saved=documents['result'];auth=authority(saved['fit_prefix_audit_reference']);matches=[r for r in auth['queue'] if r['task_id']==entry['task_id']]
        if len(matches)!=1:raise ValueError('Account task absent from exact independently audited fit prefix')
        row=matches[0]
        if saved['fit_checkpoint_reference']!=row['fit_checkpoint_reference']:raise ValueError('Account references wrong completed fit')
        fit=read(row['fit_checkpoint_reference'],sources)
        if not exact(fit['task'],tasks[entry['task_id']]) or fit['fit_performed'] is not True:raise ValueError('Completed historical fit task differs')
        results.append(inspect_entry(entry,documents,tasks[entry['task_id']],fit['result'],row['detail'],auth['reference'],auth['sources'],inputs,numerical,control['execution'],nav_csv))
        archive.merge(all_required,auth['sources'])
    for p,h in seen.items():
        if p!=reference['path']:archive.merge(all_required,{p:h})
    if not exact(index['historical_expected_source_hashes'],all_required):raise ValueError('Final account index contains unaccounted or missing sources')
    for path,sha in seen.items():
        value=index if path==reference['path'] else read(dict(path=path,sha256=sha),sources)
        if not exact(value['archive_resolution'],prefix.partition_subset(value['historical_expected_source_hashes'],contract)):raise ValueError('Account index archive partition differs')
    return dict(schema='HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INDEPENDENT_AUDIT_V1',index_reference=reference,fit_prefix_audit_reference=index['fit_prefix_audit_reference'],plan_reference=PLAN,
        shared_control_reference=CONTROL,shared_comparison_reference=COMPARISON,external_completed_account_reference=EXTERNAL,external_account_imported=False,
        audited_fit_task_count=len(current['queue']),completed_account_task_count=len(results),pending_account_task_count=len(current['queue'])-len(results),
        skipped_risk_count=sum(r['status']=='SKIPPED_RISK' for r in results),executed_account_count=sum(r['status']!='SKIPPED_RISK' for r in results),details=results,
        prefix_confirmation='CALLER_OBSERVED_BOUNDED_RUN_EXIT_NOT_INDEPENDENT_PROCESS_ATTESTATION',raw_marker_result_chain_verified=True,write_order_independently_attested=False,
        producer_called=False,runner_called=False,engine_called=False,formal_dual_benchmark_admission=False,historical_expected_source_hashes=sources,
        archive_resolution=archive.verify_expected_sources(sources,contract),**dict.fromkeys(FALSE,False))


def verify(value):
    ref=value['index_reference']
    if not exact(value,build(ref['path'],ref['sha256'],completed_prefix_confirmed=True)):raise ValueError('Complete independent account prefix report differs')


def publish_verified(path,value):
    verify(value);saved=publish(path,value)
    if not exact(archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract()),value['archive_resolution']):raise ValueError('Source changed after publication')
    return saved


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--index',required=True);p.add_argument('--index-sha256',required=True);p.add_argument('--completed-prefix-confirmed',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(publish_verified(a.output,build(a.index,a.index_sha256,completed_prefix_confirmed=a.completed_prefix_confirmed))))
