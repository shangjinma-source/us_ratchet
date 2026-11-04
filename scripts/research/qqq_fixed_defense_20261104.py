"""Fixed whole-share QQQ hold/trend comparison; no parameter search."""
import json,gzip,sys
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime,date
from zoneinfo import ZoneInfo
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backtest.long_market_trend_research_v1 import signal_proof

def run():
    names=['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']
    pinned=json.loads((ROOT/'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json').read_bytes())['base_file_dependencies']
    panels=[];hashes={}
    for name in names:
        raw=(ROOT/name).read_bytes();hashes[name]=sha256(raw).hexdigest();assert hashes[name]==pinned[name]
        r=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
        assert r['meta']['symbol']=='QQQ' and not r.get('events',{}).get('splits')
        q=r['indicators']['quote'][0]
        panels.append({datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat():{k:F(q[k][i]) for k in ('open','close')} for i,t in enumerate(r['timestamp']) if all(q[k][i] is not None for k in ('open','close'))})
    overlap=sorted(set(panels[0])&set(panels[1]));assert all(panels[0][d]==panels[1][d] for d in overlap),'OVERLAP_OPEN_CLOSE_MISMATCH'
    panel={**panels[0],**panels[1]}
    dates=json.loads((ROOT/'tmp/annual_contribution_estimate_20261104/result.json').read_bytes())['arms']['baseline']['daily'];days=[r['date'] for r in dates]
    assert all(d in panel for d in days)
    all_days=sorted(panel);monthends={}
    for day in all_days:monthends[day[:7]]=day
    complete=[d for d in sorted(monthends.values()) if d<='2026-07-30']
    decisions={}
    for i,day in enumerate(complete):
        if day<'2020-12-31':continue
        records=[dict(date=d,close=str(panel[d]['close']),source=names[0] if d<='2023-12-29' else names[1]) for d in complete[i-9:i+1]]
        decisions[day]=signal_proof(dict(decision_date=day,completed_month_end_prices=records))
    assert '2020-12-31' in decisions and len(decisions['2020-12-31']['completed_month_end_prices'])==10
    out=ROOT/'tmp/qqq_fixed_defense_20261104';out.mkdir(exist_ok=True)
    result=dict(scope='Two fixed whole-share accounts. Price-only; both exclude dividends and taxes. 5bp adverse per trade, zero commission/cash yield. Conditional provider daily bars, not OOS.',
        first_trade='2021-01-04 open; initial50000 plus first50000 deposit',source_hashes=hashes,overlap_equal_open_close_sessions=len(overlap),signals=decisions,arms={})
    for mode in ('hold','trend'):
        cash=F(50000);shares=0;invested=F(50000);unit=F(1);prior_equity=F(50000);prior_day='2020-12-31';risk_on=False;orders=[];ledger=[];annual={};peak=F(1);peak_day=prior_day;worst=F(0);worst_peak=worst_trough=None;below=0;start=None;episodes=[]
        for day in days:
            opening=panel[day]['open'];closing=panel[day]['close'];preflow_open=cash+shares*opening
            year=day[:4];flow=F(50000) if year not in annual else F(0)
            if flow:annual[year]=dict(start_unit=unit);cash+=flow;invested+=flow
            was_on=risk_on
            if mode=='hold':risk_on=True
            elif prior_day in decisions:risk_on=decisions[prior_day]['risk_on']
            if not risk_on and shares:
                fill=opening*(1-F(5,10000));cash+=shares*fill;orders.append(dict(date=day,side='SELL',quantity=shares,fill=str(fill),signal_date=prior_day));shares=0
            elif risk_on and (not was_on or flow):
                fill=opening*(1+F(5,10000));quantity=int(cash/fill)
                if quantity:cash-=quantity*fill;shares+=quantity;orders.append(dict(date=day,side='BUY',quantity=quantity,fill=str(fill),signal_date=prior_day))
            equity=cash+shares*closing
            # External cash enters at open, after overnight holding return and before trades.
            unit*=preflow_open/prior_equity*equity/(preflow_open+flow)
            if unit>=peak:peak=unit;peak_day=day
            dd=1-unit/peak
            if dd>worst:worst=dd;worst_peak=peak_day;worst_trough=day;worst_peak_unit=peak
            if equity<invested:
                below+=1
                if start is None:start=day
            elif start is not None:episodes.append(dict(start=start,recovery=day,days=(date.fromisoformat(day)-date.fromisoformat(start)).days));start=None
            annual[year].update(end_date=day,asset=equity,invested=invested,net_gain=equity-invested,twr=unit/annual[year]['start_unit']-1)
            ledger.append(dict(date=day,equity=equity,cash=cash,shares=shares,deposit=flow,invested=invested,unit_nav=unit,risk_on=risk_on));prior_day=day;prior_equity=equity
        if start:episodes.append(dict(start=start,recovery=None,days=(date.fromisoformat(days[-1])-date.fromisoformat(start)).days))
        recovery=next((r['date'] for r in ledger if r['date']>worst_trough and r['unit_nav']>=worst_peak_unit),None)
        result['arms'][mode]=dict(annual=annual,end_equity=prior_equity,net_gain=prior_equity-invested,maximum_drawdown=worst,peak=worst_peak,trough=worst_trough,recovery=recovery,peak_to_recovery_or_end_days=(date.fromisoformat(recovery or days[-1])-date.fromisoformat(worst_peak)).days,principal_underwater_sessions=below,principal_underwater_episodes=episodes,trades=len(orders),orders=orders,ledger=ledger)
    hashes['docs/qqq_fixed_defense_contract_20261104.md']=sha256((ROOT/'docs/qqq_fixed_defense_contract_20261104.md').read_bytes()).hexdigest()
    hashes['scripts/research/qqq_fixed_defense_20261104.py']=sha256(Path(__file__).read_bytes()).hexdigest()
    (out/'result.json').write_text(json.dumps(result,indent=2,default=float),encoding='utf-8')
    (out/'exact_result.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps({mode:{k:v for k,v in a.items() if k not in ('ledger','orders')} for mode,a in result['arms'].items()},indent=2,default=float))
if __name__=='__main__':run()
