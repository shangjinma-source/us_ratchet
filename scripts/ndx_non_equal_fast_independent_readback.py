"""Independent no-fitter verification of saved-window recovery artifacts."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_evidenced_split_equal_delta_readback as scalar

SOURCE=Path(__file__).resolve();SOURCE_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PLAN=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/three_cell_saved_dependency_20260912.json'
PLAN_SHA='ae3fed1689457034fbe51227de1f9202a3b9602e6e0a95afa3657fdae2771da0'
REVIEW=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json'
REVIEW_SHA='a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'
DIRECTORY=ROOT/'data/cache/research/non_equal_three_cell_recovery_20260912_fast_v3'
PAIRED={key for key in scalar.METRICS if key.startswith('paired_')}
RULE='BEFORE_SCORE_ACCESS_EACH_K_WEIGHT_SPEC_LEXICAL_FIRST_AND_LAST_TASK'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def sample_jobs(rows):
    groups={}
    for row in rows:
        task=row['task'];groups.setdefault((task['holding_count'],task['weight_spec']),[]).append(task)
    result=set()
    for tasks in groups.values():
        ordered=sorted(tasks,key=lambda task:(task['tickers'],task['job_id']))
        result.update((ordered[0]['job_id'],ordered[-1]['job_id']))
    return result


def aggregate(windows):
    q=lambda field,p:scalar.quantile([row[field] for row in windows],p)
    result=dict(return_p50=q('candidate_return',.5),return_p10=q('candidate_return',.1),
        max_drawdown_p50=q('candidate_drawdown',.5),max_drawdown_p90=q('candidate_drawdown',.9))
    for stem,field,ps in [('return','return',(.5,.1)),('drawdown_cost','drawdown',(.5,.9))]:
        for probability in ps:
            result[f'paired_{stem}_p{int(probability*100)}_vs_incumbent']=scalar.quantile(
                [row['candidate_'+field]-row['incumbent_'+field] for row in windows],probability)
    for name,field,probability in [('return_p50','return',.5),('return_p10','return',.1),
                                  ('max_drawdown_p50','drawdown',.5),('max_drawdown_p90','drawdown',.9)]:
        result[name+'_vs_012922']=result[name]-q('target_'+field,probability)
    result['target_012922_distance']=sum(abs(result[field+'_vs_012922']) for field in
        ('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90'))
    result.update(turnover=q('turnover',.5),initial_turnover=windows[0]['turnover'],
        initial_transaction_cost=windows[0]['cost'],turnover_p90=q('turnover',.9),
        turnover_max=max(row['turnover'] for row in windows),transaction_cost=q('cost',.5),
        ongoing_rebalance_turnover_p50=scalar.quantile([row['turnover'] for row in windows[1:]],.5) if len(windows)>1 else 0.)
    return result


def compare_metrics(actual,expected,tolerance=1e-12):
    scalar.require(set(actual)==set(expected),'Exact twenty-metric schema differs')
    errors=[abs(actual[key]-expected[key]) for key in actual]
    scalar.require(all(math.isfinite(value) for value in errors) and max(errors)<=tolerance,'Independent metric differs')
    return max(errors)


def verify_date(date,summary_sha):
    plan,_=scalar.read(PLAN,PLAN_SHA);review,_=scalar.read(REVIEW,REVIEW_SHA)
    bucket=date+'|NON_EQUAL_BASE|PAIRED_ONLY_NO_REFIT';selected=plan['buckets'][bucket]
    scalar.require(digest(selected)==plan['bucket_content_sha256'][bucket],'Bound classification bucket differs')
    sample=sample_jobs(selected)
    folder=DIRECTORY/date.replace('-','');summary,sha=scalar.read(folder/'summary.json',summary_sha)
    context,context_sha=scalar.read(folder/'context.json',summary['context_sha256'])
    scalar.verify_sources(context['source_hashes'])
    coordinate={key:selected[0]['task'][key] for key in ('source_batch','universe_track','selection_date')}
    scalar.require(context['coordinate']==coordinate and summary['date']==date,'Date/source differs')
    scalar.require(context['errors']==plan['errors'] and context['bucket_sha256']==plan['bucket_content_sha256'][bucket],
        'Declared correction/bucket differs')
    for report in (summary,context):
        scalar.require(report['fitted'] is False and report['promotion_allowed'] is False,'Unexpected fitting/admission role')
    scalar.require(summary['all_non_equal_training_complete'] is False,'Incomplete refit lane cannot claim completion')
    scalar.require(context['selected']==selected and len(selected)==summary['planned']==summary['completed'],
        'Complete recovery denominator differs')
    for section,label in [('reference_only','NO_DEPENDENCY'),('excluded_refit','SELECTED_INPUT_CHANGED')]:
        expected=plan['buckets'].get(date+'|NON_EQUAL_BASE|'+label,[])
        scalar.require(context[section]==expected and summary[section+'_count']==len(expected),'Excluded/reference classification differs')
    scalar.require([row['job_id'] for row in summary['outputs']]==[row['task']['job_id'] for row in selected],
        'Exact original task order differs')
    location,=[row for row in review['actual_window_error_locations'] if row['coordinate']==coordinate]
    typed_sha=location['context_sha256'];typed_path=ROOT/'data/cache/research/ndx_joint_weight_runs_v3'/typed_sha/'context.json'
    scalar.require(context['source_hashes'].get(str(typed_path))==typed_sha,'Exact original typed context missing')
    typed,_=scalar.read(typed_path,typed_sha);inputs=scalar.unpack_inputs(typed['prepared_inputs'])
    corrected=deepcopy(inputs)
    for ticker,day,value in scalar.CELLS:
        index=corrected['returns']['index'].index(day)
        scalar.require(corrected['returns']['values_by_column'][ticker][index]==0.,'Original three cell value differs')
        corrected['returns']['values_by_column'][ticker][index]=value
    calendar=inputs['returns']['index'];contract=inputs['contract']
    starts=list(range(contract['fit_days'],len(calendar)-contract['window_days']+1,contract['step_days']))
    incumbent={key:float(inputs['incumbent_weights'][key]) for key in sorted(inputs['incumbent_weights'])}
    total=sum(incumbent.values());incumbent={key:value/total for key,value in incumbent.items()}
    benchmarks={}
    for label,values in [('original',inputs),('corrected',corrected)]:
        returns=values['returns']['values_by_column'];result=[]
        for start in starts:
            days=range(start,start+contract['window_days'])
            control=[sum(returns[ticker][i]*weight for ticker,weight in incumbent.items()) for i in days]
            cr,cd=scalar.scalar_window(control,0.)
            tr,td=scalar.scalar_window(values['target_returns']['column_values'][0][start:start+contract['window_days']],0.)
            result.append(dict(incumbent_return=cr,incumbent_drawdown=cd,target_return=tr,target_drawdown=td))
        benchmarks[label]=result
    maximum=0.;samples=[];hashes={str(folder/'summary.json'):sha,str(folder/'context.json'):context_sha,str(typed_path):typed_sha}
    for descriptor,classification in zip(summary['outputs'],selected):
        task=classification['task'];job=task['job_id']
        scalar.require(Path(descriptor['path']).resolve()==(folder/(job+'.json')).resolve(),'Unexpected task path')
        value,_=scalar.read(descriptor['path'],descriptor['sha256']);selfsha=value.pop('content_sha256')
        scalar.require(digest(value)==selfsha and value['task']==task and value['context_sha256']==context_sha,
            'Recovered checkpoint identity differs')
        scalar.require(value['status']=='RECOVERED_NO_FIT','Recovered status differs')
        result=value['result'];scalar.require(result['task']==task,'Nested task differs')
        scalar.require(result['original_checkpoint_path']==classification['checkpoint_path']
            and result['original_checkpoint_sha256']==classification['checkpoint_sha256'],'Original lineage differs')
        raw,_=scalar.read(classification['checkpoint_path'],classification['checkpoint_sha256']);saved=scalar.decode(raw['result'])
        combo=task['tickers'].split(';')
        scalar.require(not set(combo)&{'GOOG','GOOGL','FTNT'},'Selected corrected ticker cannot be no-refit paired-only')
        scalar.require(result['dependency_fields_changed']==['incumbent_forward_returns'],'Dependency role differs')
        scalar.require(result['selected_fit_forward_inputs_exact'] is True,'Selected input equivalence not asserted')
        for key in ('fitted','projection_called','whole_lot_called','promotion_allowed'):
            scalar.require(result[key] is False,'Unexpected computation/admission claim')
        old=result['original'];new=result['corrected']
        scalar.require(len(old['windows'])==len(new['windows'])==len(starts)==len(saved['historical_window_weights']),
            'Complete saved-window denominator differs')
        actual_changes={key for key in old['metrics'] if old['metrics'][key]!=new['metrics'][key]}
        scalar.require(actual_changes<=PAIRED and set(result['changed_metrics'])==actual_changes,'Nonpaired metric changed')
        for label,report in [('original',old),('corrected',new)]:
            maximum=max(maximum,compare_metrics(report['metrics'],aggregate(report['windows'])))
            if label=='original':
                maximum=max(maximum,compare_metrics(report['metrics'],{key:saved['result'][key] for key in report['metrics']}))
            for row,expected in zip(report['windows'],benchmarks[label]):
                for key,target in expected.items():
                    error=abs(row[key]-target);scalar.require(error<=1e-12,'All-record scalar benchmark differs');maximum=max(maximum,error)
        prior=None
        for ordinal,(start,a,b,weight_record) in enumerate(zip(starts,old['windows'],new['windows'],saved['historical_window_weights'])):
            scalar.require(all(a[key]==b[key] for key in a if not key.startswith('incumbent_')),'Candidate/target/fee window changed')
            scalar.require(a['start']==calendar[start] and a['end']==calendar[start+contract['window_days']-1],'Window date differs')
            weights=weight_record['weights']
            scalar.require(weight_record['tickers']==combo and set(weights)==set(combo)
                and all(type(value) in (int,float) and math.isfinite(value) and value>0 for value in weights.values())
                and abs(sum(weights.values())-1.)<=1e-12,'Saved weight identity differs')
            anchored=task['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor'
            scalar.require(weight_record['fit_start']==calendar[start-contract['fit_days']]
                and weight_record['fit_end']==calendar[start-1] and weight_record['fit_row_count']==contract['fit_days']
                and weight_record['anchor_weights']==(prior if anchored else None)
                and weight_record['turnover_anchor_strength']==(contract['turnover_anchor_strength'] if anchored else 0.),
                'Saved fit boundary/anchor contract differs')
            reference=incumbent if prior is None else prior
            turnover=.5*sum(abs(weights.get(ticker,0.)-reference.get(ticker,0.)) for ticker in sorted(set(weights)|set(reference)))
            cost=turnover*contract['transaction_cost_bps']/10000.
            scalar.require(abs(a['turnover']-turnover)<=1e-12 and abs(a['cost']-cost)<=1e-12,'Saved-weight turnover/fee differs')
            if job in sample:
                returns=inputs['returns']['values_by_column']
                daily=[sum(returns[ticker][i]*weights[ticker] for ticker in combo) for i in range(start,start+contract['window_days'])]
                cr,cd=scalar.scalar_window(daily,cost)
                error=max(abs(cr-a['candidate_return']),abs(cd-a['candidate_drawdown']))
                scalar.require(error<=1e-12,'Fixed-sample scalar candidate differs');maximum=max(maximum,error)
            prior=weights
        if job in sample:samples.append(dict(job_id=job,tickers=task['tickers'],holding_count=task['holding_count'],weight_spec=task['weight_spec'],window_count=len(starts)))
        hashes[descriptor['path']]=descriptor['sha256']
    scalar.verify_sources(context['source_hashes']);scalar.verify_sources(hashes)
    return dict(date=date,path=str(folder/'summary.json'),sha256=sha,count=len(selected),
        all_record_twenty_metric_aggregates_verified=True,all_record_benchmark_windows_scalar_verified=True,
        all_record_candidate_target_fee_unchanged=True,all_record_saved_weight_turnover_verified=True,
        sample_rule=RULE,samples=samples,sample_count=len(samples),maximum_absolute_error=maximum,
        source_hashes=hashes,fit_or_projection_called=False,training_rerun=False,promotion_allowed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-path',required=True);parser.add_argument('--index-sha256',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    index,index_sha=scalar.read(args.index_path,args.index_sha256)
    scalar.require(sorted(index)==list(scalar.DATES[:10]),'Complete ten-date external SHA index required')
    output=Path(args.output).resolve()
    scalar.require((ROOT/'data/cache/research').resolve() in output.parents,'Research output only')
    if output.exists():raise FileExistsError(output)
    reports=[];sources={str(SOURCE):SOURCE_SHA,str(Path(scalar.__file__).resolve()):scalar.SOURCE_SHA,
        str(PLAN):PLAN_SHA,str(REVIEW):REVIEW_SHA,str(Path(args.index_path).resolve()):index_sha}
    for day in sorted(index):
        report=verify_date(day,index[day]);sources.update(report.pop('source_hashes'));reports.append(report)
        print(json.dumps(dict(date=day,count=report['count'],samples=report['sample_count'],maximum_error=report['maximum_absolute_error'])),flush=True)
    scalar.require(sum(row['count'] for row in reports)==2444,'Recovered global denominator differs')
    plan,_=scalar.read(PLAN,PLAN_SHA)
    counts={kind:sum(len(rows) for key,rows in plan['buckets'].items() if key.endswith('|NON_EQUAL_BASE|'+kind))
        for kind in ('PAIRED_ONLY_NO_REFIT','NO_DEPENDENCY','SELECTED_INPUT_CHANGED')}
    scalar.require(counts=={'PAIRED_ONLY_NO_REFIT':2444,'NO_DEPENDENCY':1526,'SELECTED_INPUT_CHANGED':15578},'Partition denominator differs')
    task_ids=set()
    for key,rows in plan['buckets'].items():
        if '|NON_EQUAL_BASE|' not in key:continue
        for row in rows:
            job=row['task']['job_id'];scalar.require(job not in task_ids,'Non-equal classification partition overlaps')
            task_ids.add(job);scalar.read(row['checkpoint_path'],row['checkpoint_sha256'])
            sources[row['checkpoint_path']]=row['checkpoint_sha256']
    scalar.require(len(task_ids)==19548,'Original full non-equal partition coverage differs')
    report=dict(schema='ndx_non_equal_fast_independent_readback_v1',dates=reports,counts=counts,
        total_original_non_equal_tasks=19548,recovered_tasks=2444,reference_only_tasks=1526,excluded_refit_tasks=15578,
        source_hashes=sources,all_non_equal_retraining_complete=False,fit_or_projection_called=False,promotion_allowed=False)
    scalar.verify_sources(sources);raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(raw)
    scalar.require(output.read_bytes()==raw,'Independent inventory readback differs')
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest())),flush=True)


if __name__=='__main__':main()
