"""Create-only, no-fit recovery for the exact 2444 paired-only saved tasks."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_saved_fractional_window_v2_research as recovery
from scripts import ndx_non_equal_base_runner as runner
from scripts.ndx_joint_weight_verify import _restore_input

SELF=Path(__file__).resolve(); LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()
PLAN=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/three_cell_saved_dependency_20260912.json'
PLAN_SHA='ae3fed1689457034fbe51227de1f9202a3b9602e6e0a95afa3657fdae2771da0'
ORIGINAL_CONTEXT_REVIEW=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json'
ORIGINAL_CONTEXT_REVIEW_SHA='a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'
OUTPUT=ROOT/'data/cache/research/non_equal_three_cell_recovery_20260912_fast_v3'
ERRORS=[dict(ticker='GOOG',session='2022-07-18',old=0.,new=-0.025335378898117544),
        dict(ticker='FTNT',session='2022-06-23',old=0.,new=0.019968386675822902),
        dict(ticker='GOOGL',session='2022-07-18',old=0.,new=-0.024580059928059006)]


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read(path,sha):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Hard-bound source differs')
    return json.loads(raw)


def merge(*maps):
    result={}
    for mapping in maps:
        for p,h in mapping.items():
            if p in result and result[p]!=h:raise ValueError('Source conflict')
            result[p]=h
    return result


def load_plan():
    plan=read(PLAN,PLAN_SHA)
    if plan['errors']!=ERRORS:raise ValueError('Exact evidence-backed correction values required')
    runner._verify_sources(plan['source_hashes'])
    if (plan['counts']['NON_EQUAL_BASE|PAIRED_ONLY_NO_REFIT']!=2444 or
        plan['counts']['NON_EQUAL_BASE|NO_DEPENDENCY']!=1526 or
        plan['counts']['NON_EQUAL_BASE|SELECTED_INPUT_CHANGED']!=15578):raise ValueError('Original exact denominator required')
    for key,rows in plan['buckets'].items():
        if digest(rows)!=plan['bucket_content_sha256'][key]:raise ValueError('Bucket content changed')
    return plan


def prepare_date(plan,date):
    if plan!=read(PLAN,PLAN_SHA):raise ValueError('Prepared plan differs from hard-bound classification')
    key=date+'|NON_EQUAL_BASE|PAIRED_ONLY_NO_REFIT'
    selected=plan['buckets'].get(key,[])
    if not selected:raise ValueError('Explicit nonempty paired-only date required')
    coordinate={k:selected[0]['task'][k] for k in ('source_batch','universe_track','selection_date')}
    prepared=runner.preparation.prepare_non_equal_base_date(**coordinate)
    path=Path(selected[0]['checkpoint_path']).parent/'context.json'
    checkpoint=read(selected[0]['checkpoint_path'],selected[0]['checkpoint_sha256'])
    context=read(path,checkpoint['context_sha256'])
    if context['training_semantics']!=prepared['training_semantics'] or context['tasks']!=prepared['tasks']:
        raise ValueError('Original whole prepared cohort differs')
    identifiers=[row['task']['job_id'] for row in selected]
    if len(set(identifiers))!=len(identifiers) or any(row['task'] not in context['tasks'] for row in selected):
        raise ValueError('Unique original tasks required')
    sources=merge(prepared['source_hashes'],context['source_hashes'],runner._LOADED,
        recovery.equivalence.previous.numerical_source_hashes('non_equal_fractional_v1'),
        {str(SELF):LOADED,str(recovery.SOURCE):recovery.LOADED,str(PLAN):PLAN_SHA,str(path):checkpoint['context_sha256']})
    for row in selected:sources[row['checkpoint_path']]=row['checkpoint_sha256']
    errors=plan['errors']
    if {(e['ticker'],e['session']) for e in errors}!={('GOOG','2022-07-18'),('GOOGL','2022-07-18'),('FTNT','2022-06-23')} or len(errors)!=3:
        raise ValueError('Exactly three evidenced cells required')
    updated=deepcopy(prepared['inputs'])
    for error in errors:
        if updated['returns'].loc[error['session'],error['ticker']]!=error['old']:
            raise ValueError('Original correction cell differs')
        updated['returns'].loc[error['session'],error['ticker']]=error['new']
    input_digest=lambda inputs:runner.encoding._sha({k:runner.encoding._panel_context(v) for k,v in inputs.items()})
    reviewed=read(ORIGINAL_CONTEXT_REVIEW,ORIGINAL_CONTEXT_REVIEW_SHA)
    location,=[row for row in reviewed['actual_window_error_locations'] if row['coordinate']==coordinate]
    expected_typed_context_sha=location['context_sha256']
    sources[str(ORIGINAL_CONTEXT_REVIEW)]=ORIGINAL_CONTEXT_REVIEW_SHA
    matching=[]
    for source,sha in context['source_hashes'].items():
        if Path(source).name=='context.json' and 'ndx_joint_weight_runs_v3' in source and sha==expected_typed_context_sha:
            candidate=read(source,sha)
            if 'prepared_inputs' in candidate:
                restored={k:_restore_input(v) for k,v in candidate['prepared_inputs'].items()}
                if input_digest(restored)==input_digest(prepared['inputs']):matching.append((source,sha))
    if len(matching)!=1:raise ValueError('Unique original typed context required')
    runner._verify_sources(sources)
    return dict(typed_context_reference=matching[0],inputs=prepared['inputs'],corrected_inputs=updated,selected=selected,context=context,
        original_context_path=str(path),original_context_sha256=checkpoint['context_sha256'],
        source_hashes=sources,coordinate=coordinate,errors=errors,bucket_sha256=plan['bucket_content_sha256'][key],
        reference_only=[r for k,rows in plan['buckets'].items() if k==date+'|NON_EQUAL_BASE|NO_DEPENDENCY' for r in rows],
        excluded_refit=[r for k,rows in plan['buckets'].items() if k==date+'|NON_EQUAL_BASE|SELECTED_INPUT_CHANGED' for r in rows])


def recover_task(prepared,row):
    if prepared['errors']!=ERRORS:raise ValueError('Prepared correction values changed')
    if row not in prepared['selected']:raise ValueError('Task outside exact paired-only bucket')
    task=row['task'];context=prepared['context'];sources=prepared['source_hashes']
    if read(prepared['original_context_path'],prepared['original_context_sha256'])!=context:
        raise ValueError('Prepared context mutated')
    source,sha=prepared['typed_context_reference']
    if context['source_hashes'].get(source)!=sha:
        raise ValueError('Typed context not in original closure')
    candidate=read(source,sha)
    restored={k:_restore_input(v) for k,v in candidate['prepared_inputs'].items()}
    input_digest=lambda inputs:runner.encoding._sha({k:runner.encoding._panel_context(v) for k,v in inputs.items()})
    if input_digest(restored)!=input_digest(prepared['inputs']):
        raise ValueError('Original typed inputs differ from bound context')
    corrected=deepcopy(prepared['inputs'])
    for error in prepared['errors']:
        corrected['returns'].loc[error['session'],error['ticker']]=error['new']
    if input_digest(corrected)!=input_digest(prepared['corrected_inputs']):raise ValueError('Unlisted corrected input change')
    read(row['checkpoint_path'],row['checkpoint_sha256'])
    checkpoint=runner._read(Path(row['checkpoint_path']))
    saved=runner._read_checkpoint(Path(row['checkpoint_path']),prepared['original_context_sha256'],task,context['numerical_sources'])
    task_sources=merge(recovery.equivalence.previous.numerical_source_hashes('non_equal_fractional_v1'),
        runner._LOADED,{str(SELF):LOADED,str(recovery.SOURCE):recovery.LOADED,
        prepared['original_context_path']:prepared['original_context_sha256'],source:sha,
        row['checkpoint_path']:row['checkpoint_sha256']})
    original=dict(task=task,inputs=prepared['inputs'],engine='non_equal_fractional_v1',runtime=context['runtime'],source_hashes=task_sources)
    changed=dict(original,inputs=prepared['corrected_inputs'])
    eq=recovery.equivalence.compare_candidate_numerical_inputs(left=original,right=changed)
    if eq['changed_dependency_fields']!=['incumbent_forward_returns']:
        raise ValueError('Selected complete fit/forward dependency changed')
    old=recovery.verify_original(arguments=original,saved=saved)
    new=recovery.recover(arguments=changed,saved=saved)
    for a,b in zip(old['windows'],new['windows']):
        if any(a[k]!=b[k] for k in a if not k.startswith('incumbent_')):
            raise ValueError('Candidate/target/fee exact sequence changed')
    allowed={'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
             'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent'}
    fields=[k for k in old['metrics'] if old['metrics'][k]!=new['metrics'][k]]
    if not set(fields)<=allowed:raise ValueError('Unexpected metric change')
    closure=merge(sources,old.pop('source_hashes'),new.pop('source_hashes'))
    runner._verify_sources(task_sources)
    return dict(task=task,original_checkpoint_path=row['checkpoint_path'],original_checkpoint_sha256=row['checkpoint_sha256'],
        original=old,corrected=new,changed_metrics=fields,
        original_max_absolute_error=max(abs(v-saved['result'][k]) for k,v in old['metrics'].items()),
        original_absolute_tolerance=recovery.TOLERANCE,source_hashes=closure,
        selected_fit_forward_inputs_exact=True,dependency_fields_changed=eq['changed_dependency_fields'],
        fitted=False,projection_called=False,whole_lot_called=False,promotion_allowed=False)


def publish(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    path=Path(path)
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('Existing immutable artifact differs')
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def validate_resume_checkpoint(value,expected):
    value=deepcopy(value)
    selfsha=value.pop('content_sha256')
    if digest(value)!=selfsha or value!=expected:
        raise ValueError('Existing checkpoint differs from source-bound no-fit reconstruction')


def run_date(plan,date,*,execute=False,probe=False,summary_sha256=None):
    summary_path=OUTPUT/date.replace('-','')/'summary.json'
    if execute and not probe and summary_path.exists():
        if summary_sha256 is None:raise ValueError('Completed summary requires known external SHA for read-only verification')
        return verify_completed(plan,date,summary_sha256)
    preparation_started=perf_counter()
    prepared=prepare_date(plan,date)
    preparation_seconds=perf_counter()-preparation_started
    if not execute:return dict(date=date,planned=len(prepared['selected']),training_performed=False)
    if probe:
        recovery_started=perf_counter()
        result=recover_task(prepared,prepared['selected'][0])
        recovery_seconds=perf_counter()-recovery_started
        result['measurement']=dict(preparation_seconds=preparation_seconds,recovery_seconds=recovery_seconds,
            timing_includes_original_twenty_metric_verification=True)
        path=OUTPUT/('final_probe_'+date.replace('-','')+'.json')
        if path.exists():raise FileExistsError('Probe already exists')
        sha=publish(path,result);runner._verify_sources(result['source_hashes'])
        return dict(path=str(path),sha256=sha,original_error=result['original_max_absolute_error'],
            windows=len(result['original']['windows']),task=result['task'],measurement=result['measurement'])
    # Persist shared source closure once per date, then compact per-task checkpoints.
    first=recover_task(prepared,prepared['selected'][0])
    closure=first['source_hashes']
    date_context=dict(schema='ndx_three_cell_no_fit_date_v2',coordinate=prepared['coordinate'],
        source_hashes=closure,errors=prepared['errors'],bucket_sha256=prepared['bucket_sha256'],
        selected=prepared['selected'],reference_only=prepared['reference_only'],excluded_refit=prepared['excluded_refit'],
        fitted=False,promotion_allowed=False)
    folder=OUTPUT/date.replace('-','');context_sha=publish(folder/'context.json',date_context)
    outputs=[]
    for i,row in enumerate(prepared['selected']):
        path=folder/(row['task']['job_id']+'.json')
        result=first if i==0 else recover_task(prepared,row)
        if result.pop('source_hashes')!=closure:raise ValueError('Task closure changed')
        expected=dict(schema='ndx_three_cell_no_fit_checkpoint_v2',context_sha256=context_sha,task=row['task'],
            result=result,status='RECOVERED_NO_FIT')
        if path.exists():
            validate_resume_checkpoint(json.loads(path.read_bytes()),expected)
        else:
            value=expected
            value['content_sha256']=digest(value);publish(path,value)
        outputs.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),job_id=row['task']['job_id']))
    if len(outputs)!=len(prepared['selected']) or len({r['job_id'] for r in outputs})!=len(outputs):raise ValueError('Date denominator differs')
    runner._verify_sources(closure)
    summary=dict(schema='ndx_three_cell_no_fit_date_summary_v2',context_sha256=context_sha,date=date,
        planned=len(prepared['selected']),completed=len(outputs),outputs=outputs,
        reference_only_count=len(prepared['reference_only']),excluded_refit_count=len(prepared['excluded_refit']),
        all_non_equal_training_complete=False,fitted=False,promotion_allowed=False)
    sha=publish(folder/'summary.json',summary);runner._verify_sources(closure)
    return dict(path=str(folder/'summary.json'),sha256=sha,completed=len(outputs))


def verify_completed(plan,date,summary_sha256):
    if plan!=read(PLAN,PLAN_SHA):raise ValueError('Original plan changed')
    folder=OUTPUT/date.replace('-','')
    summary=read(folder/'summary.json',summary_sha256)
    context=read(folder/'context.json',summary['context_sha256'])
    runner._verify_sources(context['source_hashes'])
    expected=plan['buckets'][date+'|NON_EQUAL_BASE|PAIRED_ONLY_NO_REFIT']
    if context['selected']!=expected or summary['planned']!=len(expected) or summary['completed']!=len(expected):
        raise ValueError('Completed summary denominator differs')
    if [r['job_id'] for r in summary['outputs']]!=[r['task']['job_id'] for r in expected]:
        raise ValueError('Completed summary exact task order differs')
    for output,row in zip(summary['outputs'],expected):
        if Path(output['path']).resolve()!=(folder/(row['task']['job_id']+'.json')).resolve():
            raise ValueError('Unexpected checkpoint path')
        value=read(output['path'],output['sha256']);selfsha=value.pop('content_sha256')
        result=value['result']
        if digest(value)!=selfsha or value['task']!=row['task'] or value['context_sha256']!=summary['context_sha256']:
            raise ValueError('Completed task binding differs')
        if (result['original_checkpoint_path']!=row['checkpoint_path'] or
            result['original_checkpoint_sha256']!=row['checkpoint_sha256'] or
            value['status']!='RECOVERED_NO_FIT'):
            raise ValueError('Original checkpoint lineage differs')
    runner._verify_sources(context['source_hashes'])
    return dict(path=str(folder/'summary.json'),sha256=summary_sha256,completed=len(expected),mode='READ_ONLY_VERIFIED')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--selection-date',required=True)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--probe',action='store_true')
    parser.add_argument('--summary-sha256')
    options=parser.parse_args()
    print(json.dumps(run_date(load_plan(),options.selection_date,execute=options.execute,probe=options.probe,summary_sha256=options.summary_sha256)))
