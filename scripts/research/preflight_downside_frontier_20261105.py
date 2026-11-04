"""Frozen 67-frontier arithmetic only: no basket generation or account replay."""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal,localcontext,ROUND_FLOOR,ROUND_CEILING
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from hashlib import sha256
import json,time,sys,gzip
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.audit_capped_training_frontier import capped,evaluate,validate_binding
from backtest.capped_frontier_rerank_research import rerank


def bounds(returns):
    answers=[]
    for rounding in (ROUND_FLOOR,ROUND_CEILING):
        with localcontext() as ctx:
            ctx.prec=80;ctx.rounding=rounding
            total=Decimal(0)
            for value in returns:
                if value>=0:continue
                # Square exact rational first; conversion and accumulation directed.
                square=value*value
                total+=Decimal(square.numerator)/Decimal(square.denominator)
            answers.append(total/Decimal(len(returns)))
    return answers


def classify(values,reference,reference_bounds):
    low,high=bounds(values);qlow,qhigh=reference_bounds
    if high<=qlow:return True,False,[str(low),str(high)]
    if low>qhigh:return False,False,[str(low),str(high)]
    exact=lambda xs:sum((min(x,F(0))**2 for x in xs),F(0))/len(xs)
    return exact(values)<=exact(reference),True,[str(low),str(high)]


