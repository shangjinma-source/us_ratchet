"""New authorized fixed action comparison; reuses archived model output, no inference."""
import json
from pathlib import Path
from fractions import Fraction
from copy import deepcopy
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
    historical_spec=deepcopy(spec)
    sid=spec['security_id'];day=spec['days'][0]
    held=spec['initial']['shares'].get(sid,0)
    close=Fraction(inputs['assembled']['close_prices'][sid][day])
    conversion=held*close
    spec['initial']['shares'][sid]=0
    spec['initial']['cash']=str(Fraction(spec['initial']['cash'])+conversion)
    spec['initial']['stock_value']=str(Fraction(spec['initial']['stock_value'])-conversion)
    spec['held']=0
    assert Fraction(spec['initial']['cash'])+Fraction(spec['initial']['stock_value'])==Fraction(spec['initial']['equity'])
    assert spec['risk_state']==historical_spec['risk_state']

    a=read(folder/'A_run1/result.json')['rows'][0]
    b=read(folder/'B_run1/answer.json')['B_signal']
    pause=dict(a,action='PAUSE_BUY',buy_fraction='0/1',holding_fraction='1/1')
    output=ROOT/'tmp/news_synthetic_entry_20261104_v2'/case
    output.mkdir(parents=True,exist_ok=False)
    save(output/'initial_conversion.json',dict(historical=historical_spec,synthetic=spec,converted_quantity=held,previous_close=str(close),cash_added=str(conversion),actual_sale=False))
    summary={'case':spec['case_id'],'days':spec['days'],'scope':'SYNTHETIC_ENTRY_FROZEN_ACTION_TRANSFER_NOT_NEW_AI_JUDGMENT','rows':[]}
    for cost in ('0','5'):
        results={name:replay(inputs,spec,arm,row,b,cost) for name,arm,row in [('BASELINE','BASELINE',a),('MODEL_ACTION','A',a),('PAUSE_ONLY','A',pause)]}
        base=results['BASELINE']['book']['daily_ledger']
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

