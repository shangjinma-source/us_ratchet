"""Same frozen selector on current inputs; research signal, no live mandate."""
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

from scripts.research.screen_profitability_roa_continuous_20261106 import build_decision

ROOT=Path(__file__).resolve().parents[2]


def main():
    pins={}
    def read(name):
        raw=(ROOT/name).read_bytes();pins[name]=sha256(raw).hexdigest()
        return json.loads(raw)
    inputs=read('tmp/roa_november_inputs_20261106.json')
    assert not inputs['training_dependency_exceptions']
    for name,expected in inputs['source_hashes'].items():
        assert sha256((ROOT/name).read_bytes()).hexdigest()==expected, 'INPUT_SOURCE_CHANGED:'+name
        pins[name]=expected
    raw_manifest=read('tmp/monthly_recovery_20261103/training_scoped_publication/manifest.json')
    ranked=[]
    for candidate in raw_manifest['candidates']:
        assert candidate['status']=='READY_CONDITIONAL'
        prices=list(map(Fraction,candidate['raw_close']))
        assert len(prices)==253 and all(p>0 for p in prices)
        ranked.append(dict(security_id=candidate['security_id'],issuer_id=candidate['issuer_id'],
            ticker=candidate['ticker'],ratio_exact=str(prices[-22]/prices[-253])))
    ranked.sort(key=lambda r:(-Fraction(r['ratio_exact']),r['security_id']))
    for rank,row in enumerate(ranked,1):row['rank']=rank
    financial=[]
    for row in inputs['rows']:
        financial.append(dict(row.get('financial',dict(status=row['status'])),security_id=row['security_id']))
    panel=dict(results=[dict(cutoff=inputs['financial_cutoff'],rows=financial)])
    roster=dict(decision_date=inputs['decision_date'],ranked=ranked)
    selection=build_decision(roster,panel,'PROFITABLE')
    comparison=read('tmp/roa_current_qqq_raw_20261106/comparison.json')
    raw_path='tmp/roa_current_qqq_raw_20261106/QQQ.response.bin'
    assert sha256((ROOT/raw_path).read_bytes()).hexdigest()==comparison['source_sha256']
    pins[raw_path]=comparison['source_sha256']
    assert comparison['last_date']=='2026-11-05' and not comparison['differences_over_cent_rounding']
    assert comparison['raw_risk_on']==inputs['market_state_cache_preflight']['risk_on']
    selected=selection['selected']
    assert len(selected)<=10 and len({r['issuer_id'] for r in selected})==len(selected)
    for source in ('scripts/research/screen_profitability_roa_continuous_20261106.py',
                   'scripts/research/describe_annual_quality_local_20261106.py'):
        pins[source]=sha256((ROOT/source).read_bytes()).hexdigest()
    output=dict(status='CURRENT_ROA_SIGNAL_RESEARCH_ONLY',selection=selection,
        market_state=dict(as_of=comparison['last_date'],risk_on=comparison['raw_risk_on'],
            rule='QQQ_SMA200_TWO_COMPLETED_CLOSES_NEXT_OPEN'),
        selected_weights={r['security_id']:'1/10' for r in selected},
        effective_weights={r['security_id']:'1/10' for r in selected} if comparison['raw_risk_on'] else {},
        source_hashes=pins,production_activated=False,executable=False,orders_created=False,
        pending=['Complete full integer-account economic admission',
                 'Account-specific stopped/pending state and corporate-action/quote admission',
                 'Production activation with actual holdings and immutable target binding',
                 'Research-conditional universe and financial revision limitations remain'])
    (ROOT/'tmp/roa_november_signal_20261106.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(dict(status=output['status'],selected=[r['ticker'] for r in selected],
        market_state=output['market_state']),indent=2))


if __name__=='__main__':main()
