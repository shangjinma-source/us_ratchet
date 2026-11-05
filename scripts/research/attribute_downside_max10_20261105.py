"""Exact additive 2026 path attribution; not a counterfactual backtest."""
import argparse
import json
from collections import Counter
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.research.summarize_downside_max10_20261105 import read,verify,pinned_book,require


def classification(book):
    source={}
    previous=None
    for row in book['provider_audit']:
        reset=row['target_decision_date']!=previous
        previous=row['target_decision_date']
        for order in row['orders']:
            reason=row.get('risk_overlay',{}).get('reasons',{}).get(order['security_id'])
            if order['side']=='SELL' and reason=='MONTHLY_PEAK_EXIT_LATCHED': category='MONTHLY_20PCT_EXIT'
            elif reset: category='MONTH_TARGET_RESET'
            else: category='WITHIN_MONTH_TARGET_EXECUTION'
            source[order['id']]={'category':category,'risk_reason':reason,'monthly_target_decision':row['target_decision_date'],
                                  'order_decision':order['decision_date'],'provider_action':row['action'],'reset':reset}
    result=[]
    for fill in book['order_log']:
        if fill.get('event')!='ASSUMED_NEXT_OPEN_FILLED':continue
        require(fill['id'] in source,'FILL_PROVIDER_ORDER_NOT_FOUND')
        result.append(dict(fill,classification=source[fill['id']]))
    return result


def run(folder):
    folder=(ROOT/folder).resolve(); baseline=ROOT/'tmp/old_continuous_baseline_20261026_v9'
    book=read(folder/'book.json');audit=read(folder/'independent_review.json');contract=read(folder/'contract.json')
    require(book['status']=='COMPLETE' and audit['status']=='INDEPENDENT_DOWNSIDE_MAX10_CHAIN_FINANCE_PASS','AUDIT_PASS_REQUIRED')
    require(len(book['daily_ledger'])==646,'FULL_WINDOW_REQUIRED');pinned_book(audit,folder/'book.json');verify(contract['source_hashes'])
    old=read(baseline/'book.json');pinned_book(read(baseline/'independent_prefix_review.json'),baseline/'book.json')
    document=read(baseline/'execution_inputs.json');verify(document['source_hashes']);prices=document['ohlc'];meta=document['assembled']['metadata']
    start=next(r for r in book['daily_ledger'] if r['date']=='2025-12-31');end=book['daily_ledger'][-1]
    fills=classification(book);yearfills=[r for r in fills if r['date'].startswith('2026')]
    dividends=[r for r in book['dividend_ledger']['events'].values() if r['event']['ex_date'].startswith('2026')]
    securities=set(start['shares'])|set(end['shares'])|{r['security_id'] for r in yearfills}
    items=[]
    for sid in sorted(securities):
        opening=F(start['shares'].get(sid,0))*F(prices[sid][start['date']]['close']) if start['shares'].get(sid,0) else F(0)
        closing=F(end['shares'].get(sid,0))*F(prices[sid][end['date']]['close']) if end['shares'].get(sid,0) else F(0)
        trades=[r for r in yearfills if r['security_id']==sid]
        buy=sum((r['quantity']*F(r['price']) for r in trades if r['side']=='BUY'),F(0))
        sell=sum((r['quantity']*F(r['price']) for r in trades if r['side']=='SELL'),F(0))
        fees=sum((F(r['fee']) for r in trades),F(0))
        dividend=sum((F(r['net']) for r in dividends if r['event']['security_id']==sid),F(0))
        pnl=closing-opening+sell-buy-fees+dividend
        if opening or closing or trades or dividend:
            items.append(dict(security_id=sid,ticker=meta[sid]['ticker'],opening_mark=opening,closing_mark=closing,buy_cash=buy,sell_cash=sell,
                              fees=fees,dividend_accrual=dividend,pnl=pnl,pnl_usd=float(pnl),fills=len(trades)))
    total=sum((r['pnl'] for r in items),F(0));change=F(end['equity'])-F(start['equity'])
    require(total==change,'ATTRIBUTION_DOES_NOT_RECONCILE')
    require(sum((r['opening_mark'] for r in items),F(0))==F(start['stock_value']),'OPENING_MARKS')
    require(sum((r['closing_mark'] for r in items),F(0))==F(end['stock_value']),'CLOSING_MARKS')
    require(not any(F(r['external_flow']) for r in book['daily_ledger'] if r['date'].startswith('2026')),'EXTERNAL_FLOW')
    slippage=F(0)
    for trade in yearfills:
        raw_open=F(prices[trade['security_id']][trade['date']]['open'])
        multiplier=F(10005,10000) if trade['side']=='BUY' else F(9995,10000)
        require(F(trade['price'])==raw_open*multiplier,'ACTUAL_5BP_FILL')
        slippage+=abs(F(trade['price'])-raw_open)*trade['quantity']
    counts={}
    for label,records in [('candidate',fills),('v27',classification(old))]:
        counts[label]={}
        for period,filtered in [('full',records),('2026',[r for r in records if r['date'].startswith('2026')])]:
            counts[label][period]=dict(total=len(filtered),by_mechanism=dict(Counter(r['classification']['category'] for r in filtered)),by_side=dict(Counter(r['side'] for r in filtered)))
    result=dict(status='EXACT_PATH_ATTRIBUTION_RECONCILED',start=start['date'],end=end['date'],opening_equity=start['equity'],closing_equity=end['equity'],
                equity_change_exact=change,equity_change_usd=float(change),direct_slippage_2026_exact=slippage,direct_slippage_2026_usd=float(slippage),securities=sorted(items,key=lambda r:r['pnl']),trade_counts=counts,
                fills_with_provider_evidence=fills,limitations=['Additive realized-path accounting, not causal counterfactual attribution.',
                'MONTH_TARGET_RESET identifies first provider call of a new monthly target; BUY/SELL both included.',
                'WITHIN_MONTH_TARGET_EXECUTION is not asserted to be cash top-up unless separate cash evidence exists.',
                '20pct exits identified by actual MONTHLY_PEAK_EXIT_LATCHED provider reason.',
                'ASML final dividend timing limitations remain those of independent_review.json.'],source_hashes={})
    paths=[Path(__file__),folder/'book.json',folder/'independent_review.json',folder/'contract.json',baseline/'book.json',baseline/'execution_inputs.json',baseline/'independent_prefix_review.json']
    result['source_hashes']={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
    verify(contract['source_hashes']);verify(audit['source_hashes'])
    (folder/'attribution_2026.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf8')
    print(json.dumps(dict(pnl=float(change),counts=counts,ranked=[(x['ticker'],x['pnl_usd']) for x in result['securities']]),indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
