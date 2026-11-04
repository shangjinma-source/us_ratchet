"""One first-date cost sample. Not portfolio selection or account backtest."""
from pathlib import Path
import sys,json,time,os,gzip
from hashlib import sha256
from fractions import Fraction as F
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.audit_capped_training_frontier import validate_binding
from backtest.downside_candidate_observer_research import DownsideCandidateObserver
from backtest.research_exact_fast_guided_observed import enhanced_search


def main():
    started=time.monotonic();out=ROOT/'tmp/downside_observer_cost_first_month_20261105'
    out.mkdir(exist_ok=False)
    receipt=dict(pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat(),deadline_seconds=180,risk_budget=64,
                 scope='FIRST_SORTED_EARLY_DATE_COST_SAMPLE_NOT_STRATEGY',search_calls=0,economic_runs=0)
    def save(name,value): (out/name).write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')
    def check():
        if time.monotonic()-started>=180:raise TimeoutError('COOPERATIVE_180_SECONDS_REACHED')
    save('receipt.json',receipt);observer=None;seen_calls=0;pins={}
    def read(name):
        check();p=ROOT/name;b=p.read_bytes();pins[name]=sha256(b).hexdigest();return json.loads(gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b)
    def verify(mapping):
        for name,h in mapping.items():
            check();actual=sha256((ROOT/name).read_bytes()).hexdigest()
            if actual!=h:raise ValueError('SOURCE_HASH_CHANGED:'+name)
            pins[name]=actual
    try:
        prior=read('tmp/downside_frontier_preflight_20261105/result.json');verify(prior['source_hashes'])
        day=min(r['decision_date'] for r in prior['rows'] if r['window']=='early');receipt['decision_date']=day
        saved=read('tmp/recent_continuous_baseline_20261026_v7/'+day+'.selection.json');raw=saved['raw_selection'];args=validate_binding(raw);verify(raw['binding']['source_hashes'])
        assert args['max_objective_evaluations']==8192
        training=read('tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json');verify(training['source_hashes'])
        window=next(o['window'] for o in training['windows'] if o['window']['decision_cutoff']==day)
        dates=window['training_dates'];assert len(dates)==253 and dates==sorted(set(dates)) and dates[-1]==day
        candidates={c['security_id']:c for c in window['candidates'] if c.get('security_id')};returns={}
        for sid in args['prices']:
            check();prices=list(map(F,candidates[sid]['training_close']));assert len(prices)==253 and all(p>0 for p in prices)
            returns[sid]=dict(zip(dates[1:],[b/a-1 for a,b in zip(prices,prices[1:])]))
        qprices={}
        for name in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
            body=read(name)['chart']['result'][0]
            for stamp,close in zip(body['timestamp'],body['indicators']['quote'][0]['close']):
                if close is None:continue
                d=datetime.fromtimestamp(stamp,tz=timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat();v=F(str(close))
                if d in qprices and qprices[d]!=v:raise ValueError('QQQ_OVERLAP_CONFLICT')
                qprices[d]=v
        reference=dict(zip(dates[1:],[qprices[b]/qprices[a]-1 for a,b in zip(dates,dates[1:])]))
        observer=DownsideCandidateObserver(max_holdings=len(args['prices']),search_arguments=args,stock_returns=returns,qqq_reference=reference,max_risk_evaluations=64)
        receipt.update(domain_size=len(args['prices']),max_holdings_scope='DOMAIN_SIZE_DIAGNOSTIC_NO_HOLDING_FILTER',loading_seconds=time.monotonic()-started,source_hashes=pins)
        for name in ('backtest/downside_candidate_observer_research.py','backtest/research_exact_fast_search_observed.py','backtest/saved_quantity_candidate_comparison_observed.py','backtest/research_exact_fast_guided_observed.py','scripts/research/sample_downside_observer_cost_20261105.py'):
            pins[name]=sha256((ROOT/name).read_bytes()).hexdigest()
        save('receipt.json',receipt)
        class Timed:
            def observe(self,q,*,phase,evaluation_index):
                nonlocal seen_calls
                check();seen_calls+=1;observer.observe(q,phase=phase,evaluation_index=evaluation_index)
                if seen_calls%128==0 or seen_calls==1:
                    save('progress.json',dict(elapsed=time.monotonic()-started,hook_calls=seen_calls,phase=phase,coverage=observer.counts,complete=observer.complete))
        check();receipt['search_calls']=1;save('receipt.json',receipt)
        result=enhanced_search(candidate_observer=Timed(),**args);check();observer.end_observation()
        save('search_result.json',result)
        differences=[]
        def diff(a,b,path=''):
            if isinstance(a,dict) and isinstance(b,dict):
                for k in sorted(set(a)|set(b)):
                    if k not in a or k not in b:differences.append(dict(path=path+'/'+k,actual=a.get(k),saved=b.get(k)))
                    else:diff(a[k],b[k],path+'/'+k)
            elif a!=b:differences.append(dict(path=path,actual=a,saved=b))
        diff(result,raw['search_result']);save('saved_result_differences.json',differences)
        receipt.update(status='SEARCH_FINISHED_COST_SAMPLE',saved_original_result_equal=not differences,difference_count=len(differences),objective_evaluations=result['objective_evaluations'],continuous_evaluations=result['continuous_comparison']['exact_evaluations'])
        try:observer.finalize();receipt['finalize']='COMPLETE_OBSERVED_STREAM_ONLY'
        except ValueError as e:receipt['finalize']=str(e)
    except Exception as error:
        receipt.update(status='STOPPED_WITH_ERROR',error=repr(error))
    receipt.update(elapsed_seconds=time.monotonic()-started,hook_calls=seen_calls,source_hashes=pins,coverage=observer.counts if observer else None,observer_complete=observer.complete if observer else False)
    save('summary.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if k!='source_hashes'},default=str))

if __name__=='__main__':main()
