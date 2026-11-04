"""Read-only complete/prefix review CLI; never executes an economic strategy."""
import argparse,json,sys,importlib.util
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"research_contracts/reentry_repair_20261029"))
import independent_reference_review as reference
from backtest import long_market_trend_independent_review_v1 as trend
from scripts import review_old_continuous_identity_prefix_v1 as prefix

def load(path):return json.loads(Path(path).read_bytes())
def digest(path):return sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--run-directory',required=True);p.add_argument('--output',required=True);args=p.parse_args();run=Path(args.run_directory);contract=load(run/'contract.json');pins=dict(contract['source_hashes'])
    for name,h in pins.items():
        if digest(ROOT/name)!=h:raise ValueError('INPUT_PIN_CHANGED:'+name)
    window=contract['window'];early=window=='2021_2023'
    if window not in ('2021_2023','2024_2026') or contract['mode']!='REENTRY_REPAIR':raise ValueError('FIXED_REENTRY_RUN_REQUIRED')
    base=ROOT/'tmp'/('recent_continuous_baseline_20261026_v7' if early else 'old_continuous_baseline_20261026_v9')
    required=[base/'execution_inputs.json', ROOT/'tmp'/('trend_'+window+'_20261026_v1')/'execution_inputs.json',ROOT/'tmp'/('recent_execution_prices_20261026' if early else 'old_window_execution_prices_20261026')/'execution_prices_v1.json',ROOT/'tmp/reentry_repair_20261029/nvda_cash_reference/review.json',ROOT/'research_contracts/reentry_repair_20261029/frozen_contract.json']
    for file in required:
        if pins.get(file.relative_to(ROOT).as_posix())!=digest(file):raise ValueError('REQUIRED_INPUT_BINDING:'+str(file))
    document=load(base/'execution_inputs.json');prior=load(ROOT/'tmp'/('trend_'+window+'_20261026_v1')/'execution_inputs.json')
    prices=load(ROOT/'tmp'/('recent_execution_prices_20261026' if early else 'old_window_execution_prices_20261026')/'execution_prices_v1.json')
    cashpath=ROOT/'tmp/reentry_repair_20261029/nvda_cash_reference/review.json';cash=load(cashpath)
    for source in (document['assembled']['source_hashes'],document.get('action_source_hashes',{}),prior['action_review']['source_hashes'],cash['source_hashes']):
        for name,h in source.items():
            if digest(ROOT/name)!=h:raise ValueError('SOURCE_PIN_CHANGED:'+name)
            pins[name.replace('\\','/')]=h
    if prior['baseline_execution_inputs']!=document:raise ValueError('BASELINE_ACTION_REVIEW_MISMATCH')
    context=dict(window=window,document=document,prices=prices,action_review=prior['action_review'],cash_review=cash)
    if not early:
        ap=ROOT/'tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py'
        if digest(ap)!='2016ac8bfc802ae3042bd7592e3a897bcb0568c88a79161a8de05d58dc8f3aa5':raise ValueError('LEGACY_ADAPTER_PIN')
        spec=importlib.util.spec_from_file_location('independent_reentry_wbd',ap);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);proof=m.certify(ROOT,document['assembled']['session_dates']);context['legacy_admit']=lambda gate:m.admit(gate,proof)
    book=load(run/'book.json')
    signals_document=load(ROOT/'tmp/qqq_month_end_warmup_20261026_v1/two_window_signal_input_manifest.json')
    signals={r['decision_date']:r for w in signals_document['windows'] if w['name']==window for r in w['inputs']}
    original_trend_review=trend.review
    def trend_with_signals(*a,**kw):return original_trend_review(*a,signals=signals,signal_source_hashes=signals_document['source_hashes'],**kw)
    trend.review=trend_with_signals
    reference.ledger=trend
    original_verify=reference.ReferenceOrderVerifier.verify
    def verify_combined(self,item,original,decision,active,shares):
        if original.get('risk_overlay')!={'empty_target':True}:return original_verify(self,item,original,decision,active,shares)
        assert item['decision_date']==decision and item['active_date']==active
        assert item['original']==original and item['adjusted']==original
        assert item['actual_shares']==shares
        assert reference.F(item['actual_cash'])==reference.F(original['unreserved_cash'])
        assert all(o['side']=='SELL' for o in original['orders'])
        assert item['locks_before']==self.locks==item['locks_after']
        assert not item['interval_reviews']
        self.count+=1
        return original['orders']
    reference.ReferenceOrderVerifier.verify=verify_combined
    def bridge(*a,**kw):return reference.review(*a,reference_context=context,**kw)
    with patch.object(prefix,'review',bridge):result=prefix.review_executed_prefix(book,document['assembled'],document['ohlc'],document['dividend_events'])
    for file in [run/'book.json',run/'contract.json',Path(__file__),ROOT/'research_contracts/reentry_repair_20261029/independent_reference_review.py',ROOT/'scripts/review_old_continuous_identity_prefix_v1.py',ROOT/'backtest/historical_dividend_identity_independent_review_v1.py']:
        pins[file.resolve().relative_to(ROOT).as_posix()]=digest(file)
    result['source_hashes']=pins
    with Path(args.output).open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:result[k] for k in ['status','start','end','executed_sessions']}))
if __name__=='__main__':main()
