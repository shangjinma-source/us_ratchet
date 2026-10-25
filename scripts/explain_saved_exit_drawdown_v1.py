"""Explain saved paired paths, without running selection or new backtests."""
import argparse
from collections import defaultdict
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path


def number(value):
    return Fraction(str(value))


def summarize(outcome):
    assert outcome['status']=='COMPLETE' and outcome['external_flows']=='0'
    initial=number(outcome['selection_account_states'][0]['account_state']['cash'])
    assert not outcome['selection_account_states'][0]['account_state']['shares']
    peak=initial;peak_date=outcome['selection_account_states'][0]['decision_date']
    worst=Fraction(0);interval=None;ends={}
    for row in outcome['daily_ledger']:
        equity=number(row['equity'])
        assert equity>0
        if equity>peak:peak=equity;peak_date=row['date']
        drawdown=1-equity/peak
        if drawdown>worst:
            worst=drawdown;interval=dict(peak_date=peak_date,trough_date=row['date'],
                peak_equity=float(peak),trough_equity=float(equity))
        ends[row['date'][:7]]=row
    assert worst==number(outcome['drawdown']['maximum_close_drawdown'])
    previous=initial;months={}
    for month,row in sorted(ends.items()):
        equity=number(row['equity'])
        months[month]=dict(close_date=row['date'],return_percent=float(100*(equity/previous-1)),
            end_equity=float(equity),cash_percent=float(100*number(row['cash'])/equity))
        previous=equity
    assert previous/initial-1==number(outcome['total_return'])
    return dict(maximum_drawdown_percent=float(worst*100),interval=interval,months=months)


def analyze(directory):
    paths={arm:directory/arm/'outcome.json' for arm in ('cap50','cap50_exit20')}
    raw={arm:path.read_bytes() for arm,path in paths.items()}
    review=json.loads((directory/'independent_fill_review.json').read_bytes())
    assert review['status']=='PASS_INDEPENDENT_FILL_CASH_SHARE_NAV'
    checked={row['arm']:row['outcome_sha256'] for row in review['reports']}
    assert all(sha256(body).hexdigest()==checked[arm] for arm,body in raw.items())
    books={arm:json.loads(body) for arm,body in raw.items()}
    assert [row['date'] for row in books['cap50']['daily_ledger']]==[row['date'] for row in books['cap50_exit20']['daily_ledger']]
    summary={arm:summarize(book) for arm,book in books.items()}
    names={quote['security_id']:quote['ticker'] for book in books.values()
           for selection in book['selection_account_states'] for quote in selection['valuation_quotes']}
    book=books['cap50_exit20'];states=defaultdict(list);new_exits=[];seen=set()
    for audit in book['provider_audit']:
        risk=audit.get('risk_overlay',{}).get('state')
        if not risk:continue
        states[risk['decision_date']].append(risk)
        for sid in risk['exited']:
            key=(risk['decision_date'],sid)
            if key in seen:continue
            seen.add(key)
            orders=[order for order in audit['orders'] if order['security_id']==sid and order['side']=='SELL']
            fills=[fill for fill in book['order_log'] if fill.get('id') in {o['id'] for o in orders}
                   and fill['event']=='ASSUMED_NEXT_OPEN_FILLED']
            new_exits.append(dict(decision_date=risk['decision_date'],signal_date=risk['session_date'],
                security_id=sid,ticker=names[sid],signal_close=float(number(risk['last_closes'][sid])),
                peak_close=float(number(risk['peaks'][sid])),unit=risk['unit_ids'][sid],
                modeled_fills=[dict(date=f['date'],quantity=f['quantity'],price=float(number(f['price']))) for f in fills]))
    for event in new_exits:
        history=states[event['decision_date']];sid=event['security_id']
        last=history[-1]
        # No price comparison across a changed share unit or a missing end mark.
        valid=sid in last['last_closes'] and last['unit_ids'].get(sid)==event['unit']
        event['last_observed_session']=last['session_date']
        event['later_price_change_percent']=None
        event['comparison_scope']='LAST_SAVED_POLICY_MARK_NOT_COUNTERFACTUAL_RETURN'
        if valid and event['modeled_fills']:
            fill=event['modeled_fills'][-1]
            if last['session_date']>=fill['date']:
                event['later_price_change_percent']=100*(float(number(last['last_closes'][sid]))/fill['price']-1)
        buys=[fill for fill in book['order_log'] if fill['event']=='ASSUMED_NEXT_OPEN_FILLED'
              and fill.get('security_id')==sid and fill.get('side')=='BUY' and fill['date']>event['signal_date']]
        event['next_modeled_buy']=None
        if buys:
            first=min(buys,key=lambda fill:fill['date'])
            event['next_modeled_buy']=dict(date=first['date'],quantity=first['quantity'],price=float(number(first['price'])))
    months=[]
    for month,base in summary['cap50']['months'].items():
        variant=summary['cap50_exit20']['months'][month]
        months.append(dict(month=month,baseline_return=base['return_percent'],exit_return=variant['return_percent'],
            difference_percentage_points=variant['return_percent']-base['return_percent'],
            exits=[e for e in new_exits if e['signal_date'].startswith(month)]))
    return dict(source_sha256={str(paths[arm]):sha256(body).hexdigest() for arm,body in raw.items()},
        summary=summary,months=months,exit_events=new_exits,
        limitations=['Path comparison is not causal attribution: monthly equity and subsequent quantities differ.',
                    'Post-exit price changes are not realizable returns or grounds for changing a live rule.',
                    'Saved conditional historical prices; not PIT certified or independent OOS.',
                    'No new search, parameter fitting, market capture, or account changes.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=analyze(Path(args.directory))
    with Path(args.output).open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(intervals={arm:row['interval'] for arm,row in result['summary'].items()},
        worst_relative_months=sorted(result['months'],key=lambda row:row['difference_percentage_points'])[:3],
        exit_count=len(result['exit_events'])),ensure_ascii=False))


if __name__=='__main__':main()
