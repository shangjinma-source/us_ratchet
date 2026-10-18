"""Inspect saved best-by-k targets; no optimizer, book, new candidates or prices."""
import argparse
from collections import defaultdict
from fractions import Fraction as F
from hashlib import sha256
import json
import math
from pathlib import Path
from scripts.audit_monthly_selection_endpoint import PREPARED, PREPARED_SHA, require

ROOT=Path(__file__).resolve().parents[1]
OUTCOME='tmp/daily_exclusion_B0_20261016_v1/outcome.json'
OUTCOME_SHA='b60767394f091b5107186a01aa7747e0ef467407fc67f2901a410920ddf13e0f'
OUTPUT='tmp/saved_cardinality_competition_audit_20261016_v1'


def inspect_target(target,prices,cash,metadata):
    q=target['quantities'];require(all(type(v)is int and v>0 for v in q.values()),'INVALID_QUANTITIES')
    weights={s:prices[s]*v/cash for s,v in q.items()}
    require(target['actual_k']==len(q),'ACTUAL_K_MISMATCH')
    require({s:F(v) for s,v in target['actual_weights'].items()}==weights,'SAVED_WEIGHT_MISMATCH')
    notional=sum((prices[s]*v for s,v in q.items()),F(0));residual=cash-notional
    require(residual>=0 and F(target['residual_cash'])==residual and F(target['fees'])==0,'SAVED_CASH_MISMATCH')
    require(F(target['notional'])==notional,'SAVED_NOTIONAL_MISMATCH')
    ordered=sorted(weights.values(),reverse=True);invested=sum(ordered,F(0))
    score=target['training_mean_net_log_wealth'];require(type(score)in(int,float)and math.isfinite(score),'INVALID_SAVED_SCORE')
    return dict(actual_k=len(q),holdings={metadata[s]['ticker']:v for s,v in q.items()},
        weights={metadata[s]['ticker']:str(v) for s,v in weights.items()},
        top1_total_capital_weight=str(ordered[0]) if ordered else '0',top3_total_capital_weight=str(sum(ordered[:3],F(0))),
        effective_stock_count=str(invested**2/sum((v*v for v in ordered),F(0))) if ordered else '0',
        cash_fraction=str(residual/cash),saved_mean_log_score=score)


def exact_product(target,args,cash):
    prices={s:F(v) for s,v in args['prices'].items()};q=target['quantities']
    residual=cash-sum((prices[s]*v for s,v in q.items()),F(0))
    product=math.prod((residual+sum((prices[s]*v*F(scenario[s]) for s,v in q.items()),F(0)))/cash for scenario in args['training_scenarios'])
    saved=target.get('training_gross_growth_product')
    require(saved is None or F(saved)==product,'SAVED_PRODUCT_MISMATCH')
    return product


def inspect_month(window,selection):
    result=selection['search_result'];args=window['search_arguments'];cash=F(selection['investable_equity'])
    require(result['decision_date']==window['decision_date'],'DECISION_MISMATCH')
    require(F(result['fee_bps'])==F(args['fee_bps'])==0,'NONZERO_FEES_UNSUPPORTED')
    require(F(result['entered_cash'])==cash,'CASH_MISMATCH')
    prices={s:F(v)for s,v in args['prices'].items()};targets=result['best_by_k']
    require(targets['1']==result['selected'],'SELECTED_NOT_SAVED_SINGLE')
    evidence={p['k']:p for p in result['per_k']};lanes=result['local_search_budget_by_k']
    by_k=[]
    for key,target in targets.items():
        k=int(key);metrics=inspect_target(target,prices,cash,args['metadata']);require(k==metrics['actual_k'],'K_MISMATCH')
        metrics['k']=k
        metrics['search_evidence']=evidence.get(k)
        metrics['budget_evidence']=lanes.get(key)
        by_k.append(metrics)
    multiple=[r for r in by_k if r['k']>=2];require(multiple,'NO_SAVED_MULTISTOCK_TARGETS')
    best=max(multiple,key=lambda r:r['saved_mean_log_score'])
    one=next(r for r in by_k if r['k']==1)
    exact_one=exact_product(targets['1'],args,cash);exact_multi=exact_product(targets[str(best['k'])],args,cash)
    relation='GREATER' if exact_one>exact_multi else 'EQUAL' if exact_one==exact_multi else 'LESS'
    return dict(decision_date=window['decision_date'],active_date=window['active_date'],year=window['active_date'][:4],
        candidate_count=len(prices),saved_k_count=len(targets),single=one,best_saved_multiple=best,
        single_minus_multi_mean_log_score=one['saved_mean_log_score']-best['saved_mean_log_score'],
        single_to_multi_scenario_product_ratio=str(exact_one/exact_multi),single_vs_multi_exact=relation,
        best_multiple_rank_basis='SAVED_FLOAT_MEAN_LOG_SCORES; FINALISTS_EXACT_PRODUCT_RECHECKED',
        single_quantity_optimum_established=result['single_security_quantity_optimum_established'],
        all_affordable_k_initialized=result['all_affordable_k_initialized'],global_optimum_established=result['global_optimum_established'],
        visited_multistock_states=sum(p['visited_states'] for p in result['per_k']if p['k']>=2),
        exhausted_multistock_lanes=sum(bool(v.get('support_enumeration_complete')) for k,v in lanes.items()if int(k)>=2),
        budget_stopped_multistock_lanes=sum(v.get('stop_reason')=='LANE_BUDGET_STOPPED' for k,v in lanes.items()if int(k)>=2),
        per_k=by_k)


