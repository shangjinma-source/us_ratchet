"""Read externally indexed actual DELTA outputs; scalar oracle, never fitting."""
from copy import deepcopy
import json
from pathlib import Path
import platform
import sys
import numpy as np
import pandas as pd
import scipy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_base_delta_probe_independent_audit as scalar
FOLDER=ROOT/'data/cache/research/delta_paired_snapshot_20260912_v1'
PAIRED=('paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent','paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent')


def main():
    sources={}
    def merge(mapping):
        for p,h in mapping.items():
            p=str(Path(p).resolve());assert p not in sources or sources[p]==h;sources[p]=h
    def read(p,h):
        merge({p:h});raw=Path(p).read_bytes();assert scalar.sha(raw)==h,p;return json.loads(raw)
    def verify():
        for p,h in sources.items():assert scalar.sha(Path(p).read_bytes())==h,p
    index=read(FOLDER/'tasks/index_f70142afc0d36ab67046239566c8037d5f2652c0e149359a588f71440b22f362.json',
               'fcbdbb99dca8b11465106f29f58ec1424de1fcc3df3783f4d2d67d63491aceb9')
    assert index['planned']==614 and len(index['completed'])==2 and index['status']=='PARTIAL'
    final=index['finalization'];assert final['completed']==2 and final['source_closure_verified'] is True
    merge(final['source_hashes']);merge(final['additional_provenance_hashes']);verify()
    assert index['manifest']['sha256']=='a784d343acf4363530b2a452ef8e11709b5d5275a177fdd86dc7b4592918b891'
    manifest=read(index['manifest']['path'],index['manifest']['sha256'])
    rows={r['new_job_id']:r for r in manifest['tasks']};assert len(rows)==614
    runtime=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__)
    reports=[];modes=[]
    for entry in index['completed']:
        saved=read(entry['path'],entry['sha256']);row=rows[saved['new_job_id']];r=saved['result']
        assert saved['original']==row and saved['manifest_sha256']==index['manifest']['sha256']
        assert saved['manifest_path']==index['manifest']['path']
        context=read(row['context_path'],row['context_sha256']);old=read(row['checkpoint_path'],row['checkpoint_sha256'])
        assert old['task']==row['task'] and row['task'] in context['tasks']
        assert context['runtime']==row['runtime']==runtime
        assert scalar.decode(old['result'])==r['original_result']
        assert {k:v for k,v in r['result'].items() if k not in PAIRED}=={k:v for k,v in r['original_result'].items() if k not in PAIRED}
        if saved['mode']=='EXTERNAL_COMPLETED_PROBE_IMPORTED_NO_REPEAT_TRACE':
            assert saved['imported_probe_sha256']=='1e39d8149e6d2d82853958bae413e75b608a02461a7b587da49f2a917a3cd519'
            probe=read(saved['imported_probe_path'],saved['imported_probe_sha256']);expected=deepcopy(probe['result']);merge(expected.pop('source_hashes'))
            assert expected==r
        else:assert saved['mode']=='ORIGINAL_V3_TRACE_RECOVERED'
        modes.append(saved['mode'])
        inputs={k:scalar.decode(v['payload']) for k,v in context['prepared_inputs'].items()}
        panel=inputs['returns'];calendar=panel['index'];returns=dict(zip(panel['columns'],panel['column_values']));changed=deepcopy(returns)
        for ticker,day,new in scalar.CORRECTIONS:
            i=calendar.index(day);assert changed[ticker][i]==0.;changed[ticker][i]=new
        contract=inputs['contract'];starts=list(range(contract['fit_days'],len(calendar)-contract['window_days']+1,contract['step_days']))
        windows=r['historical_window_weights'];assert len(starts)==len(windows);prior=None
        for start,window in zip(starts,windows):
            assert window['tickers']==row['task']['tickers'].split(';')
            assert window['fit_start']==calendar[start-contract['fit_days']] and window['fit_end']==calendar[start-1]
            assert window['fit_row_count']==contract['fit_days']
            anchored=row['task']['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor'
            assert window['anchor_weights']==(prior if anchored else None)
            assert window['turnover_anchor_strength']==(contract['turnover_anchor_strength'] if anchored else 0.)
            prior=window['weights']
        variants=[]
        for label,data,savedrows,savedresult in [('original',returns,r['original_windows'],r['original_result']),('corrected',changed,r['corrected_windows'],r['result'])]:
            calculated,metrics=scalar.economics(data,inputs['target_returns']['column_values'][0],inputs['incumbent_weights'],contract,windows)
            assert len(calculated)==len(savedrows)
            error=max(abs(x[k]-y[k]) for x,y in zip(calculated,savedrows) for k in x)
            paired_error=max(abs(metrics[k]-savedresult[k]) for k in PAIRED);assert max(error,paired_error)<=1e-12
            for start,window in zip(starts,savedrows):assert (window['start'],window['end'])==(calendar[start],calendar[start+contract['window_days']-1])
            variants.append(dict(variant=label,window_error=error,paired_error=paired_error,windows=calculated))
        for x,y in zip(r['original_windows'],r['corrected_windows']):
            assert {k:v for k,v in x.items() if not k.startswith('incumbent_')}=={k:v for k,v in y.items() if not k.startswith('incumbent_')}
        gap,=r['historical_loader_provenance_gaps'];assert gap['path']==str(ROOT/'config/ndx_cardinality_discovery_v1.yaml')
        assert gap['expected_historical_sha256']=='1f85b1d848c5a884290b9a8edc89efd4a9d8520c271ad9581c33c3601e72d78e'
        assert gap['observed_current_sha256']==scalar.sha(Path(gap['path']).read_bytes())
        for value in (saved,r):
            for flag in ('original_historical_provenance_verified','point_in_time_verified','promotion_allowed'):assert value[flag] is False
        reports.append(dict(new_job_id=saved['new_job_id'],task=row['task'],variants=variants,gap=gap))
    assert sorted(modes)==['EXTERNAL_COMPLETED_PROBE_IMPORTED_NO_REPEAT_TRACE','ORIGINAL_V3_TRACE_RECOVERED']
    merge({str(Path(__file__).resolve()):scalar.sha(Path(__file__).read_bytes()),str(Path(scalar.__file__).resolve()):scalar.sha(Path(scalar.__file__).read_bytes())});verify()
    report=dict(schema='ndx_delta_snapshot_first_two_independent_audit_v1',source_hashes=sources,planned=614,completed=2,
        tasks=reports,actual_runtime=runtime,imported_full_result_exact=True,all_old_results_exact_to_checkpoints=True,
        all_window_scalars_independently_verified=True,no_fitter_or_evaluator_called=True,original_historical_provenance_verified=False,
        point_in_time_verified=False,promotion_allowed=False)
    output=FOLDER/'first_two_independent_audit_20260912.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=scalar.sha(output.read_bytes()),sources=len(sources),max_error=max(max(v['window_error'],v['paired_error']) for t in reports for v in t['variants']))))


if __name__=='__main__':main()
