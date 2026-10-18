"""Independent scalar and Decimal Close readback of two hard-bound selected tasks."""
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_exact_price_cache_drift_research as drift
from backtest import ndx_legacy_close_accounting_oracle_research as ledger
from scripts import ndx_base_delta_probe_independent_audit as scalar
FOLDER=ROOT/'data/cache/research/selected_delta_drift_snapshot_20260919_v1'
INDEX=FOLDER/'tasks/index_73877ebf6d105237112af86876a756a0f4af7a25ad9c109308b595468795b641.json'
INDEX_SHA='c149dd9c151d97536268e3b4296d507cb41c27ba7cb65bbf97e1f914557623ef'
MANIFEST_SHA='beb22a53d179a725e359272273b14c8fc6ed6fe669e0fac574c0a4ff5f45fb9e'
LOADED={str(p):drift.file_sha(p) for p in (Path(__file__).resolve(),drift.SOURCE,Path(ledger.__file__).resolve(),Path(scalar.__file__).resolve())}


def compare(computed,saved,tolerance):
    errors={}
    for key,value in computed.items():
        observed=saved[key]
        if type(value) in (float,int) and type(value) is not bool:
            if type(observed) not in (float,int) or not math.isfinite(observed):raise ValueError('Nonfinite or boolean scalar')
            error=abs(value-observed)
            if error>tolerance:raise ValueError('Independent scalar differs: '+key)
            errors[key]=error
        elif type(value)!=type(observed) or value!=observed:raise ValueError('Independent state differs: '+key)
    return errors


def build():
    sources=dict(LOADED)
    def include(mapping):
        for p,h in mapping.items():
            if p in sources and sources[p]!=h:raise ValueError('Conflicting source')
            sources[p]=h
    def read(p,h):
        p=str(Path(p).resolve())
        if drift.file_sha(p)!=h:raise ValueError('External SHA differs')
        include({p:h});return json.loads(Path(p).read_bytes())
    index=read(INDEX,INDEX_SHA);manifest=read(FOLDER/'manifest.json',MANIFEST_SHA)
    if index['manifest']!={'path':str(FOLDER/'manifest.json'),'sha256':MANIFEST_SHA} or len(index['completed'])!=2 or index['planned']!=11254:
        raise ValueError('Hard first-two denominator differs')
    include(index['finalization']['historical_expected_source_hashes']);include(index['finalization']['additional_provenance_hashes'])
    contract=drift.load_contract();drift.verify_expected_sources(sources,contract)
    planned={r['new_job_id']:r for r in manifest['tasks']};reports=[]
    for entry in index['completed']:
        task_file=read(entry['path'],entry['sha256']);row=planned[task_file['new_job_id']]
        if task_file['original']!=row:raise ValueError('Saved task differs from hard plan')
        result=task_file['result'];context=read(row['context_path'],row['context_sha256']);task=row['task']
        if task not in context['tasks'] or result['original_task']!=task:raise ValueError('Original task binding differs')
        inputs={k:scalar.decode(v['payload']) for k,v in context['prepared_inputs'].items()}
        ret=inputs['returns'];returns=dict(zip(ret['columns'],ret['column_values']));calendar=ret['index'];c=inputs['contract']
        for ticker,date,changed in [('GOOG','2022-07-18',-.025335378898117544),('GOOGL','2022-07-18',-.024580059928059006),('FTNT','2022-06-23',.019968386675822902)]:
            pos=calendar.index(date)
            if returns[ticker][pos]!=0.:raise ValueError('Original evidenced cell differs')
            returns[ticker][pos]=changed
        windows=result['historical_window_weights']
        rows,metrics=scalar.economics(returns,inputs['target_returns']['column_values'][0],inputs['incumbent_weights'],c,windows)
        if len(rows)!=len(result['new_windows']):raise ValueError('Window denominator differs')
        errors=compare(metrics,result['result'],1e-12)
        for computed,saved in zip(rows,result['new_windows']):compare(computed,saved,1e-12)
        starts=list(range(c['fit_days'],len(calendar)-c['window_days']+1,c['step_days']))
        if len(starts)!=len(windows):raise ValueError('Saved fitted-window denominator differs')
        for start,weight,forward in zip(starts,windows,result['new_windows']):
            if (weight['fit_start'],weight['fit_end'],weight['fit_row_count'])!=(calendar[start-c['fit_days']],calendar[start-1],c['fit_days']):raise ValueError('Fit calendar differs')
            if (forward['start'],forward['end'])!=(calendar[start],calendar[start+c['window_days']-1]):raise ValueError('Forward calendar differs')
        panel=inputs['nominal_prices'];begin=calendar[starts[0]];end=calendar[starts[-1]+c['window_days']-1]
        positions=[i for i,date in enumerate(panel['index']) if begin<=date<=end];tickers=task['tickers'].split(';')
        prices={t:[panel['column_values'][panel['columns'].index(t)][i] for i in positions] for t in tickers}
        universe=dict(zip(inputs['universe']['columns'],inputs['universe']['column_values']))
        chains={t:universe['risk_chain'][universe['ticker'].index(t)] for t in tickers}
        accounting=ledger.account(dates=[panel['index'][i] for i in positions],prices=prices,
            schedule={calendar[start]:w['weights'] for start,w in zip(starts,windows)},risk_chains=chains,contract=c)
        accounting_errors=compare(accounting['summary'],result['result'],1e-8)
        reports.append(dict(new_job_id=task_file['new_job_id'],task=task,mode=task_file['mode'],window_count=len(rows),
            scalar_max_error=max(errors.values()),legacy_close_max_error=max(accounting_errors.values()),
            checked_legacy_close_fields=sorted(accounting['summary']),legacy_close_summary=accounting['summary'],
            saved_non20_fields_independently_recomputed=False,binary_float_ledger_hash_independently_verified=False))
    verification=drift.verify_expected_sources(sources,contract)
    return dict(schema='ndx_selected_snapshot_first_two_independent_audit_20260919_v1',tasks=reports,
        verified_source_hashes=verification['verified_source_hashes'],historical_expected_source_hashes=sources,
        historical_price_cache_gap_observations=verification['historical_gap_observations'],
        optimizer_or_original_simulator_called=False,historical_full_source_closure_verified=False,
        nominal_quote_authenticity_verified=False,dynamic_next_open_execution_validated=False,
        point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    report=build();path=FOLDER/'first_two_independent_audit_20260919.json'
    with path.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    drift.verify_expected_sources(report['historical_expected_source_hashes'],drift.load_contract())
    print(json.dumps(dict(path=str(path),sha256=drift.file_sha(path),tasks=report['tasks'])))
