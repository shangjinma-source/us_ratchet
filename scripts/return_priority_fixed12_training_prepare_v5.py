"""Finish conditionally accepted parent-price inputs; prepare arguments, no search."""
import argparse
import csv
import hashlib
import json
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    pins={}
    def read(name,expected=None):
        raw=(ROOT/name).read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if expected and digest!=expected:raise ValueError('Source hash differs: '+name)
        pins[name]=digest
        return raw
    result=json.loads(read('tmp/fixed12_training_prepare_20261014_v4/prepared.json','7eaea9709cd06195b0328383e5a612a9836e5e046e8c6d69c4a9df3f188e02a8'))
    for name,digest in result['source_hashes'].items():read(name,digest)
    evidence=json.loads(read('tmp/nonsimple_price_coordinate_independent_20261014_v1/comparison.json','47600c994ffd9b43a2aaeedf5bd60b04ef8002043d8a9a1b80f7cee921bc3f3f'))
    read('tmp/nonsimple_price_coordinate_independent_20261014_v1/findings.json')
    for name,digest in evidence['source_hashes'].items():read(name,digest)
    read('tmp/fixed12_official_actions_20261014_v1/non_simple_action_web_observations.json')
    sources={}
    for ticker in ('HON','CMCSA','ILMN'):
        paths=[p for p in evidence['source_hashes'] if 'root_price_byte_archive_' in p and Path(p).name.startswith(ticker+'.') and p.endswith('.csv')]
        if len(paths)!=1:raise ValueError('Whole archive selection ambiguous')
        rows=list(csv.DictReader(read(paths[0]).decode('utf-8-sig').splitlines()))
        closes={r['Date']:r['Close'] for r in rows}
        if len(closes)!=len(rows):raise ValueError('Duplicate archive date')
        sources[ticker]=(paths[0],closes)
    for w in result['windows']:
        days=w['training_dates']
        for row in w['candidates']:
            if row['ticker'] not in sources:continue
            path,closes=sources[row['ticker']]
            values=[closes.get(d) for d in days]
            if any(v is None or Fraction(v)<=0 for v in values):raise ValueError('Incomplete archive training')
            if row['ticker']=='ILMN' and w['decision_cutoff']<='2024-06-25':raise ValueError('Unreviewed ILMN holding event exposure')
            row['previous_quote_coordinate_blockers']=row['blockers']
            row.update(blockers=[],status='READY_CONDITIONAL',training_source=path,
                training_basis='CONDITIONAL_ARCHIVED_WITH_NOMINAL_OVERLAP',training_close=values,
                training_gross=[str(Fraction(values[i+21])/Fraction(values[i])) for i in range(0,252,21)],
                missing_training_dates=[],decision_cost=values[-1],decision_cost_factor='1',
                decision_cost_basis='CONDITIONAL_ARCHIVED_WITH_NOMINAL_OVERLAP_NOT_OFFICIAL_NOMINAL_CERTIFICATION',
                return_scope='PARENT_ONLY_PRICE_RETURN_EXCLUDES_DISTRIBUTED_RIGHTS',
                share_multiplier_applied=False,distributed_rights_valued=False,
                source_recovery_evidence='tmp/nonsimple_price_coordinate_independent_20261014_v1/comparison.json')
        if any(r['blockers'] for r in w['candidates']):raise ValueError('Unresolved window, no search arguments authorized')
        included=[r for r in w['candidates'] if r['status']=='READY_CONDITIONAL']
        if len({r['security_id'] for r in included})!=len(included):raise ValueError('Duplicate SID')
        if any(not r['security_id'] or not r['issuer_id'] or Fraction(r['decision_cost'])<=0 or len(r['training_gross'])!=12 for r in included):raise ValueError('Invalid eligible candidate')
        args=dict(prices={r['security_id']:str(Fraction(r['decision_cost'])) for r in included},
            metadata={r['security_id']:dict(ticker=r['ticker'],issuer_id=r['issuer_id']) for r in included},
            entered_cash='20000',fee_bps='0',minimum_cash_buffer='0',
            training_scenarios=[{r['security_id']:r['training_gross'][i] for r in included} for i in range(12)],
            scenario_dates=w['scenario_end_dates'],decision_date=w['decision_cutoff'],
            max_objective_evaluations=8192,fixed_seed='fresh-quantity-20261014-v1')
        w.update(status='READY_CONDITIONAL',ready_count=len(included),included_count=len(included),
            exclusions=[dict(ticker=r['ticker'],security_id=r['security_id'],reasons=r['exclusion_reasons']) for r in w['candidates'] if r['status']!='READY_CONDITIONAL'],
            coverage=[dict(ticker=r['ticker'],security_id=r['security_id'],issuer_id=r['issuer_id'],status=r['status']) for r in w['candidates']],search_arguments=args)
    result.update(status='ALL_TWELVE_READY_CONDITIONAL_PENDING_INDEPENDENT_REVIEW',research_only=True,future_outcome_used=False,
        scope='Fixed twelve retrospective monthly decisions; price-only, not independent OOS or certified PIT. No search executed.',
        source_hashes=pins)
    result['training_price_only_limitations'].append('HON/CMCSA/ILMN use whole conditional archive. ILMN training retains parent ex-distribution price drop and excludes GRAL rights; no 1028/1000 share conversion.')
    pins[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for name,digest in pins.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during prepare')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    path=Path(args.output).resolve()
    if path.exists() or (ROOT/'tmp').resolve() not in path.parents:raise ValueError('Create-only tmp required')
    result=prepare();path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps([dict(date=w['decision_cutoff'],included=w['included_count'],exclusions=w['exclusions']) for w in result['windows']]))
