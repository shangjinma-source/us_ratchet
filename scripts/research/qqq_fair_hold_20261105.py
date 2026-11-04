"""Fixed QQQ two-window integer-share buy-and-hold with unspent dividend receivables."""
import json,gzip
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime,date
from zoneinfo import ZoneInfo
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2]
def run():
    names=['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']
    pins=json.loads((ROOT/'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json').read_bytes())['base_file_dependencies']
    panel={};dividends={};hashes={}
    for name in names:
        raw=(ROOT/name).read_bytes();hashes[name]=sha256(raw).hexdigest();assert hashes[name]==pins[name]
        body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
        assert body['meta']['symbol']=='QQQ' and not body.get('events',{}).get('splits')
        quote=body['indicators']['quote'][0]
        for i,t in enumerate(body['timestamp']):
            if quote['open'][i] is None or quote['close'][i] is None:continue
            day=datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat();value={k:F(quote[k][i]) for k in ('open','close')}
            if day in panel:assert panel[day]==value
            panel[day]=value
        for event in body.get('events',{}).get('dividends',{}).values():
            day=datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat();amount=F(event['amount'])
            if day in dividends:assert dividends[day]==amount
            dividends[day]=amount
    output=ROOT/'tmp/qqq_fair_hold_20261105';output.mkdir(exist_ok=False);results=[]
    for name,anchor in [('recent_continuous_baseline_20261026_v7','2020-12-31'),('old_continuous_baseline_20261026_v9','2023-12-29')]:
        inputpath=ROOT/'tmp'/name/'execution_inputs.json';raw=inputpath.read_bytes();hashes[str(inputpath.relative_to(ROOT))]=sha256(raw).hexdigest();inputs=json.loads(raw)
        days=inputs['assembled']['session_dates'];assert days[0]==anchor
        active=days[1:];assert all(d in panel for d in active)
        cash=F(20000);shares=0;receivable=F(0);ledger=[];peak=F(20000);dd=F(0);events=[]
        for day in active:
            if day in dividends and shares:
                credit=shares*dividends[day];receivable+=credit;events.append(dict(ex_date=day,quantity=shares,per_share=str(dividends[day]),receivable=str(credit),payment_date=None))
            if not shares:
                fill=panel[day]['open']*F(10005,10000);shares=int(cash/fill);cash-=shares*fill;assert shares>0
                order=dict(date=day,side='BUY',quantity=shares,raw_open=str(panel[day]['open']),fill=str(fill),cash_after=str(cash))
            equity=cash+shares*panel[day]['close']+receivable;peak=max(peak,equity);dd=max(dd,1-equity/peak)
            ledger.append(dict(date=day,shares=shares,cash=str(cash),dividend_receivable=str(receivable),equity=str(equity)))
        years=(date.fromisoformat(active[-1])-date.fromisoformat(anchor)).days/365.25
        summary=dict(window=name,anchor=anchor,first_open=active[0],last_close=active[-1],initial=20000,terminal=float(equity),cagr_pct=(float(equity/20000)**(1/years)-1)*100,drawdown_pct=float(dd*100),return_pct=float(equity/20000-1)*100,shares=shares,cash=float(cash),dividend_receivable=float(receivable),dividend_events=len(events),fills=1,terminal_liquidation_5bp_sensitivity=float(equity-shares*panel[active[-1]]['close']*F(5,10000)))
        (output/(name+'.json')).write_text(json.dumps(dict(summary=summary,order=order,dividends=events,ledger=ledger),indent=2),encoding='utf-8');results.append(summary)
    result=dict(scope='Unlevered QQQ hold, each window independent 20k, first next-open buy 5bp, zero commission, no reinvestment, terminal close not forced sale; gross dividends accrue ex-date and remain nonspendable without paydate. Conditional vendor source, not independently certified total-return series.',source_hashes=hashes,results=results)
    (output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':run()
