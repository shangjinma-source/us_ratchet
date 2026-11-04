# Serialization-only successor; original SHA256 c1e0a928ff9aa52388d45786ec85db2eb3eaa82fbdb96e34cd4c837c7651a66d
"""Single complete first-date observation. Not an account backtest."""
from pathlib import Path
import sys,json,time,os,gzip
from hashlib import sha256
from fractions import Fraction as F
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backtest.research_exact_fraction_json import dumps as exact_dumps
from scripts.audit_capped_training_frontier import validate_binding
from backtest.downside_candidate_observer_integer_research import DownsideCandidateObserver
from scripts.audit_capped_training_frontier import capped,evaluate
from scripts.research.preflight_downside_frontier_20261105 import classify
from backtest.research_exact_fast_guided_observed import enhanced_search


def main():
    started=time.monotonic();out=ROOT/'tmp/downside_observer_complete_first_month_20261105_v2'
    out.mkdir(exist_ok=False)
    receipt=dict(pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat(),deadline_seconds=300,risk_budget=10000,
                 scope='FIRST_SORTED_EARLY_DATE_COMPLETE_OBSERVATION_NOT_STRATEGY',search_calls=0,economic_runs=0)
    def save(name,value): (out/name).write_text(exact_dumps(value),encoding='utf-8')
    def check():
        if time.monotonic()-started>=300:raise TimeoutError('COOPERATIVE_300_SECONDS_REACHED')
    save('receipt.json',receipt);observer=None;seen_calls=0;observer_seconds=0.0;pins={};phase_counts={} ; passed_by_k={}; additional_passed_by_k={}; old_cap_signatures=set();risk_signatures=set()
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
        observer=DownsideCandidateObserver(max_holdings=len(args['prices']),search_arguments=args,stock_returns=returns,qqq_reference=reference,max_risk_evaluations=10000)
        receipt.update(domain_size=len(args['prices']),max_holdings_scope='DOMAIN_SIZE_DIAGNOSTIC_NO_HOLDING_FILTER',loading_seconds=time.monotonic()-started,source_hashes=pins)
        for name in ('backtest/downside_candidate_observer_research.py','backtest/research_exact_fast_search_observed.py','backtest/saved_quantity_candidate_comparison_observed.py','backtest/research_exact_fast_guided_observed.py','scripts/research/complete_first_month_downside_observer_20261105_v2.py','backtest/research_exact_fraction_json.py','backtest/downside_candidate_observer_integer_research.py','backtest/downside_daily_integer_candidate.py'):
            pins[name]=sha256((ROOT/name).read_bytes()).hexdigest()
        save('receipt.json',receipt)
        old_cap_signatures={tuple(sorted(capped(r['quantities'],args).items())) for r in raw['search_result']['best_by_k'].values()}
        class Timed:
            def observe(self,q,*,phase,evaluation_index):
                nonlocal seen_calls,observer_seconds
                check();seen_calls+=1;phase_counts[phase]=phase_counts.get(phase,0)+1
                before=observer.counts['risk_evaluated'];passed_before=observer.counts['risk_pass_positive']+observer.counts['risk_pass_cash']
                began=time.monotonic()
                try:observer.observe(q,phase=phase,evaluation_index=evaluation_index)
                finally:observer_seconds+=time.monotonic()-began
                if observer.counts['risk_evaluated']>before:
                    signature=tuple(sorted(capped(q,args).items()));risk_signatures.add(signature)
                    if observer.counts['risk_pass_positive']+observer.counts['risk_pass_cash']>passed_before:
                        k=str(len(signature));passed_by_k[k]=passed_by_k.get(k,0)+1
                        if signature not in old_cap_signatures:additional_passed_by_k[k]=additional_passed_by_k.get(k,0)+1
                check()
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
        sidecar=observer.finalize()
        assert not differences,'ORIGINAL_SEARCH_RESULT_CHANGED'
        assert observer.counts['risk_evaluated']==observer.counts['capped_unique'] and observer.counts['over_holdings_limit']==0,'INCOMPLETE_CAP_DOMAIN'
        assert len(risk_signatures)==observer.counts['capped_unique'],'RISK_SIGNATURE_COVERAGE_MISMATCH'
        assert phase_counts.get('base')==result['objective_evaluations'],'BASE_HOOK_COVERAGE'
        extra=result['continuous_comparison']['exact_evaluations']
        assert phase_counts.get('comparison')==extra['saved_unique']+extra['new_unique'],'COMPARISON_HOOK_COVERAGE'
        sidecar.update(source_hashes=pins,search_hook_counts_verified=True,phase_counts=phase_counts,
                       passed_by_actual_k=passed_by_k,additional_passed_not_in_saved_frontier_by_k=additional_passed_by_k,
                       binding=dict(decision_date=day,search_arguments=args,diagnostic_max_holdings=102))
        save('sidecar.json',sidecar)
        receipt['finalize']='COMPLETE_SAME_CALL_OBSERVED_DOMAIN_NOT_ALL_POSSIBLE_PORTFOLIOS'
        receipt.update(passed_by_actual_k=passed_by_k,additional_passed_not_in_saved_frontier_by_k=additional_passed_by_k,
                       phase_counts=phase_counts,integer_diagnostics=observer.integer_returns.diagnostics)
    except Exception as error:
        receipt.update(status='STOPPED_WITH_ERROR',error=repr(error))
    receipt.update(elapsed_seconds=time.monotonic()-started,observer_seconds=observer_seconds,hook_calls=seen_calls,source_hashes=pins,coverage=observer.counts if observer else None,observer_complete=observer.complete if observer else False)
    mismatches=[name for name,h in pins.items() if sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    receipt['post_run_source_verification']=dict(status='FAIL' if mismatches else 'PASS',count=len(pins),mismatches=mismatches)
    if mismatches:receipt['status']='SOURCE_CHANGED_FAILURE'
    save('summary.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if k!='source_hashes'},default=str))

if __name__=='__main__':main()
