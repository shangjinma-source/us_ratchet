"""67 already-reviewed inputs, arithmetic only; no selection search or book run."""
from pathlib import Path
import sys,json
from hashlib import sha256
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from docs.candidates.qqq_risk_budget_offline_limits import configure_offline_fraction_serialization
from docs.candidates.qqq_risk_budget_exact import scale_targets_to_qqq_risk


def main():
    policy=configure_offline_fraction_serialization()
    path=ROOT/'tmp/risk_budget_64d_inventory_20261105/risk_inputs.json'
    assert sha256(path.read_bytes()).hexdigest()=='c1fbdb4891d573be29657238dc8f4718d7685edb6769edbada1e3ceeae1c4592'
    document=json.loads(path.read_bytes())
    for name,digest in document['source_hashes'].items():
        assert sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    results=[];maximum_digits=0
    for row in document['windows']:
        assert row['status']=='CONDITIONAL_INPUT_READY'
        result=scale_targets_to_qqq_risk(**row['arguments'])
        # Round-trip the exact emitted fractions as the downstream independent reader will.
        for key in ('portfolio_variance','qqq_variance','scale_squared_exact'):
            text=result[key];assert str(Fraction(text))==text
            maximum_digits=max(maximum_digits,*(len(part.lstrip('-')) for part in text.split('/')))
        results.append(dict(window=row['window'],decision_date=row['decision_date'],result=result))
    assert len(results)==67
    output=dict(status='67_REAL_INPUT_SIZING_AND_EXACT_ROUNDTRIP_PASS',serialization_policy=policy,
        maximum_fraction_component_digits=maximum_digits,economic_runs=0,rows=results,
        source_hashes={path.relative_to(ROOT).as_posix():sha256(path.read_bytes()).hexdigest(),
            **{name:sha256((ROOT/name).read_bytes()).hexdigest() for name in [
                'docs/candidates/qqq_risk_budget_exact.py','docs/candidates/qqq_risk_budget_offline_limits.py',
                'scripts/research/preflight_qqq_risk_budget_sizing_20261105.py']}})
    target=path.parent/'sizing_preflight.json'
    target.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=output['status'],rows=len(results),maximum_fraction_component_digits=maximum_digits,economic_runs=0)))

if __name__=='__main__':main()