def build(root=ROOT):
    root=Path(root);pins={}
    def read(path,h):
        raw=(root/path).read_bytes();require(sha256(raw).hexdigest()==h,'SOURCE_CHANGED:'+path);pins[path]=h
        return json.loads(raw)
    prepared=read(PREPARED,PREPARED_SHA);outcome=read(OUTCOME,OUTCOME_SHA)
    require(outcome['status']=='COMPLETE','OUTCOME_INCOMPLETE')
    for path,h in prepared['source_hashes'].items():
        require(sha256((root/path).read_bytes()).hexdigest()==h,'SOURCE_CHANGED:'+path);pins[path]=h
    windows={w['decision_date']:w for w in prepared['windows']}
    selections=[r['selection']for r in outcome['provider_audit']if r.get('selection')]
    require(len(selections)==len(windows) and {s['decision_date']for s in selections}==set(windows),'MONTH_COVERAGE')
    rows=[inspect_month(windows[s['decision_date']],s)for s in selections]
    groups=defaultdict(list)
    for row in rows:groups[row['year']].append(row)
    summary=[dict(year=year,months=len(group),single_beats_saved_multi=sum(r['single_vs_multi_exact']=='GREATER'for r in group),
        minimum_mean_log_gap=min(r['single_minus_multi_mean_log_score']for r in group),maximum_mean_log_gap=max(r['single_minus_multi_mean_log_score']for r in group),
        globally_proven_months=sum(r['global_optimum_established']for r in group))for year,group in sorted(groups.items())]
    for path in ['scripts/audit_saved_cardinality_competition.py','scripts/audit_monthly_selection_endpoint.py']:
        pins[path]=sha256((root/path).read_bytes()).hexdigest()
    return dict(status='PASS_SAVED_CARDINALITY_INSPECTION',rows=rows,annual_summary=summary,source_hashes=pins,
        optimizer_calls=0,book_calls=0,new_candidates_evaluated=0,independent_oos=False,point_in_time_certified=False,
        conclusion='Concentration beats saved visited multi-stock targets under this training objective; global multi-stock superiority or inferiority remains unknown.',
        limitations=['Best multi-stock uses saved float score ordering; exact arithmetic rechecks the two finalists, not all unvisited states.',
            'k counts positive shares, not meaningful diversification; top weights and effective count expose concentration.',
            'Training score differences are neither annual returns nor future outperformance.',
            'Fixed observed domain excluding TRI; no historical PIT or independent validation claim.'])


def table(report):
    lines=['| 决策日 | 已保存k数 | 最佳多股k | 单股-多股训练均值log差 | 多股最大权重 | 多股有效只数 | 多股停止预算的k数 |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for r in report['rows']:
        m=r['best_saved_multiple'];lines.append(f"| {r['decision_date']} | {r['saved_k_count']} | {m['k']} | {r['single_minus_multi_mean_log_score']:.6f} | {float(F(m['top1_total_capital_weight'])):.2%} | {float(F(m['effective_stock_count'])):.2f} | {r['budget_stopped_multistock_lanes']} |")
    return '\n'.join(lines)+'\n\n训练目标偏好已访问的集中方案，不等于证明分散无效；未访问整股组合仍未知，未重跑搜索或回测。\n'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args();report=build()
    if args.write:
        directory=ROOT/OUTPUT;directory.mkdir(exist_ok=False)
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (directory/'table.md').write_text(table(report),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],annual_summary=report['annual_summary']),ensure_ascii=False))
