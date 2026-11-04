"""Scale saved daily returns with annual deposits; not an integer-share replay."""
import json
from pathlib import Path
from fractions import Fraction as F
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[2]


def run():
    receipt = json.loads((ROOT/'research_contracts/reentry_repair_20261029/completion_receipt.json').read_bytes())
    comparison = json.loads((ROOT/'research_contracts/reentry_repair_20261029/comparison.json').read_bytes())
    for pins in (receipt['source_hashes'], comparison['source_hashes']):
        for name, expected in pins.items():
            assert sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
    result = dict(scope='Proportional daily-return scenario, independent source segments spliced; not actual continuous integer-share strategy replay',
                  initial_date='2020-12-31', initial_cash=50000, annual_deposit=50000,
                  end_date='2026-07-30', requested_month_end_not_available='2026-07-31',
                  timing='Deposit before first observed trading-session return each year; first-day close-to-close return applied to deposited amount as approximation',
                  boundary='2023-12-29 appears once as last early ledger return; recent first return is 2024-01-02 equity divided by independent 20000 anchor. No 20000 reset return is applied.',
                  source_hashes={}, arms={})
    for mode in ('baseline','candidate'):
        asset, invested, unit, unit_peak = F(50000), F(50000), F(1), F(1)
        unit_peak_day='2020-12-31'; maximum_dd=F(0); peak_day=trough_day=None
        annual={}; rows=[]; last_date='2020-12-31'
        for window in ('2021_2023','2024_2026'):
            path=ROOT/f'tmp/reentry_repair_20261029/{mode}_{window}/book.json'
            raw=path.read_bytes();result['source_hashes'][path.relative_to(ROOT).as_posix()]=sha256(raw).hexdigest()
            book=json.loads(raw);assert book['status']=='COMPLETE' and F(book['external_flows'])==0
            previous=F(20000)
            for row in book['daily_ledger']:
                day=row['date'];assert day>last_date
                year=day[:4];flow=F(0)
                if year not in annual:
                    flow=F(50000);asset+=flow;invested+=flow
                    annual[year]=dict(first_session=day,capital_after_deposit=asset,invested=invested,
                        high=asset,high_date=day+' before session',low=asset,low_date=day+' before session',
                        running_peak=asset,running_peak_date=day+' before session',maximum_drawdown=F(0),drawdown_peak=None,drawdown_trough=None)
                gross=F(row['equity'])/previous;previous=F(row['equity']);asset*=gross;unit*=gross
                if unit>unit_peak:unit_peak=unit;unit_peak_day=day
                dd=1-unit/unit_peak
                if dd>maximum_dd:maximum_dd=dd;peak_day=unit_peak_day;trough_day=day
                a=annual[year]
                if asset>a['high']:a['high']=asset;a['high_date']=day
                if asset<a['low']:a['low']=asset;a['low_date']=day
                if asset>a['running_peak']:a['running_peak']=asset;a['running_peak_date']=day
                yearly_dd=1-asset/a['running_peak']
                if yearly_dd>a['maximum_drawdown']:
                    a.update(maximum_drawdown=yearly_dd,drawdown_peak=a['running_peak_date'],drawdown_trough=day)
                a.update(end_date=day,end_asset=asset,net_gain=asset-invested,year_return=asset/a['capital_after_deposit']-1)
                rows.append(dict(date=day,deposit=flow,asset=asset,invested=invested,unit_nav=unit))
                last_date=day
        assert invested==350000 and len(rows)==1399
        result['arms'][mode]=dict(end_asset=asset,total_invested=invested,net_gain=asset-invested,
            profit_over_contributions=asset/invested-1, time_weighted_total_return=unit-1,
            time_weighted_maximum_drawdown=maximum_dd,drawdown_peak=peak_day,drawdown_trough=trough_day,annual=annual,daily=rows)
    output=ROOT/'tmp/annual_contribution_estimate_20261104';output.mkdir(exist_ok=True)
    (output/'result.json').write_text(json.dumps(result,indent=2,default=float),encoding='utf-8')
    (output/'exact_result.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    for mode,arm in result['arms'].items():
        print(mode,json.dumps({k:v for k,v in arm.items() if k not in ('daily','annual')},default=float))
        for year,a in arm['annual'].items():print(year,json.dumps({k:v for k,v in a.items() if k not in ('running_peak','running_peak_date')},default=float))


if __name__=='__main__':run()
