"""Hard-bound complete 11254-task plan and one explicitly requested new-input probe."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_delta_three_cell_paired_probe_research as prior
from backtest import ndx_delta_selected_input_research as adapter
SELF=Path(__file__).resolve();LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/delta_selected_input_20260912_v1'


def corrected(inputs):
    result=deepcopy(inputs)
    for ticker,date,old,new in adapter.CORRECTIONS:
        if result['returns'].loc[date,ticker]!=old:raise ValueError('Original evidenced cell differs')
        result['returns'].loc[date,ticker]=new
    return result


def check_selected(task,inputs):
    contract=inputs['contract'];calendar=inputs['returns'].index
    starts=range(contract['fit_days'],len(calendar)-contract['window_days']+1,contract['step_days'])
    used={i for start in starts for i in range(start-contract['fit_days'],start+contract['window_days'])}
    if (type(task['holding_count']) is not int or task['holding_count']<2 or
        task['weight_spec'] not in ('constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')):
        raise ValueError('Selected fitted DELTA task required')
    if not any(t in task['tickers'].split(';') and calendar.get_loc(day) in used for t,day,_,_ in adapter.CORRECTIONS):
        raise ValueError('Actual selected input dependency absent')


def build_plan():
    classified=prior.original.read(prior.CLASSIFICATION,prior.CLASSIFICATION_SHA)
    inventory=prior.original.read(prior.INVENTORY,prior.INVENTORY_SHA)
    errors=[dict(ticker=t,session=d,old=a,new=b) for t,d,a,b in adapter.CORRECTIONS]
    if (sorted(classified['errors'],key=lambda x:x['ticker'])!=sorted(errors,key=lambda x:x['ticker']) or
        classified['counts']['DELTA|SELECTED_INPUT_CHANGED']!=11254):
        raise ValueError('Hard original exact 11254 / three-cell cohort required')
    sources=prior.original.merge(classified['source_hashes'],adapter.correction_sources(),adapter.trace.source_hashes(),
        adapter.equivalence.previous.LOADED,{str(prior.CLASSIFICATION):prior.CLASSIFICATION_SHA,
        str(prior.INVENTORY):prior.INVENTORY_SHA,str(SELF):LOADED,str(adapter.SOURCE):adapter.LOADED,
        str(adapter.provenance.SOURCE):adapter.provenance.LOADED,str(adapter.provenance.previous.SOURCE):adapter.provenance.previous.LOADED,
        str(adapter.equivalence.SOURCE):adapter.equivalence.LOADED_SHA,str(prior.SELF):prior.LOADED,
        str(prior.original.SELF):prior.original.LOADED})
    prior.original.original._verify_sources(sources)
    contexts={};seen=set();dates=[];observations={}
    for date in sorted(classified['masks_by_date']):
        rows=sorted(classified['buckets'].get(date+'|DELTA|SELECTED_INPUT_CHANGED',[]),key=lambda x:x['task']['job_id'])
        if not rows:continue
        descriptor,=[x for x in inventory['summaries'] if x['coordinate']['selection_date']==date]
        summary=prior.original.read(descriptor['path'],descriptor['sha256'])
        sources=prior.original.merge(sources,summary['source_hashes'],{descriptor['path']:descriptor['sha256']})
        tasks=[]
        for row in rows:
            ref=prior.task_context_reference(row,summary['source_hashes']);path=ref['context_path']
            if path not in contexts:
                context=prior.original.read(path,ref['context_sha256'])
                if context['numerical_sources']!=adapter.trace.full._LOADED_SOURCES or context['runtime']!=adapter.current_runtime():
                    raise ValueError('Original numerical source or actual runtime differs')
                inputs={k:adapter._restore_input(v) for k,v in context['prepared_inputs'].items()}
                corrected(inputs)
                contexts[path]=(context,inputs)
                observations[path]=dict(context_sha256=ref['context_sha256'],gaps=adapter.provenance.validate_historical_evidence(context,sources))
            context,inputs=contexts[path];task=row['task'];job=task['job_id']
            if job in seen or task not in context['tasks'] or task['selection_date']!=date:
                raise ValueError('Original task identity/date differs')
            if sources.get(row['checkpoint_path'])!=row['checkpoint_sha256']:
                raise ValueError('Original checkpoint not bound by hard source evidence')
            value=prior.original.read(row['checkpoint_path'],row['checkpoint_sha256'])
            payload=deepcopy(value);own=payload.pop('checkpoint_sha256')
            if (set(payload)!={'context_sha256','task','status','result'} or own!=adapter.encoding._sha(payload)
                or payload['context_sha256']!=adapter.encoding._sha(context) or payload['task']!=task or payload['status']!='EVALUATED'):
                raise ValueError('Original checkpoint full identity differs')
            check_selected(task,inputs);seen.add(job)
            tasks.append(dict(**row,**ref,runtime=context['runtime'],new_job_id=adapter.encoding._sha(dict(
                schema='ndx_selected_three_cell_new_input_task_v1',original_task=task,checkpoint_sha256=row['checkpoint_sha256'],
                context_sha256=ref['context_sha256'],errors=errors,adapter_sha256=adapter.LOADED,runner_sha256=LOADED))))
        dates.append(dict(date=date,planned=len(tasks),tasks=tasks))
    if len(seen)!=11254 or len(contexts)!=161 or len(dates)!=15:
        raise ValueError('Exact full 11254 / 161 contexts / 15 dates required')
    for path,entry in observations.items():
        if adapter.provenance.validate_historical_evidence(contexts[path][0],sources)!=entry['gaps']:
            raise ValueError('Historical loader observation drift')
    prior.original.original._verify_sources(sources)
    return dict(schema='ndx_selected_three_cell_new_input_plan_v1',dates=dates,planned=11254,context_count=161,
        errors=errors,source_hashes=sources,historical_context_gap_observations=observations,
        probe=dict(date=dates[0]['date'],task=dates[0]['tasks'][0]),
        probe_selection='FIRST_DATE_THEN_ORIGINAL_JOB_ID_NO_ECONOMIC_SORT',observed_runtime=adapter.current_runtime(),
        old_input_numerical_evaluation_count=0,historical_training_performed=False,
        original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)


def load_plan(path,sha):
    saved=prior.original.read(path,sha)
    # Rebuild from independent hard anchors, never from caller-supplied hashes.
    if saved!=build_plan():raise ValueError('Externally signed plan differs from exact hard-source reconstruction')
    return saved


def run_first_probe(*,plan_path,plan_sha256,output):
    output=Path(output)
    if output.exists():raise FileExistsError('Existing new-input probe must not repeat fitting')
    plan=load_plan(plan_path,plan_sha256);row=plan['probe']['task']
    context=prior.original.read(row['context_path'],row['context_sha256'])
    inputs={k:adapter._restore_input(v) for k,v in context['prepared_inputs'].items()}
    sources=prior.original.merge(plan['source_hashes'],{str(Path(plan_path).resolve()):plan_sha256})
    started=perf_counter()
    result=adapter.evaluate_selected_delta(arguments=dict(task=row['task'],inputs=inputs,engine='joint_weight_v3',
        runtime=row['runtime'],source_hashes=sources),corrected_inputs=corrected(inputs),
        context_path=row['context_path'],context_sha256=row['context_sha256'],checkpoint_path=row['checkpoint_path'],checkpoint_sha256=row['checkpoint_sha256'])
    elapsed=perf_counter()-started
    saved=prior.original.publish(output,dict(schema='ndx_selected_three_cell_new_input_probe_v1',result=result,
        plan_path=str(Path(plan_path).resolve()),plan_sha256=plan_sha256,selected=plan['probe'],elapsed_seconds=elapsed,
        planned=11254,whole_batch_executed=False,original_result_reproduced=False,promotion_allowed=False))
    prior.original.original._verify_sources(result['source_hashes'])
    if adapter.provenance.validate_historical_evidence(context,result['source_hashes'])!=result['historical_loader_provenance_gaps']:
        raise ValueError('Historical loader observation drift during publication')
    return dict(**saved,elapsed_seconds=elapsed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--first-probe',action='store_true')
    parser.add_argument('--plan-path');parser.add_argument('--plan-sha256');parser.add_argument('--output');args=parser.parse_args()
    if args.prepare:
        output=Path(args.output) if args.output else OUTPUT/'plan.json'
        if output.exists():raise FileExistsError('Plan already exists')
        result=build_plan();saved=prior.original.publish(output,result)
        prior.original.original._verify_sources(result['source_hashes']);print(json.dumps(saved))
    else:
        if not args.plan_path or not args.plan_sha256:raise ValueError('External plan path and SHA required')
        print(json.dumps(run_first_probe(plan_path=args.plan_path,plan_sha256=args.plan_sha256,output=args.output or OUTPUT/'first_probe.json')))
