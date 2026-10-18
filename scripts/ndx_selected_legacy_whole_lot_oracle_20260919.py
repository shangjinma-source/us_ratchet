"""Recompute saved-target old Close accounting only; no optimizer or engine calls."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_legacy_close_accounting_oracle_research as oracle
from backtest import ndx_exact_price_cache_drift_research as drift
from scripts import ndx_base_delta_probe_independent_audit as scalar
LOADED={str(p):drift.file_sha(p) for p in (Path(__file__).resolve(),Path(oracle.__file__).resolve(),Path(drift.__file__).resolve(),Path(scalar.__file__).resolve())}
FOLDER=ROOT/'data/cache/research/delta_selected_input_20260912_v1'


def main():
    expected=dict(LOADED)
    def read(path,sha):
        path=str(Path(path).resolve());assert drift.file_sha(path)==sha,path
        assert path not in expected or expected[path]==sha;expected[path]=sha
        return json.loads(Path(path).read_bytes())
    probe=read(FOLDER/'first_probe.json','241ac517d78668761f32a25da68856cf396d28a1ef5591d9da993a0e2307607a')
    assert probe['plan_sha256']=='f0ff0242f08dcb62ceb19d5650db811fe8d0d83741f7ecc995b6a3945cf15266'
    plan=read(probe['plan_path'],probe['plan_sha256']);assert probe['selected']==plan['probe']
    saved=probe['result'];row=probe['selected']['task'];task=row['task']
    for path,sha in saved['source_hashes'].items():
        assert path not in expected or expected[path]==sha;expected[path]=sha
    drift_contract=drift.load_contract();verification=drift.verify_expected_sources(expected,drift_contract)
    context=read(row['context_path'],row['context_sha256']);checkpoint=read(row['checkpoint_path'],row['checkpoint_sha256'])
    assert checkpoint['task']==task and task in context['tasks']
    inputs={key:scalar.decode(value['payload']) for key,value in context['prepared_inputs'].items()}
    contract=inputs['contract'];calendar=inputs['returns']['index'];fit=contract['fit_days'];window=contract['window_days']
    starts=list(range(fit,len(calendar)-window+1,contract['step_days']));windows=saved['historical_window_weights']
    assert len(starts)==len(windows)
    schedule={calendar[start]:record['weights'] for start,record in zip(starts,windows)}
    begin=calendar[starts[0]];end=calendar[starts[-1]+window-1]
    panel=inputs['nominal_prices'];positions=[i for i,d in enumerate(panel['index']) if begin<=d<=end]
    dates=[panel['index'][i] for i in positions];selected=task['tickers'].split(';')
    prices={t:[panel['column_values'][panel['columns'].index(t)][i] for i in positions] for t in selected}
    universe=inputs['universe'];ucols=dict(zip(universe['columns'],universe['column_values']))
    chains={t:ucols['risk_chain'][ucols['ticker'].index(t)] for t in selected}
    computed=oracle.account(dates=dates,prices=prices,schedule=schedule,risk_chains=chains,contract=contract)
    summary=computed['summary'];independent_shares=[];residuals=[]
    for start,record in zip(starts,windows):
        i=dates.index(calendar[start]);investable=oracle.number(contract['portfolio_cash_usd'])-oracle.number(contract['minimum_cash_buffer_usd'])
        shares={t:int(investable*oracle.number(record['weights'][t])/oracle.number(prices[t][i])) for t in selected}
        independent_shares.append(shares)
        residuals.append(float(oracle.number(contract['portfolio_cash_usd'])-sum(shares[t]*oracle.number(prices[t][i]) for t in selected)))
    summary.update(whole_lot_min_shares=min(min(s.values()) for s in independent_shares),
        whole_lot_residual_cash_p50=scalar.quantile(residuals,.5),
        whole_lot_executable_all_windows=summary['whole_lot_cash_buffer_preserved'] and summary['whole_lot_constraints_preserved_all_days'] and all(min(s.values())>=1 for s in independent_shares),
        whole_lot_executability=summary['whole_lot_execution_mode'])
    differences={}
    for key,actual in summary.items():
        original=saved['result'][key]
        if type(actual) is float:
            delta=abs(actual-original);assert delta<=1e-8+1e-12*abs(original),(key,actual,original);differences[key]=delta
        else:assert actual==original,(key,actual,original)
    # Every whole_lot output except the binary-float ledger serialization hash
    # is checked; Decimal ledger rounding intentionally has its own encoding.
    unchecked=set(k for k in saved['result'] if k.startswith('whole_lot_'))-set(summary)
    assert unchecked=={'whole_lot_rebalance_trace_sha256'}
    verification=drift.verify_expected_sources(expected,drift_contract)
    report=dict(schema='ndx_selected_legacy_close_decimal_oracle_20260919_v1',task=task,
        verified_source_hashes=verification['verified_source_hashes'],historical_expected_source_hashes=expected,
        historical_price_cache_gap_observations=verification['historical_gap_observations'],
        summary=summary,numeric_absolute_errors=differences,daily=computed['daily'],trades=computed['trades'],
        old_binary_float_ledger_sha_not_independently_compared=True,unchecked_saved_fields=sorted(unchecked),
        nominal_quote_authenticity_verified=False,historical_full_source_closure_verified=False,
        same_close_legacy_accounting_validated=True,dynamic_next_open_execution_validated=False,
        optimizer_or_original_simulator_called=False,point_in_time_verified=False,promotion_allowed=False)
    output=FOLDER/'legacy_close_decimal_oracle_20260919.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    drift.verify_expected_sources(expected,drift_contract)
    print(json.dumps(dict(path=str(output),sha256=drift.file_sha(output),days=len(dates),rebalances=len(schedule),max_numeric_error=max(differences.values()))))


if __name__=='__main__':main()
