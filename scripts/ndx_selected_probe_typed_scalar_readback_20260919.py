"""Limited saved-input readback; does not claim the old live source closure passes."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_base_delta_probe_independent_audit as scalar
FOLDER=ROOT/'data/cache/research/delta_selected_input_20260912_v1'


def main():
    sources={}
    def read(path,expected):
        path=str(Path(path).resolve());raw=Path(path).read_bytes();assert scalar.sha(raw)==expected,path
        assert path not in sources or sources[path]==expected;sources[path]=expected
        return json.loads(raw)
    probe=read(FOLDER/'first_probe.json','241ac517d78668761f32a25da68856cf396d28a1ef5591d9da993a0e2307607a')
    assert probe['plan_sha256']=='f0ff0242f08dcb62ceb19d5650db811fe8d0d83741f7ecc995b6a3945cf15266'
    plan=read(probe['plan_path'],probe['plan_sha256']);assert probe['selected']==plan['probe']
    row=plan['probe']['task'];task=row['task'];result=probe['result'];out=result['result']
    context=read(row['context_path'],row['context_sha256']);checkpoint=read(row['checkpoint_path'],row['checkpoint_sha256'])
    assert checkpoint['task']==task and task in context['tasks'] and result['original_task']==task
    old=scalar.decode(checkpoint['result']);assert out.keys()==old.keys()
    for key in ('tickers','holding_count','weight_spec'):assert out[key]==task[key]
    assert result['observed_runtime']==context['runtime']==row['runtime']
    assert result['old_input_numerical_evaluation_count']==0 and result['new_input_numerical_evaluation_count']==1
    assert result['original_result_reproduced'] is False and result['window_fit_reuse_performed'] is False
    inputs={key:scalar.decode(value['payload']) for key,value in context['prepared_inputs'].items()}
    assert set(inputs)=={'returns','target_returns','nominal_prices','universe','contract','incumbent_weights'}
    panel=inputs['returns'];calendar=panel['index'];returns=dict(zip(panel['columns'],panel['column_values']))
    for ticker,day,new in scalar.CORRECTIONS:
        position=calendar.index(day);assert returns[ticker][position]==0.;returns[ticker][position]=new
    contract=inputs['contract'];windows=result['historical_window_weights'];starts=list(range(contract['fit_days'],len(calendar)-contract['window_days']+1,contract['step_days']))
    assert len(windows)==len(starts)==result['new_fitted_window_count']==out['rolling_fit_window_count']
    prior=None
    for start,window in zip(starts,windows):
        assert window['tickers']==task['tickers'].split(';')
        assert window['fit_start']==calendar[start-contract['fit_days']] and window['fit_end']==calendar[start-1]
        assert window['fit_row_count']==contract['fit_days']
        assert window['anchor_weights']==prior and window['turnover_anchor_strength']==contract['turnover_anchor_strength']
        prior=window['weights']
    rows,metrics=scalar.economics(returns,inputs['target_returns']['column_values'][0],inputs['incumbent_weights'],contract,windows)
    assert len(rows)==len(result['new_windows'])
    window_error=max(abs(row[key]-saved[key]) for row,saved in zip(rows,result['new_windows']) for key in row)
    aggregate_error=max(abs(value-out[key]) for key,value in metrics.items())
    assert max(window_error,aggregate_error)<=1e-12
    for start,saved in zip(starts,result['new_windows']):
        assert saved['start']==calendar[start] and saved['end']==calendar[start+contract['window_days']-1]
    numeric_wholelot={key:value for key,value in out.items() if key.startswith('whole_lot_') and type(value) in (int,float)}
    assert all(math.isfinite(value) for value in numeric_wholelot.values())
    assert all(key in out for key in ('whole_lot_rebalance_trace_sha256','whole_lot_terminal_shares','whole_lot_initial_shares'))
    for key in ('point_in_time_verified','promotion_allowed','selection_performed','original_historical_provenance_verified'):assert result[key] is False
    for path in (Path(__file__).resolve(),Path(scalar.__file__).resolve()):sources[str(path)]=scalar.sha(path.read_bytes())
    for path,expected in sources.items():assert scalar.sha(Path(path).read_bytes())==expected
    report=dict(schema='ndx_selected_probe_limited_typed_scalar_readback_20260919_v1',source_hashes=sources,
        task=task,window_count=len(windows),scalar_windows=rows,scalar_twenty_metrics=metrics,
        maximum_window_error=window_error,maximum_aggregate_error=aggregate_error,
        full_new_result_schema_matches_original=True,nominal_result_fields_present_finite=True,
        nominal_execution_independently_replayed=False,new_full_v3_result_independently_reproduced=False,
        hard_typed_context_and_checkpoint_bytes_verified=True,historical_source_closure_verified=False,
        scope='SAVED_TYPED_INPUT_AND_FRACTIONAL_SCALAR_ONLY_PENDING_FULL_SOURCE_DRIFT_DIAGNOSIS',
        no_fitter_or_evaluator_called=True,point_in_time_verified=False,promotion_allowed=False)
    output=FOLDER/'limited_typed_scalar_readback_20260919.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=scalar.sha(output.read_bytes()),windows=len(windows),maximum_error=max(window_error,aggregate_error))))


if __name__=='__main__':main()
