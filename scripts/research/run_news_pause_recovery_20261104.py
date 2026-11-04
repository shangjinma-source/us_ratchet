"""New authorized fixed action comparison; reuses archived model output, no inference."""
import json
from pathlib import Path
from fractions import Fraction
from scripts.research.run_news_five_case_v1 import ROOT, BASE, read, save, digest, replay

def run(case):
    folder=ROOT/'tmp/news_five_case_execution_20261029'/case
    review=read(folder/'semantic_review.json')
    assert all(review.get(k) is True for k in ('semantic_pass','action_evidence_contiguous_pass','development_replay_permitted'))
    for relative, expected in review['source_hashes'].items():
        assert digest(ROOT/relative)==expected, relative
    spec=read(folder/'preflight.json')
    inputs=read(ROOT/BASE/'execution_inputs.json')
    original=read(ROOT/BASE/'book.json')
    a=read(folder/'A_run1/result.json')['rows'][0]
    b=read(folder/'B_run1/answer.json')['B_signal']
    pause=dict(a,action='PAUSE_BUY',buy_fraction='0/1',holding_fraction='1/1')
    output=ROOT/'tmp/news_pause_recovery_three_20261104'/case
    output.mkdir(parents=True,exist_ok=False)
    summary={'case':spec['case_id'],'days':spec['days'],'new_authorization':'2026-11-04 fixed no-model action comparison; old inference contract not restarted','rows':[]}
    for cost in ('0','5'):
        results={name:replay(inputs,spec,arm,row,b,cost) for name,arm,row in [('BASELINE','BASELINE',a),('MODEL_ACTION','A',a),('PAUSE_ONLY','A',pause)]}
        base=results['BASELINE']['book']['daily_ledger']
        if cost=='5':
            old={r['date']:r for r in original['daily_ledger']}
            for row in base:
                assert all(row[k]==old[row['date']][k] for k in ('cash','shares','equity'))
        for name,result in results.items():
            save(output/(cost+'bp_'+name+'.json'),result)
            assert result['trace'][-1]['news_active'] is False
            peak=Fraction(spec['initial']['equity']);dd=Fraction(0)
            for row in result['book']['daily_ledger']:
                equity=Fraction(row['equity']);peak=max(peak,equity);dd=max(dd,1-equity/peak)
            summary['rows'].append(dict(cost_bps=cost,arm=name,delta_usd=float(equity-Fraction(base[-1]['equity'])),return_pct=float((equity/Fraction(spec['initial']['equity'])-1)*100),drawdown_pct=float(dd*100),fills=len([r for r in result['book']['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED'])))
    summary['input_hashes']={str(p.relative_to(ROOT)):digest(p) for p in [folder/'preflight.json',folder/'A_run1/result.json',ROOT/BASE/'execution_inputs.json',Path(__file__)]}
    save(output/'summary.json',summary)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':
    for case in ('DLTR_20220825_v2','PDD_20230320','PDD_20230526'):run(case)

