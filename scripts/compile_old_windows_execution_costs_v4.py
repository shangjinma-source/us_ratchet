"""Pure compile exact execution-close costs; preserve every raw training scenario."""
import hashlib,json,sys
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window

def main():
    pins={}
    def document(path):
        raw=(ROOT/path).read_bytes();pins[path]=hashlib.sha256(raw).hexdigest();doc=json.loads(raw)
        for name,digest in doc.get('source_hashes',{}).items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED:'+name)
            if name in pins and pins[name]!=digest:raise ValueError('PIN_CONFLICT:'+name)
            pins[name]=digest
        return doc
    training_path='tmp/old_window_source_reuse_20261026/unified_raw_compilation_v3.json'
    execution_path='tmp/old_window_execution_prices_20261026/execution_prices_v1.json'
    old=document(training_path);execution=document(execution_path)
    if execution['training_sha256']!=pins[training_path]:raise ValueError('TRAINING_BINDING_MISMATCH')
    if old['pure_compiled_windows']!=31 or execution['retained_holding_price_gaps']:raise ValueError('INCOMPLETE_INPUT')
    self_path=Path(__file__).relative_to(ROOT).as_posix();pins[self_path]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result=deepcopy(old);changes=[]
    for window in result['windows']:
        day=window['decision_date'];previous=deepcopy(window['compiled_search_arguments'])
        for candidate in window['candidates']:
            if candidate['status']=='EXCLUDED_TRAINING_RULE':continue
            ticker=candidate['ticker'];prior=Fraction(candidate['decision_cost'])
            close=Fraction(execution['ohlc_candidates_by_ticker'][ticker][day]['close']);delta=close-prior
            if abs(delta)>Fraction('0.00001'):raise ValueError('NON_REPRESENTATION_PRICE_DIFFERENCE:'+ticker+':'+day)
            candidate['decision_cost']=str(close)
            candidate['decision_cost_execution_source']=execution['source_routes'][ticker]['source_by_date'][day]
            candidate['source_references']=candidate.get('source_references',[])+[execution_path]
            if delta:
                receipt=dict(decision_date=day,ticker=ticker,security_id=candidate['security_id'],old_cost=str(prior),new_cost=str(close),delta=str(delta),
                    reason='PREDECLARED_EXACT_EXECUTION_CLOSE_REPRESENTATION_NO_PERFORMANCE_SELECTION',source=candidate['decision_cost_execution_source'])
                changes.append(receipt);candidate['cost_representation_normalization']=receipt
        window['admission']['source_references']=window['admission']['source_references']+[execution_path]
        arguments=compile_monthly_training_window(window=dict(decision_cutoff=day,training_dates=window['training_dates'],candidates=window['candidates']),source_hashes=pins,admission=window['admission'])
        for name,value in previous.items():
            if name!='prices' and value!=arguments[name]:raise ValueError('NON_COST_ARGUMENT_CHANGED:'+name+':'+day)
        window['compiled_search_arguments']=arguments
    for path,digest in pins.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED_DURING_RUN:'+path)
    result.update(schema='OLD_WINDOWS_UNIFIED_RAW_COMPILATION_V4',source_hashes=pins,
        prior_training_path=training_path,prior_training_sha256=pins[training_path],execution_prices_path=execution_path,
        execution_prices_sha256=pins[execution_path],cost_normalization_changes=changes,
        all_training_scenarios_unchanged=True,all_decision_costs_exact_execution_close=True,execution_authorized=False)
    result['limitations'].append('Exact quote-cost agreement does not admit identity transitions or corporate-action cash/shares/receivable accounting.')
    target=ROOT/'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(windows=len(result['windows']),cost_changes=len(changes),scenario_changes=0,search_calls=0,economic_runs=0,sha256=hashlib.sha256(target.read_bytes()).hexdigest())))

if __name__=='__main__':main()
