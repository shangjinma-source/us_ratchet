"""Compare only complete matching account paths; no live promotion authority."""
import argparse
from datetime import date
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
from backtest.research_exact_fraction_json import loads

ROOT=Path(__file__).resolve().parents[2]


def metrics(book, anchor):
    initial=F(book['initial_cash']);peak=initial;drawdown=F(0)
    streak=longest=0;prior=initial;annual={}
    for row in book['daily_ledger']:
        equity=F(row['equity'])
        if equity<=0 or F(row['cash'])<0:raise ValueError('INVALID_ACCOUNT_EQUITY_OR_CASH')
        if equity>=peak:peak=equity;streak=0
        else:streak+=1;longest=max(longest,streak)
        drawdown=max(drawdown,1-equity/peak)
        key=row['date'][:4]
        annual.setdefault(key,dict(start=prior,end=equity,first_date=row['date'],last_date=row['date']))
        annual[key].update(end=equity,last_date=row['date']);prior=equity
    years=(date.fromisoformat(book['daily_ledger'][-1]['date'])-date.fromisoformat(anchor)).days/365.25
    return dict(cagr_pct=100*((float(prior/initial))**(1/years)-1),
        drawdown_pct=float(drawdown*100),drawdown_exact=str(drawdown),terminal=str(prior),
        fills=len(book['order_log']),longest_underwater_sessions=longest,end_underwater_sessions=streak,
        annual=[dict(year=y,first_date=v['first_date'],last_date=v['last_date'],
            return_pct=float((v['end']/v['start']-1)*100)) for y,v in annual.items()])


def compare(candidate, reference):
    benchmark=reference['book']
    if candidate['status']!='COMPLETE' or benchmark['status']!='COMPLETE':
        return dict(status='INCOMPLETE_METRICS_WITHHELD',reason=candidate.get('reason'),economic_pass=False)
    dates=[r['date'] for r in candidate['daily_ledger']]
    expected=[r['date'] for r in benchmark['daily_ledger']]
    if dates!=expected or dates!=sorted(set(dates)) or len(dates)!=1399:
        raise ValueError('FULL_SESSION_PATH_MISMATCH')
    if reference['anchor']!='2020-12-31' or reference['end']!='2026-07-30' or dates[-1]!=reference['end'] or dates[0]!='2021-01-04':
        raise ValueError('FULL_PERIOD_MISMATCH')
    if F(candidate['initial_cash'])!=F(benchmark['initial_cash']) or F(candidate['initial_cash'])!=20000:
        raise ValueError('INITIAL_CAPITAL_MISMATCH')
    if candidate.get('slippage_bps')!='5' or candidate.get('commission')!='0_USER_AUTHORIZED_RESEARCH_ASSUMPTION':
        raise ValueError('CANDIDATE_COST_CONTRACT_MISMATCH')
    a=metrics(candidate,reference['anchor']);b=metrics(benchmark,reference['anchor'])
    conditions=dict(return_above_qqq=F(a['terminal'])>F(b['terminal']),
        drawdown_below_qqq=F(a['drawdown_exact'])<F(b['drawdown_exact']),
        drawdown_at_most_30=F(a['drawdown_exact'])<=F(3,10),
        no_more_than_ten_holdings=all(len(r['shares'])<=10 for r in candidate['daily_ledger']))
    return dict(status='COMPLETE_ECONOMIC_COMPARISON_REQUIRES_INDEPENDENT_ADMISSION',
        economic_pass=all(conditions.values()),conditions=conditions,candidate=a,qqq=b,
        production_activated=False,limitations=['Gross dividends, zero-commission assumption, daily-close drawdown',
            'Source, identity, financial PIT and current execution admission remain separate',
            'Historical acceptance does not guarantee a future drawdown ceiling'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-directory',required=True)
    args=parser.parse_args();directory=ROOT/args.run_directory
    path=directory/'book.json';raw=path.read_bytes();candidate=loads(raw.decode())
    baseline=ROOT/'tmp/qqq_continuous_paid_reinvestment_20261106.json';baseline_raw=baseline.read_bytes()
    result=compare(candidate,json.loads(baseline_raw))
    result['input_hashes']={str(path):sha256(raw).hexdigest(),str(baseline):sha256(baseline_raw).hexdigest()}
    (directory/'economic_comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
