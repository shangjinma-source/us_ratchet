"""Full saved-task lineage checks and prespecified k/spec scalar sampling."""
import argparse
from collections import defaultdict
from copy import deepcopy
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_base_delta_probe_independent_audit as scalar


def audit_completed_date(index_path,index_sha256):
    sources={}
    def read(path,digest):
        path=Path(path).resolve();raw=path.read_bytes()
        if scalar.sha(raw)!=digest:raise ValueError('External artifact SHA mismatch: '+str(path))
        if str(path) in sources and sources[str(path)]!=digest:raise ValueError('Source collision')
        sources[str(path)]=digest;return json.loads(raw)
    index=read(index_path,index_sha256)
    manifest=read(index['manifest']['path'],index['manifest']['sha256'])
    tasks={r['new_job_id']:r for r in manifest['tasks']}
    final=index['finalization']
    if (index['status']!='COMPLETE' or final['status']!='COMPLETE' or
            len(tasks)!=len(manifest['tasks']) or len(index['completed'])!=len(tasks) or
            index['planned']!=len(tasks) or final['planned']!=len(tasks) or final['completed']!=len(tasks)):
        raise ValueError('Complete original date task denominator required')
    for evidence in (manifest,final):
        for path,digest in evidence['source_hashes'].items():
            if path in sources and sources[path]!=digest:raise ValueError('Source closure conflict')
            sources[path]=digest
    def verify():
        for path,digest in sources.items():
            if scalar.sha(Path(path).read_bytes())!=digest:raise ValueError('Source drift: '+path)
    verify()
    groups=defaultdict(list)
    for key,row in tasks.items():groups[(row['task']['holding_count'],row['task']['weight_spec'])].append(key)
    sample_ids={key for group in groups.values() for key in (min(group),max(group))}
    saved_samples={};observed=set();modes=defaultdict(int);reconstruction_max=0.
    for entry in index['completed']:
        value=read(entry['path'],entry['sha256']);identifier=value['new_job_id']
        if identifier not in tasks or identifier in observed:raise ValueError('Unknown/duplicate completed task')
        observed.add(identifier);row=tasks[identifier];result=value['result'];evaluation=result['evaluation'];task=row['task']
        original=read(row['checkpoint_path'],row['checkpoint_sha256'])
        if (original['task']!=task or original['context_sha256']!=manifest['context']['sha256']
                or original['status']!='EVALUATED'):
            raise ValueError('Original full task/context identity differs')
        if (value['manifest_sha256']!=index['manifest']['sha256'] or value['manifest_path']!=index['manifest']['path']
                or result['cache_checkpoint_sha256']!=row['checkpoint_sha256'] or value['promotion_allowed'] is not False
                or any(evaluation['result'][k]!=task[k] for k in ('tickers','holding_count','weight_spec'))):
            raise ValueError('Completed task/input/cache identity differs')
        for path,digest in result['source_hashes'].items():
            if sources.get(path)!=digest:raise ValueError('Task dependency absent from finalized date closure')
        error=result['original_metric_reconstruction_max_error']
        if type(error) not in (int,float) or not math.isfinite(error) or not 0<=error<=1e-12:
            raise ValueError('Declared original twenty-metric reconstruction failed')
        reconstruction_max=max(reconstruction_max,error)
        if task['holding_count']==1 and result['refitted_window_count']!=0:raise ValueError('K1 covariance refit')
        if len(result['window_cache_audit'])!=len(evaluation['historical_window_weights']):raise ValueError('Window trace denominator differs')
        modes[value['mode']]+=1
        if value['mode']=='EXTERNALLY_BOUND_COMPLETED_PROBE_IMPORTED_NO_FIT':
            probe=read(value['imported_probe_path'],value['imported_probe_sha256'])
            if probe['result']!=result:raise ValueError('Imported probe changed')
        elif value['mode']!='NEW_NUMERICAL_EVALUATION':raise ValueError('Unknown completed numerical mode')
        if identifier in sample_ids:saved_samples[identifier]=value
    if observed!=set(tasks):raise ValueError('Full task set differs')
    typed=read(manifest['typed_context']['path'],manifest['typed_context']['sha256'])
    inputs={key:scalar.decode(value['payload']) for key,value in typed['prepared_inputs'].items()}
    panel=inputs['returns'];calendar=panel['index'];oldreturns=dict(zip(panel['columns'],panel['column_values']));newreturns=deepcopy(oldreturns)
    for cell in manifest['corrections']:
        i=calendar.index(cell['session'])
        if oldreturns[cell['ticker']][i]!=cell['old']:raise ValueError('Original corrected cell differs')
        newreturns[cell['ticker']][i]=cell['new']
    samples=[];contract=inputs['contract'];fit=contract['fit_days']
    starts=list(range(fit,len(calendar)-contract['window_days']+1,contract['step_days']))
    for identifier in sorted(sample_ids):
        value=saved_samples[identifier];row=tasks[identifier];task=row['task']
        checkpoint=read(row['checkpoint_path'],row['checkpoint_sha256'])
        if checkpoint['task']!=task:raise ValueError('Sample original complete task differs')
        old=scalar.decode(checkpoint['result']);new=value['result']['evaluation'];variants=[]
        for label,returns,saved in [('original',oldreturns,old),('corrected',newreturns,new)]:
            windows,metrics=scalar.economics(returns,inputs['target_returns']['column_values'][0],inputs['incumbent_weights'],contract,saved['historical_window_weights'])
            error=max(abs(number-saved['result'][key]) for key,number in metrics.items())
            if error>1e-12:raise ValueError('Independent sampled scalar metrics differ')
            variants.append(dict(variant=label,metrics=metrics,max_error=error,windows=windows))
        prior_a=prior_b=None;anchored=task['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor';checked=[]
        for i,start in enumerate(starts):
            a,b=old['historical_window_weights'][i],new['historical_window_weights'][i]
            for record,prior in ((a,prior_a),(b,prior_b)):
                if (record['fit_start']!=calendar[start-fit] or record['fit_end']!=calendar[start-1]
                        or record['anchor_weights']!=(prior if anchored else None)):
                    raise ValueError('Sample anchor/history clock differs')
            history_equal=all(oldreturns[t][start-fit:start]==newreturns[t][start-fit:start] for t in task['tickers'].split(';'))
            hit=task['holding_count']==1 or history_equal and a['anchor_weights']==b['anchor_weights']
            observed_mode=value['result']['window_cache_audit'][i]
            if (observed_mode['mode']=='REUSED_EXACT_FITTER_INPUT')!=hit or (observed_mode['old_fitter_input_sha256']==observed_mode['new_fitter_input_sha256'])!=hit:
                raise ValueError('Sample cache mode/hash relation differs')
            if hit and a['weights']!=b['weights']:raise ValueError('Sample cached weights changed')
            checked.append(dict(ordinal=i,history_equal=history_equal,reused=hit));prior_a=a['weights'];prior_b=b['weights']
        samples.append(dict(new_job_id=identifier,task=task,variants=variants,window_mode_checks=checked))
    sources[str(Path(__file__).resolve())]=scalar.sha(Path(__file__).read_bytes())
    sources[str(Path(scalar.__file__).resolve())]=scalar.sha(Path(scalar.__file__).read_bytes())
    verify()
    return dict(schema='ndx_snapshot_completed_date_independent_audit_v1',source_hashes=sources,date=manifest['date'],
        complete_task_count=len(tasks),complete_task_lineage_verified=True,numerical_modes=dict(modes),
        all_tasks_declared_old_twenty_metric_max_error=reconstruction_max,
        all_tasks_old_metrics_independently_recomputed=False,sampling_rule='FIRST_AND_LAST_NEW_JOB_ID_PER_K_AND_WEIGHT_SPEC_NO_ECONOMIC_RANKING',
        sampled_task_count=len(samples),samples=samples,all_sampled_windows_independently_recomputed=True,
        no_fitter_or_evaluator_called=True,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--index-path',required=True);parser.add_argument('--index-sha256',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();report=audit_completed_date(args.index_path,args.index_sha256);output=Path(args.output)
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=scalar.sha(output.read_bytes()),date=report['date'],tasks=report['complete_task_count'],samples=report['sampled_task_count'])))
