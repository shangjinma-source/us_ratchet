"""Independent saved-byte arithmetic review; no generator, optimizer or book imports."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN='tmp/continuous_candidate_diagnostic_20261016_v1'
OUTPUT='tmp/continuous_candidate_diagnostic_independent_20261016_v1'


def require(ok,reason):
    if not ok:raise ValueError(reason)


def canonical(value,ascii=True):
    return json.dumps(value,sort_keys=True,separators=(',',':'),default=str,ensure_ascii=ascii,allow_nan=False).encode()


def audit(root=ROOT):
    root=Path(root);pins={}
    def read(path):
        raw=(root/path).read_bytes();pins[path]=sha256(raw).hexdigest();return json.loads(raw)
    complete=read(RUN+'/complete.json');started=read(RUN+'/started.json')
    require(complete['status']=='COMPLETE_PENDING_INDEPENDENT_REVIEW','NOT_COMPLETE')
    require(started['source_hashes']==complete['source_hashes'],'START_COMPLETE_PINS')
    for path,h in complete['source_hashes'].items():
        require(sha256((root/path).read_bytes()).hexdigest()==h,'SOURCE_DRIFT:'+path);pins[path]=h
    prepared=read('tmp/daily_verified_domain_experiment_20261016_v2/prepared.json')
    outcome=read('tmp/daily_exclusion_B0_20261016_v1/outcome.json')
    windows={w['decision_date']:w for w in prepared['windows']}
    selections={r['selection']['decision_date']:r['selection']for r in outcome['provider_audit']if r.get('selection')}
    summaries={r['decision_date']:r for r in complete['rows']}
    require(len(complete['rows'])==len(summaries)==len(windows)==len(selections)==34,'MONTH_COVERAGE')
    require(set(summaries)==set(windows)==set(selections),'MONTH_KEYS')
    rows=[];total_checked=0
    for day,window in windows.items():
        selected=selections[day];binding=selected['binding'];old=selected['search_result']
        require(sha256(canonical(binding,False)).hexdigest()==selected['decision_id'],'OLD_DECISION_BINDING')
        args=deepcopy(window['search_arguments']);args['entered_cash']=selected['investable_equity']
        require(args==binding['search_arguments'],'OLD_SEARCH_ARGUMENTS')
        require(all(p in pins and pins[p]==h for p,h in binding['source_hashes'].items()),'OLD_SOURCE_CLOSURE')
        quotes=binding['valuation_quotes'];equity=F(binding['available_cash'])
        for sid,q in binding['shares'].items():
            require(type(q)is int and q>=0,'OLD_SHARES')
            if q:
                require(quotes[sid]['as_of']==day,'OLD_MARK_DATE');equity+=q*F(quotes[sid]['price'])
        require(equity==F(selected['investable_equity'])==F(binding['investable_equity']),'OLD_EQUITY')
        result=read(RUN+'/'+day+'.json')
        require(result['inherited_saved_result']==old and result['inherited_coverage_reverified']is False,'OLD_FRONTIER_RETENTION')
        require(result['binding']['search_arguments_sha256']==sha256(canonical(args)).hexdigest()
            and result['binding']['saved_result_sha256']==sha256(canonical(old)).hexdigest(),'WRAPPER_BINDING')
        cash=equity;fee=F(args['fee_bps'])/10000;buffer=F(args['minimum_cash_buffer'])
        prices={s:F(p)for s,p in args['prices'].items()};metadata=args['metadata'];scenarios=args['training_scenarios'];cache={}
        def arithmetic(q):
            require(type(q)is dict and set(q)<=set(prices) and all(type(v)is int and v>0 for v in q.values()),'QUANTITIES')
            key=tuple(sorted(q.items()))
            if key in cache:return cache[key]
            require(len({metadata[s]['issuer_id']for s in q})==len(q),'ISSUER_CONFLICT')
            notional=sum((prices[s]*n for s,n in q.items()),F(0));fees=notional*fee;residual=cash-notional-fees
            require(residual>=0 and (not q or residual>=buffer),'BUDGET')
            growth=[(residual+sum((prices[s]*n*F(scenario[s])for s,n in sorted(q.items())),F(0)))/cash for scenario in scenarios]
            product=math.prod(growth);rank=(product,-notional,key)
            values=dict(notional=notional,fees=fees,residual_cash=residual,cash_fraction=residual/cash)
            cache[key]=(rank,values,growth);return cache[key]
        def check_record(record):
            q=record['quantities'];rank,values,growth=arithmetic(q)
            require(record['actual_k']==len(q),'CARDINALITY')
            for k,v in values.items():require(F(record[k])==v,'RECORD_'+k)
            require({s:F(v)for s,v in record['actual_weights'].items()}=={s:prices[s]*n/cash for s,n in q.items()},'WEIGHTS')
            if record['training_gross_growth_product']is not None:require(F(record['training_gross_growth_product'])==rank[0],'EXACT_PRODUCT')
            require(record['training_mean_net_log_wealth']==sum(math.log(v.numerator)-math.log(v.denominator)for v in growth)/len(growth),'DISPLAY_SCORE')
            return rank
        frontier={}
        for k,record in old['best_by_k'].items():
            rank=check_record(record);require(k==str(len(record['quantities'])),'OLD_K');frontier[k]=(rank,record['quantities'])
        oldrank=check_record(old['selected']);require(oldrank==max(v[0]for v in frontier.values()),'OLD_WINNER')
        oldcount=len(cache);generation=result['additional_generation']
        require(generation['iterations_requested']==generation['iterations_completed']==generation['gradient_evaluations']==32,'ITERATIONS')
        require(len(generation['trace'])==32 and generation['scenario_wealth_evaluations']==32*len(scenarios),'TRACE_COUNT')
        # Replay only saved vertex/step arithmetic, not FW gradient generation.
        weights={s:F(0)for s in prices};proposals=[{}];seen={()};spendable=max(F(0),cash-buffer)
        for i,trace in enumerate(generation['trace']):
            require(trace['iteration']==i+1 and F(trace['step'])==F(2,i+2),'FIXED_STEP')
            vertex=trace['vertex'];require(vertex is None or vertex in prices,'SAVED_VERTEX')
            step=F(trace['step']);weights={s:(1-step)*w+(step if s==vertex else 0)for s,w in weights.items()}
            groups={}
            for s in sorted(prices):groups.setdefault(metadata[s]['issuer_id'],[]).append(s)
            keep={min(ss,key=lambda s:(-weights[s],s))for ss in groups.values()}
            q={s:int(spendable*weights[s]//(prices[s]*(1+fee)))for s in sorted(keep)};q={s:n for s,n in q.items()if n}
            key=tuple(sorted(q.items()));added=key not in seen
            require(trace['candidate_added']==added,'TRACE_DEDUP')
            if added:proposals.append(q);seen.add(key)
        require(proposals==[r['quantities']for r in generation['candidates']] and len(proposals)==generation['candidate_count'],'SAVED_PROPOSALS_FROM_TRACE')
        for candidate in generation['candidates']:
            rank,values,_=arithmetic(candidate['quantities'])
            require(candidate['actual_k']==len(candidate['quantities']),'PROPOSAL_K')
            require(all(F(candidate[k])==values[k]for k in ('fees','residual_cash')),'PROPOSAL_FEES_CASH')
            k=str(candidate['actual_k'])
            if k not in frontier or rank>frontier[k][0]:frontier[k]=(rank,candidate['quantities'])
        require(set(frontier)==set(result['best_by_k']),'MERGED_K_COVERAGE')
        for k,record in result['best_by_k'].items():require((check_record(record),record['quantities'])==frontier[k],'MERGED_K_WINNER')
        newrank=check_record(result['selected']);require(newrank==max(v[0]for v in frontier.values()) and newrank>=oldrank,'GLOBAL_VISITED_WINNER')
        require(result['exact_evaluations']==dict(saved_unique=oldcount,new_unique=len(cache)-oldcount),'EXACT_EVAL_COUNTS')
        row=summaries[day];strict=newrank[0]>oldrank[0];changed=result['selected']['quantities']!=selected['target_quantities'];tie=changed and not strict
        require(row['strict_score_improvement']==strict and row['changed']==changed and row['tie_only_change']==tie,'CLASSIFICATION')
        require(row['old_quantities']==selected['target_quantities'] and row['new_quantities']==result['selected']['quantities'],'SUMMARY_QUANTITIES')
        require(result['global_optimum_established']is False and result['historical_backtest_run']is False,'NO_PERFORMANCE_CLAIM')
        winner=result['selected'];rows.append(dict(decision_date=day,old_k=len(selected['target_quantities']),new_k=winner['actual_k'],
            holdings=[dict(ticker=metadata[s]['ticker'],quantity=q,weight=winner['actual_weights'][s])for s,q in winner['quantities'].items()],
            cash_fraction=winner['cash_fraction'],strict_training_improvement=strict,tie_only_change=tie,checked_unique_targets=len(cache)))
        total_checked+=len(cache)
    require(complete['strict_improvements']==sum(r['strict_training_improvement']for r in rows),'STRICT_TOTAL')
    require(complete['tie_only_changes']==sum(r['tie_only_change']for r in rows),'TIE_TOTAL')
    require(complete['changed_months']==sum(r['strict_training_improvement']or r['tie_only_change']for r in rows),'CHANGED_TOTAL')
    path='scripts/review_continuous_candidate_diagnostic.py';pins[path]=sha256((root/path).read_bytes()).hexdigest()
    return dict(status='PASS_INDEPENDENT_SAVED_CANDIDATE_ARITHMETIC',months=len(rows),strict_improvements=complete['strict_improvements'],
        tie_only_changes=complete['tie_only_changes'],unchanged=34-complete['changed_months'],checked_unique_targets=total_checked,
        saved_vertex_trace_arithmetic_checked=True,fw_gradient_choices_recomputed=False,optimizer_calls=0,book_calls=0,
        historical_performance_improvement_proven=False,source_hashes=pins,rows=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args();report=audit()
    if args.write:
        directory=ROOT/OUTPUT;directory.mkdir(exist_ok=False)
        (directory/'receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        lines=['| 决策日 | 原k→新k | 新目标（占总资金） | 现金占比 | 训练分数严格提高 |','|---|---:|---|---:|---|']
        for row in report['rows']:
            names='；'.join(f"{p['ticker']} {p['quantity']}股 ({float(F(p['weight'])):.2%})"for p in row['holdings'])
            lines.append(f"| {row['decision_date']} | {row['old_k']}→{row['new_k']} | {names} | {float(F(row['cash_fraction'])):.2%} | {'是' if row['strict_training_improvement'] else '否'} |")
        lines+=['','仅同一封存月度资本下的训练候选诊断；未执行连续账户回测，不代表更高收益或更低回撤，未采用。']
        (directory/'table.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items()if k not in ('source_hashes','rows')},ensure_ascii=False))
