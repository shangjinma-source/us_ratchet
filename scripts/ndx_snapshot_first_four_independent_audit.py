"""Read actual first four snapshot records; scalar arithmetic only, no fitting."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_base_delta_probe_independent_audit as scalar


def main():
    folder=ROOT/'data/cache/research/base_window_snapshot_20260912_v1/20230403';sources={}
    def read(path,expected):
        path=Path(path).resolve();raw=path.read_bytes()
        if scalar.sha(raw)!=expected:raise ValueError('External SHA mismatch')
        sources[str(path)]=expected;return json.loads(raw)
    prior=read(folder/'index_466fb38db8e3edd9cbc230ce4bb402eb96136080cca82d5bf52b3e05c3678f4a.json','eecaa49837eba27d62b3f2c57bcfd5686577f5c6f5d643f837e24b3ab314b239')
    index=read(folder/'index_21ac8a6fb782b9db02caf48c74c044959b503a5f51eaec6cda71666654077bfc.json','6fee444971ce679c701d6a2173ccc1db13c09e3726c781f6360f9eb90f97d27b')
    if len(prior['completed'])!=3 or len(index['completed'])!=4 or index['planned']!=966 or index['status']!='PARTIAL':
        raise ValueError('Actual three imported plus one new denominator differs')
    if any(row not in index['completed'] for row in prior['completed']):raise ValueError('Imported checkpoint changed')
    manifest=read(index['manifest']['path'],index['manifest']['sha256'])
    if index['manifest']!=prior['manifest']:raise ValueError('Manifest changed across resumes')
    for evidence in (prior['finalization'],index['finalization'],manifest):
        for path,digest in evidence['source_hashes'].items():
            if path in sources and sources[path]!=digest:raise ValueError('Source conflict')
            sources[path]=digest
    tasks={row['new_job_id']:row for row in manifest['tasks']};imports=[];new_records=[]
    for entry in index['completed']:
        row=read(entry['path'],entry['sha256'])
        if row['manifest_sha256']!=index['manifest']['sha256'] or row['new_job_id'] not in tasks:raise ValueError('Task lineage differs')
        if row['mode']=='EXTERNALLY_BOUND_COMPLETED_PROBE_IMPORTED_NO_FIT':
            probe=read(row['imported_probe_path'],row['imported_probe_sha256'])
            if row['result']!=probe['result'] or row['new_job_id']!=probe['selected']['new_job_id']:raise ValueError('Imported result not exact')
            imports.append(row['new_job_id'])
        elif row['mode']=='NEW_NUMERICAL_EVALUATION':new_records.append(row)
        else:raise ValueError('Unknown task mode')
    if len(imports)!=3 or len(new_records)!=1:raise ValueError('Unexpected new evaluations')
    row=new_records[0];taskrow=tasks[row['new_job_id']];task=taskrow['task']
    if row['new_job_id']!='ff60642387d23b9c7690041d9391950ada51449855cfb2642094dc06687f0f49':raise ValueError('Different first new task')
    typed=read(manifest['typed_context']['path'],manifest['typed_context']['sha256'])
    inputs={key:scalar.decode(value['payload']) for key,value in typed['prepared_inputs'].items()}
    panel=inputs['returns'];returns=dict(zip(panel['columns'],panel['column_values']));calendar=panel['index'];changed=deepcopy(returns)
    for error in manifest['corrections']:
        i=calendar.index(error['session'])
        if returns[error['ticker']][i]!=error['old']:raise ValueError('Original correction cell differs')
        changed[error['ticker']][i]=error['new']
    original=read(taskrow['checkpoint_path'],taskrow['checkpoint_sha256'])
    if original['task']!=task:raise ValueError('Original task identity differs')
    old=scalar.decode(original['result']);new=row['result']['evaluation'];contract=inputs['contract']
    variants=[]
    for label,values,saved in [('old',returns,old),('new',changed,new)]:
        windows,metrics=scalar.economics(values,inputs['target_returns']['column_values'][0],inputs['incumbent_weights'],contract,saved['historical_window_weights'])
        errors={key:abs(value-saved['result'][key]) for key,value in metrics.items()}
        if max(errors.values())>1e-12:raise ValueError('Saved scalar economics differ')
        variants.append(dict(variant=label,windows=windows,metrics=metrics,max_absolute_error=max(errors.values())))
    anchored=task['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor';prior_old=prior_new=None;checks=[]
    fit=contract['fit_days'];starts=list(range(fit,len(calendar)-contract['window_days']+1,contract['step_days']))
    modes=row['result']['window_cache_audit']
    if len(starts)!=len(modes):raise ValueError('Window denominator differs')
    for i,start in enumerate(starts):
        a,b=old['historical_window_weights'][i],new['historical_window_weights'][i]
        for record,previous in ((a,prior_old),(b,prior_new)):
            if record['fit_start']!=calendar[start-fit] or record['fit_end']!=calendar[start-1] or record['anchor_weights']!=(previous if anchored else None):
                raise ValueError('Anchor/date trace differs')
        history_equal=all(returns[t][start-fit:start]==changed[t][start-fit:start] for t in task['tickers'].split(';'))
        reuse=task['holding_count']==1 or history_equal and a['anchor_weights']==b['anchor_weights']
        if (modes[i]['mode']=='REUSED_EXACT_FITTER_INPUT')!=reuse or (modes[i]['old_fitter_input_sha256']==modes[i]['new_fitter_input_sha256'])!=reuse:
            raise ValueError('Actual mode/fingerprint differs from independent history/anchor')
        if reuse and a['weights']!=b['weights']:raise ValueError('Cached weights changed')
        checks.append(dict(ordinal=i,history_equal=history_equal,reused=reuse));prior_old=a['weights'];prior_new=b['weights']
    sources[str(Path(__file__).resolve())]=scalar.sha(Path(__file__).read_bytes())
    sources[str(Path(scalar.__file__).resolve())]=scalar.sha(Path(scalar.__file__).read_bytes())
    for path,digest in sources.items():
        if scalar.sha(Path(path).read_bytes())!=digest:raise ValueError('Final source drift')
    result=dict(schema='ndx_snapshot_first_four_independent_audit_v1',source_hashes=sources,planned=966,completed=4,
        imported_probe_results_exact=imports,new_task=task,new_task_id=row['new_job_id'],variants=variants,mode_checks=checks,
        remaining_task_count=962,independent_fitter_executed=False,independent_evaluator_executed=False,
        full_april_delta_complete=False,point_in_time_verified=False,promotion_allowed=False)
    output=folder/'first_four_independent_audit_20260912.json'
    with output.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=scalar.sha(output.read_bytes()),sources=len(sources),
        max_error=max(v['max_absolute_error'] for v in variants),remaining=962,window_modes=checks)))


if __name__=='__main__':main()
