"""Review an executed contiguous prefix, never relabel the source run complete."""
import argparse
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest.long_market_trend_independent_review_v1 import review


def review_executed_prefix(book, assembled, bars, dividend_events=(), *, signals, signal_source_hashes):
    if book['status'] not in ('COMPLETE','BLOCKED'):
        raise ValueError('FINAL_COMPLETE_OR_BLOCKED_BOOK_REQUIRED')
    rows=book['daily_ledger']; sessions=assembled['session_dates']
    if not rows:raise ValueError('NO_EXECUTED_PREFIX')
    count=len(rows); end=rows[-1]['date']
    if [row['date'] for row in rows]!=sessions[1:count+1]:
        raise ValueError('NONCONTIGUOUS_EXECUTED_PREFIX')
    partial=book['status']=='BLOCKED'
    if not partial and count!=len(sessions)-1:raise ValueError('FALSE_COMPLETE_BOOK')
    trailing=book['provider_audit'][count:]
    pending=[]
    if partial:
        if (count>=len(sessions)-1 or len(trailing)!=1 or trailing[0]['status']!='BLOCKED'
                or trailing[0].get('orders') or book['reason']!='ORDER_PROVIDER_NOT_READY'):
            raise ValueError('ONLY_PRE_EXECUTION_PROVIDER_BLOCK_SUPPORTED')
        if book['state_date']!=sessions[count+1] or book['last_valued_date']!=end:
            raise ValueError('UNEXPECTED_BLOCK_BOUNDARY')
        if (book['cash']!=rows[-1]['cash'] or book['shares']!=rows[-1]['shares']
                or book['receivable']!=rows[-1]['receivable']
                or book['distribution_rights']!=rows[-1]['distribution_rights']
                or book['merger_entitlements']!=rows[-1]['merger_entitlements']):
            raise ValueError('UNVALUED_TERMINAL_MUTATION')
        if any(log['date']>end for log in book['order_log']):
            raise ValueError('POST_PREFIX_ORDER_LOG')
        pending=[p['decision_date'] for p in assembled['monthly_inputs'] if p['decision_date']>=end]
    elif trailing:raise ValueError('EXTRA_COMPLETE_AUDITS')
    local=deepcopy(book); domain=deepcopy(assembled)
    domain['session_dates']=sessions[:count+1]
    domain['monthly_inputs']=[p for p in assembled['monthly_inputs'] if p['decision_date']<end]
    for key in ('actions','provider_actions'):
        domain[key]=[event for event in assembled.get(key,[]) if event['date']<=end]
    for key in ('distribution_events','cash_stock_merger_events'):
        domain[key]=[event for event in assembled.get(key,[]) if event['effective_date']<=end]
    local['provider_audit']=local['provider_audit'][:count]
    executed_dates={p['decision_date'] for p in domain['monthly_inputs']}
    local['selection_account_states']=[a for a in book['selection_account_states'] if a['decision_date'] in executed_dates]
    removed=[a['decision_date'] for a in book['selection_account_states'] if a['decision_date'] not in executed_dates]
    if removed and (not partial or removed!=[end]):raise ValueError('UNEXPECTED_UNEXECUTED_SELECTIONS')
    if [a['decision_date'] for a in local['selection_account_states']]!=[p['decision_date'] for p in domain['monthly_inputs']]:
        raise ValueError('SELECTION_PREFIX_MISMATCH')
    # Compatibility view only: the original book/status remain untouched.
    local['status']='COMPLETE'
    local['total_return']=str(Fraction(rows[-1]['equity'])/20000-1)
    proof=review(local,domain,bars,initial_cash='20000',
        dividend_events=[event for event in dividend_events if event['ex_date']<=end],
        expected_fee_bps='0',expected_slippage_bps='5',verify_selections=True,verify_risk_provider=True, signals=signals, signal_source_hashes=signal_source_hashes)
    return dict(status='EXECUTED_PREFIX_REVIEW_PASS' if partial else 'COMPLETE_DECLARED_INTERVAL_REVIEW_PASS',
        original_book_status=book['status'],original_reason=book.get('reason'),
        start=sessions[0],end=end,executed_sessions=count,requested_end=sessions[-1],
        pending_decision_dates=pending,unexecuted_selection_dates=removed,
        removed_unexecuted_provider_audits=len(trailing),proof=proof,
        interval_return=local['total_return'],full_bull_bear_validation=False,
        limitation='Only the recorded executed interval is verified; no source book or missing session is fabricated.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book',type=Path,required=True)
    parser.add_argument('--assembled',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    raw=args.book.read_bytes(); source=args.assembled.read_bytes()
    book=json.loads(raw); document=json.loads(source)
    baseline=document['baseline_execution_inputs']
    signals=document['signals'];pins=document['signal_source_hashes']
    if not pins:raise ValueError('SIGNAL_PINS_REQUIRED')
    for filename,expected in pins.items():
        if sha256((ROOT/filename).read_bytes()).hexdigest()!=expected:raise ValueError('SIGNAL_SOURCE_CHANGED:'+filename)
    if set(signals)!={p['decision_date'] for p in baseline['assembled']['monthly_inputs']}:raise ValueError('EXACT_SIGNAL_DOMAIN_REQUIRED')
    result=review_executed_prefix(book,baseline['assembled'],baseline['ohlc'],baseline.get('dividend_events') or (),signals=signals,signal_source_hashes=pins)
    result['source_hashes']={str(args.book):sha256(raw).hexdigest(),str(args.assembled):sha256(source).hexdigest(),
        'scripts/review_long_market_trend_account_v1.py':sha256(Path(__file__).read_bytes()).hexdigest(),
        'backtest/long_market_trend_independent_review_v1.py':sha256((ROOT/'backtest/long_market_trend_independent_review_v1.py').read_bytes()).hexdigest()}
    with args.output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    print(json.dumps({k:result[k] for k in ('status','start','end','executed_sessions','unexecuted_selection_dates')}))


if __name__=='__main__':main()
