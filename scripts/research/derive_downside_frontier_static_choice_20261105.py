"""Derive cash/noncash separation and frozen-score static choice; no D rerun."""
from pathlib import Path
import sys,json,statistics
from fractions import Fraction as F
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.audit_capped_training_frontier import evaluate,validate_binding
from backtest.capped_frontier_rerank_research import product_hash


def main():
 source=ROOT/'tmp/downside_frontier_preflight_20261105/result.json';original=json.loads(source.read_bytes())
 for name,h in original['source_hashes'].items():assert sha256((ROOT/name).read_bytes()).hexdigest()==h,name
 rows=[]
 for row in original['rows']:
  assert row['status']=='STATIC_FRONTIER_CHECK_COMPLETE'
  base='recent_continuous_baseline_20261026_v7' if row['window']=='early' else 'old_continuous_baseline_20261026_v9'
  raw=json.loads((ROOT/'tmp'/base/(row['decision_date']+'.selection.json')).read_bytes())['raw_selection'];args=validate_binding(raw)
  passing=[b for b in row['baskets'] if b['passes']];noncash=[b for b in passing if b['target_quantities']];cash=[b for b in passing if not b['target_quantities']]
  scores={tuple(sorted(b['target_quantities'].items())):evaluate(b['target_quantities'],args) for b in passing}
  incumbent=next((tuple(sorted(b['target_quantities'].items())) for b in passing if b['original_capped_raw']),None)
  if incumbent is not None:
   improved=[s for s in scores if scores[s]['product']>scores[incumbent]['product']]
   chosen=max(improved,key=lambda s:(scores[s]['product'],-scores[s]['notional'],s)) if improved else incumbent
  else:chosen=max(scores,key=lambda s:(scores[s]['product'],-scores[s]['notional'],s)) if scores else ()
  chosen_cash=F(1)-sum((q*F(args['prices'][s]) for s,q in chosen),F(0))/F(args['entered_cash'])
  rows.append(dict(window=row['window'],decision_date=row['decision_date'],passing_including_cash=len(passing),passing_cash=len(cash),passing_positive_holdings=len(noncash),no_positive_holding_basket=not noncash,positive_basket_holdings_min=min((len(b['target_quantities']) for b in noncash),default=None),positive_basket_holdings_median=statistics.median([len(b['target_quantities']) for b in noncash]) if noncash else None,positive_basket_holdings_max=max((len(b['target_quantities']) for b in noncash),default=None),positive_basket_cash_weights=[b['cash_weight'] for b in noncash],static_choice=dict(target_quantities=dict(chosen),holdings_count=len(chosen),cash_only=not chosen,cash_weight=str(chosen_cash),training_product_hash=product_hash(scores[chosen]['product']) if chosen in scores else None,incumbent_admitted=incumbent is not None)))
 summary=[]
 for label in ('early','later'):
  r=[x for x in rows if x['window']==label];counts=[x['passing_positive_holdings'] for x in r];chosen=[x['static_choice'] for x in r];cashweights=[float(F(x['cash_weight']))*100 for x in chosen]
  summary.append(dict(window=label,months=len(r),passing_cash_baskets=sum(x['passing_cash'] for x in r),passing_positive_baskets=sum(counts),no_positive_basket_months=sum(x['no_positive_holding_basket'] for x in r),positive_pass_count_min=min(counts),positive_pass_count_median=statistics.median(counts),positive_pass_count_max=max(counts),static_cash_months=sum(x['cash_only'] for x in chosen),static_holdings_min=min(x['holdings_count'] for x in chosen),static_holdings_median=statistics.median(x['holdings_count'] for x in chosen),static_holdings_max=max(x['holdings_count'] for x in chosen),static_cash_weight_min_pct=min(cashweights),static_cash_weight_median_pct=statistics.median(cashweights),static_cash_weight_max_pct=max(cashweights)))
 output=dict(source_result_sha256=sha256(source.read_bytes()).hexdigest(),source_result_preserved=True,summary=summary,rows=rows,choice_rule='Filter same saved baskets by unchanged D gate; retain admitted raw-capped incumbent unless strictly better product; otherwise product then lower notional then lexicographic quantities',scope='Static choices at original baseline accounts, not branch economic returns',search_calls=0,economic_runs=0)
 path=source.parent/'cash_separated_static_choices.json';path.write_text(json.dumps(output,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