def main():
    started=time.monotonic();pins={};out=ROOT/'tmp/downside_frontier_preflight_20261105';out.mkdir(exist_ok=True);assert not (out/"result.json").exists()
    def load(name):
        path=ROOT/name;pins[path.relative_to(ROOT).as_posix()]=sha256(path.read_bytes()).hexdigest();raw=path.read_bytes();return json.loads(gzip.decompress(raw) if raw[:2]==b"\x1f\x8b" else raw)
    def verify(expected):
        for name,digest in expected.items():
            path=ROOT/name;actual=sha256(path.read_bytes()).hexdigest()
            if actual!=digest:raise ValueError('SOURCE_HASH_CHANGED:'+name)
            pins[path.relative_to(ROOT).as_posix()]=actual
    manifest=load('research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json')['base_file_dependencies']
    qpaths=['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']
    qprices={}
    for path in qpaths:
        verify({path:manifest[path]});body=load(path)['chart']['result'][0]
        for stamp,close in zip(body['timestamp'],body['indicators']['quote'][0]['close']):
            if close is None:continue
            day=datetime.fromtimestamp(stamp,tz=timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat();value=F(str(close))
            if day in qprices and qprices[day]!=value:raise ValueError('QQQ_OVERLAP_CONFLICT')
            qprices[day]=value
    rows=[]
    for label,base,training in [('early','tmp/recent_continuous_baseline_20261026_v7','tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),('later','tmp/old_continuous_baseline_20261026_v9','tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')]:
        verify({training:manifest[training],base+'/execution_inputs.json':manifest[base+'/execution_inputs.json']})
        document=load(training);verify(document['source_hashes']);book=load(base+'/book.json');assert book['status']=='COMPLETE'
        audits={}
        for audit in book['provider_audit']:
            d=audit.get('target_decision_date')
            if d and d not in audits and 'monthly_ceiling' in audit:audits[d]=audit
        for outer in document['windows']:
            window=outer.get('window',outer);day=window.get('decision_cutoff',window.get('decision_date'));row=dict(window=label,decision_date=day)
            try:
                if time.monotonic()-started>540:raise TimeoutError('PREDECLARED_LOCAL_540_SECOND_LIMIT')
                saved=load(base+'/'+day+'.selection.json');raw=saved['raw_selection'];args=validate_binding(raw);verify(raw['binding']['source_hashes'])
                dates=window['training_dates'];assert len(dates)==253 and dates==sorted(set(dates)) and dates[-1]==day
                candidates={c['security_id']:c for c in window['candidates'] if c.get('security_id')}
                returns={}
                assert args['scenario_dates']==dates[21::21] and len(args['training_scenarios'])==12
                for sid in args['prices']:
                    candidate=candidates[sid];prices=list(map(F,candidate['training_close']));assert len(prices)==253 and all(p>0 for p in prices)
                    assert all(F(args['training_scenarios'][j][sid])==prices[(j+1)*21]/prices[j*21] for j in range(12)),('SCENARIO_MISMATCH',sid)
                    returns[sid]=[b/a-1 for a,b in zip(prices,prices[1:])]
                reference=[qprices[b]/qprices[a]-1 for a,b in zip(dates,dates[1:])];qbound=bounds(reference)
                selected=rerank(raw);assert selected['target_quantities']==audits[day]['monthly_ceiling'],'BASELINE_SELECTED_MISMATCH'
                original=tuple(sorted((s,q) for s,q in selected['target_quantities'].items() if q));basecap=tuple(sorted(capped(raw['target_quantities'],args).items()))
                unique={}
                for key,record in raw['search_result']['best_by_k'].items():
                    assert int(key)==len(record['quantities']);basket=capped(record['quantities'],args);signature=tuple(sorted(basket.items()));unique.setdefault(signature,[]).append(int(key))
                assert original in unique and basecap in unique
                outcomes=[]
                for signature,ks in unique.items():
                    quantity=dict(signature);score=evaluate(quantity,args);weights={s:q*F(args['prices'][s])/F(args['entered_cash']) for s,q in signature};assert sum(weights.values(),F(0))<=1
                    portfolio=[sum((weights[s]*returns[s][i] for s in weights),F(0)) for i in range(252)]
                    passed,exact,interval=classify(portfolio,reference,qbound)
                    outcomes.append(dict(target_quantities=quantity,source_cardinalities=sorted(ks),passes=passed,exact_boundary_comparison=exact,downside_interval=interval,original_v27_selected=signature==original,original_capped_raw=signature==basecap,cash_weight=str(1-sum(weights.values(),F(0)))))
                row.update(status='STATIC_FRONTIER_CHECK_COMPLETE',training_start=dates[0],training_end=dates[-1],candidate_domain=sorted(args['prices']),scenario_checks=12*len(args['prices']),unique_capped_baskets=len(outcomes),passing_baskets=sum(r['passes'] for r in outcomes),implied_cash_month=not any(r['passes'] for r in outcomes),original_selected_passes=next(r['passes'] for r in outcomes if r['original_v27_selected']),original_selected=dict(original),qqq_downside_interval=list(map(str,qbound)),baskets=outcomes)
            except Exception as error:row.update(status='BLOCKED',reason=repr(error))
            rows.append(row);(out/'progress.json').write_text(json.dumps(dict(month=day,status=row['status'],completed=len(rows),elapsed=time.monotonic()-started)),encoding='utf-8')
            if isinstance(row.get('reason'),str) and 'TIME_LIMIT' in row['reason']:break
    summary=[]
    for label in ('early','later'):
        part=[r for r in rows if r['window']==label];valid=[r for r in part if r['status']=='STATIC_FRONTIER_CHECK_COMPLETE'];summary.append(dict(window=label,required_months=36 if label=='early' else 31,observed_months=len(part),complete_months=len(valid),blocked_months=len(part)-len(valid),cash_months=sum(r['implied_cash_month'] for r in valid),original_selected_pass_months=sum(r['original_selected_passes'] for r in valid),unique_baskets=sum(r['unique_capped_baskets'] for r in valid),passing_baskets=sum(r['passing_baskets'] for r in valid),exact_boundary_comparisons=sum(b['exact_boundary_comparison'] for r in valid for b in r['baskets'])))
    for name in ['scripts/research/preflight_downside_frontier_20261105.py','scripts/audit_capped_training_frontier.py','backtest/capped_frontier_rerank_research.py']:pins[name]=sha256((ROOT/name).read_bytes()).hexdigest()
    result=dict(summary=summary,rows=rows,source_hashes=pins,elapsed_seconds=time.monotonic()-started,method='EXACT_DAILY_FRACTION_RETURNS_80_DIGIT_DIRECTED_DOWNSIDE_INTERVALS_EXACT_BOUNDARIES',search_calls=0,economic_runs=0,scope='Original baseline accounts and saved same-call frontier; no new branch account performance')
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
