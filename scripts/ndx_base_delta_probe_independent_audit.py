"""Scalar saved-weight oracle; imports no evaluator or fitting implementation."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/cache/research/base_three_cell_window_delta_20260912_v1'
PLAN_SHA='dc79584e51e8bf1cdd46ab155afa0d75cb8d43c8898fd77b07d56e5b87b2cd0c'
CORRECTIONS=[('GOOG','2022-07-18',-.025335378898117544),('FTNT','2022-06-23',.019968386675822902),('GOOGL','2022-07-18',-.024580059928059006)]


def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


def decode(value):
    if not isinstance(value,dict):return value
    if set(value)=={'mapping'}:return {k:decode(v) for k,v in value['mapping'].items()}
    if set(value)=={'float_hex'}:return float.fromhex(value['float_hex'])
    if set(value)=={'timestamp'}:return value['timestamp'][:10]
    if set(value)=={'sequence_type','items'}:return [decode(v) for v in value['items']]
    raise ValueError('Unknown typed context value')


def metric(values,cost=0.):
    nav=peak=1.;dd=0.
    for i,value in enumerate(values):
        factor=(1.+value)*(1.-cost if i==0 else 1.)
        if not math.isfinite(factor) or factor<=0:raise ValueError('Invalid scalar wealth factor')
        nav*=factor;peak=max(peak,nav);dd=max(dd,1.-nav/peak)
    return nav**(252./len(values))-1.,dd


def quantile(values,p):
    values=sorted(values);position=(len(values)-1)*p;lo=math.floor(position);hi=math.ceil(position)
    return values[lo]+(values[hi]-values[lo])*(position-lo)


def economics(returns,target,incumbent,contract,records):
    order=sorted(incumbent);total=sum(incumbent[t] for t in order);incumbent={t:incumbent[t]/total for t in order}
    fit,window,step=[contract[k] for k in ('fit_days','window_days','step_days')]
    length=len(target);starts=list(range(fit,length-window+1,step))
    if len(starts)!=len(records):raise ValueError('Window denominator differs')
    prior=None;rows=[]
    for start,record in zip(starts,records):
        weights=record['weights'];reference=incumbent if prior is None else prior
        if any(not math.isfinite(v) or v<=0 for v in weights.values()) or abs(sum(weights.values())-1)>1e-12:
            raise ValueError('Weights not finite positive simplex')
        turnover=.5*sum(abs(weights.get(t,0)-reference.get(t,0)) for t in sorted(set(weights)|set(reference)))
        cost=turnover*contract['transaction_cost_bps']/10000.
        cand=[sum(returns[t][i]*weights[t] for t in record['tickers']) for i in range(start,start+window)]
        inc=[sum(returns[t][i]*incumbent[t] for t in order) for i in range(start,start+window)]
        cr,cd=metric(cand,cost);ir,idd=metric(inc);tr,td=metric(target[start:start+window])
        rows.append(dict(candidate_return=cr,candidate_drawdown=cd,incumbent_return=ir,incumbent_drawdown=idd,
            target_return=tr,target_drawdown=td,turnover=turnover,cost=cost));prior=weights
    def q(key,p):return quantile([row[key] for row in rows],p)
    out={name:q('candidate_'+key,p) for name,key,p in [('return_p50','return',.5),('return_p10','return',.1),('max_drawdown_p50','drawdown',.5),('max_drawdown_p90','drawdown',.9)]}
    for stem,key,ps in [('return','return',[.5,.1]),('drawdown_cost','drawdown',[.5,.9])]:
        for p in ps:out[f'paired_{stem}_p{int(p*100)}_vs_incumbent']=quantile([r['candidate_'+key]-r['incumbent_'+key] for r in rows],p)
    for name,key,p in [('return_p50','return',.5),('return_p10','return',.1),('max_drawdown_p50','drawdown',.5),('max_drawdown_p90','drawdown',.9)]:out[name+'_vs_012922']=out[name]-q('target_'+key,p)
    out['target_012922_distance']=sum(abs(out[k+'_vs_012922']) for k in ('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90'))
    out.update(turnover=q('turnover',.5),initial_turnover=rows[0]['turnover'],initial_transaction_cost=rows[0]['cost'],
        ongoing_rebalance_turnover_p50=quantile([r['turnover'] for r in rows[1:]],.5) if len(rows)>1 else 0.,
        turnover_p90=q('turnover',.9),turnover_max=max(r['turnover'] for r in rows),transaction_cost=q('cost',.5))
    return rows,out


def audit_probe(kind,probe_sha):
    sources={}
    def read(path,expected):
        raw=Path(path).read_bytes()
        if sha(raw)!=expected:raise ValueError('Externally bound artifact differs')
        sources[str(path)]=expected;return json.loads(raw)
    plan=read(FOLDER/'sealed_plan_v2.json',PLAN_SHA)
    probe=read(FOLDER/'probes'/(kind+'.json'),probe_sha)
    if probe['selected']!=plan['probes'][kind]:raise ValueError('Probe not the prespecified sample')
    choice=probe['selected'];day,=[r for r in plan['dates'] if r['date']==choice['date']]
    taskrow,=[r for r in day['tasks'] if r['new_job_id']==choice['new_job_id']]
    for path,expected in {**day['source_hashes'],**probe['result']['source_hashes']}.items():
        if sha(Path(path).read_bytes())!=expected:raise ValueError('Source closure drift: '+path)
        if path in sources and sources[path]!=expected:raise ValueError('Source conflict')
        sources[path]=expected
    context=read(day['context_path'],day['context_sha256'])
    typed=read(day['typed_context_path'],day['typed_context_sha256'])
    checkpoint=read(taskrow['checkpoint_path'],taskrow['checkpoint_sha256'])
    if checkpoint['context_sha256']!=day['context_sha256'] or checkpoint['task']!=taskrow['task'] or taskrow['task'] not in context['tasks']:
        raise ValueError('Original task/context/checkpoint lineage differs')
    inputs={key:decode(value['payload']) for key,value in typed['prepared_inputs'].items()}
    panel=inputs['returns'];calendar=panel['index'];returns=dict(zip(panel['columns'],panel['column_values']))
    target=inputs['target_returns']['column_values'][0];contract=inputs['contract'];inc=inputs['incumbent_weights']
    changed=deepcopy(returns)
    for ticker,date,new in CORRECTIONS:
        i=calendar.index(date)
        if returns[ticker][i]!=0.:raise ValueError('Old evidenced cell not zero')
        changed[ticker][i]=new
    old=decode(checkpoint['result']);new=probe['result']['evaluation'];task=taskrow['task'];names=task['tickers'].split(';')
    anchored=task['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor'
    starts=list(range(contract['fit_days'],len(calendar)-contract['window_days']+1,contract['step_days']))
    modes=probe['result']['window_cache_audit']
    if len(modes)!=len(starts):raise ValueError('Mode denominator differs')
    mode_checks=[];oldprior=newprior=None
    for i,start in enumerate(starts):
        a,b=old['historical_window_weights'][i],new['historical_window_weights'][i]
        for record,prior in ((a,oldprior),(b,newprior)):
            if (record['tickers']!=names or record['fit_start']!=calendar[start-contract['fit_days']] or record['fit_end']!=calendar[start-1]
                or record['fit_row_count']!=contract['fit_days'] or record['anchor_weights']!=(prior if anchored else None)
                or record['turnover_anchor_strength']!=(contract['turnover_anchor_strength'] if anchored else 0.)):
                raise ValueError('Fit date/identity/anchor differs')
        history_equal=all(returns[t][start-contract['fit_days']:start]==changed[t][start-contract['fit_days']:start] for t in names)
        anchor_equal=a['anchor_weights']==b['anchor_weights']
        expected_hit=len(names)==1 or history_equal and anchor_equal
        mode=modes[i]
        if (mode['mode']=='REUSED_EXACT_FITTER_INPUT')!=expected_hit or (mode['old_fitter_input_sha256']==mode['new_fitter_input_sha256'])!=expected_hit:
            raise ValueError('Recorded fingerprint/mode differs from independent history/anchor equality')
        if expected_hit and a['weights']!=b['weights']:raise ValueError('Exact cached fit changed weights')
        mode_checks.append(dict(ordinal=i,history_equal=history_equal,anchor_equal=anchor_equal,expected_reuse=expected_hit,
            independent_old_dependency_sha256=digest(dict(history={t:returns[t][start-contract['fit_days']:start] for t in names},anchor=a['anchor_weights'])),
            independent_new_dependency_sha256=digest(dict(history={t:changed[t][start-contract['fit_days']:start] for t in names},anchor=b['anchor_weights']))))
        oldprior=a['weights'];newprior=b['weights']
    variants=[]
    for label,values,saved in [('original',returns,old),('three_cell_corrected',changed,new)]:
        windows,metrics=economics(values,target,inc,contract,saved['historical_window_weights'])
        errors={key:abs(value-saved['result'][key]) for key,value in metrics.items()}
        if max(errors.values())>1e-12:raise ValueError('Scalar economic mismatch: '+str(errors))
        variants.append(dict(variant=label,windows=windows,metrics=metrics,max_absolute_error=max(errors.values())))
    if kind=='k1' and probe['result']['refitted_window_count']!=0:raise ValueError('K1 refitted')
    sources[str(Path(__file__).resolve())]=sha(Path(__file__).read_bytes())
    for path,expected in sources.items():
        if sha(Path(path).read_bytes())!=expected:raise ValueError('Source drift after audit')
    return dict(kind=kind,task=task,variants=variants,mode_checks=mode_checks,source_hashes=sources,
        original_reported_reconstruction_error=probe['result']['original_metric_reconstruction_max_error'],
        source_probe_sha256=probe_sha,fitter_executed=False,evaluator_executed=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--kind',required=True,choices=['anchored','non_anchor','k1']);parser.add_argument('--probe-sha256',required=True)
    args=parser.parse_args();report=audit_probe(args.kind,args.probe_sha256)
    output=FOLDER/'probes'/(args.kind+'_independent_scalar_audit.json')
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=sha(output.read_bytes()),kind=args.kind,max_error=max(v['max_absolute_error'] for v in report['variants']))))
