"""Saved DELTA trace scalar audit, without importing any fitting engine."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_base_delta_probe_independent_audit as scalar
FOLDER=ROOT/'data/cache/research/delta_three_cell_paired_trace_20260912_v2'
PAIRED=('paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent','paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent')


def main():
    sources={}
    def read(path,expected):
        path=str(Path(path).resolve());raw=Path(path).read_bytes()
        assert scalar.sha(raw)==expected,path
        assert path not in sources or sources[path]==expected
        sources[path]=expected
        return json.loads(raw)
    probe=read(FOLDER/'first_probe.json','1e39d8149e6d2d82853958bae413e75b608a02461a7b587da49f2a917a3cd519')
    result=probe['result'];plan=read(probe['plan_path'],probe['plan_sha256'])
    assert probe['plan_sha256']=='fb2e514516123efe67dffb92821410ce2eb52d3e757494c4dfaf517c7ea9b330'
    assert probe['selected']==plan['probe']
    for path,expected in result['source_hashes'].items():
        assert path not in sources or sources[path]==expected
        sources[path]=expected
    def verify():
        start=perf_counter()
        for path,expected in sources.items():assert scalar.sha(Path(path).read_bytes())==expected,path
        return perf_counter()-start
    verify_seconds=verify()
    context=read(result['context_path'],result['context_sha256'])
    checkpoint=read(result['checkpoint_path'],result['checkpoint_sha256'])
    task=probe['selected']['task']['task']
    assert checkpoint['task']==task and task in context['tasks']
    assert scalar.decode(checkpoint['result'])==result['original_result']
    old=result['original_result'];new=result['result']
    assert set(old)==set(new)
    assert {k:v for k,v in old.items() if k not in PAIRED}=={k:v for k,v in new.items() if k not in PAIRED}
    assert result['changed_result_fields']==[k for k in PAIRED if old[k]!=new[k]]
    inputs={key:scalar.decode(value['payload']) for key,value in context['prepared_inputs'].items()}
    panel=inputs['returns'];calendar=panel['index'];returns=dict(zip(panel['columns'],panel['column_values']))
    corrected=deepcopy(returns)
    for ticker,date,value in scalar.CORRECTIONS:
        i=calendar.index(date);assert corrected[ticker][i]==0.;corrected[ticker][i]=value
    windows=result['historical_window_weights'];contract=inputs['contract'];prior=None
    starts=list(range(contract['fit_days'],len(calendar)-contract['window_days']+1,contract['step_days']))
    assert len(windows)==len(starts)
    for start,record in zip(starts,windows):
        assert record['tickers']==task['tickers'].split(';')
        assert record['fit_start']==calendar[start-contract['fit_days']] and record['fit_end']==calendar[start-1]
        assert record['fit_row_count']==contract['fit_days']
        assert record['anchor_weights']==prior
        assert record['turnover_anchor_strength']==contract['turnover_anchor_strength']
        prior=record['weights']
    variants=[]
    for label,panel,saved,saved_result in [('original',returns,result['original_windows'],old),('corrected',corrected,result['corrected_windows'],new)]:
        rows,metrics=scalar.economics(panel,inputs['target_returns']['column_values'][0],inputs['incumbent_weights'],contract,windows)
        assert len(rows)==len(saved)
        error=max(abs(row[k]-observed[k]) for row,observed in zip(rows,saved) for k in row)
        paired_error=max(abs(metrics[k]-saved_result[k]) for k in PAIRED)
        assert max(error,paired_error)<=1e-12
        for start,row in zip(starts,saved):
            assert row['start']==calendar[start] and row['end']==calendar[start+contract['window_days']-1]
        variants.append(dict(variant=label,window_error=error,paired_error=paired_error,rows=rows,paired={k:metrics[k] for k in PAIRED}))
    for a,b in zip(result['original_windows'],result['corrected_windows']):
        assert {k:v for k,v in a.items() if not k.startswith('incumbent_')}=={k:v for k,v in b.items() if not k.startswith('incumbent_')}
    gap,=result['historical_loader_provenance_gaps']
    gap_path=str(ROOT/'config/ndx_cardinality_discovery_v1.yaml')
    assert gap['path']==gap_path and gap['expected_historical_sha256']=='1f85b1d848c5a884290b9a8edc89efd4a9d8520c271ad9581c33c3601e72d78e'
    assert gap['observed_current_sha256']==scalar.sha(Path(gap_path).read_bytes())
    found=[]
    def visit(value):
        if isinstance(value,dict):
            if 'path' in value and 'sha256' in value:
                path=str(Path(value['path']).resolve());expected=value['sha256']
                if sources.get(path)!=expected:
                    assert path==gap_path and expected==gap['expected_historical_sha256'];found.append(path)
            for key,item in value.items():
                if isinstance(key,str) and Path(key).is_absolute() and isinstance(item,str) and len(item)==64:
                    if sources.get(key)!=item:
                        assert key==gap_path and item==gap['expected_historical_sha256'];found.append(key)
                visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    visit(scalar.decode(context['source_evidence']));assert set(found)=={gap_path}
    for key in ('original_historical_provenance_verified','point_in_time_verified','promotion_allowed','no_fit_reuse'):assert result[key] is False
    assert result['old_trace_numerical_evaluation_count']==1 and result['new_input_fit_count']==0
    sources[str(Path(__file__).resolve())]=scalar.sha(Path(__file__).read_bytes())
    sources[str(Path(scalar.__file__).resolve())]=scalar.sha(Path(scalar.__file__).read_bytes())
    verify()
    report=dict(schema='ndx_delta_gap_probe_independent_audit_v1',source_hashes=sources,task=task,window_count=len(windows),
        original_full_result_exact_to_checkpoint=True,only_paired_four_fields_may_change=True,variants=variants,
        gap=gap,one_full_source_verification_seconds=verify_seconds,probe_elapsed_seconds=probe['elapsed_seconds'],
        no_fitter_or_evaluator_called=True,original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
    output=FOLDER/'first_probe_independent_audit_20260912.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=scalar.sha(output.read_bytes()),sources=len(sources),windows=len(windows),source_verify_seconds=verify_seconds,max_error=max(max(x['window_error'],x['paired_error']) for x in variants))))


if __name__=='__main__':main()
