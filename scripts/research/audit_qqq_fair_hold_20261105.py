"""Independent accounting and annual metrics for the frozen QQQ hold output."""
import json,gzip
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime,date
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
def run():
    out=ROOT/'tmp/qqq_fair_hold_20261105';manifest=json.loads((out/'summary.json').read_bytes());prices={};divs={};reports=[]
    for name in list(manifest['source_hashes'])[:2]:
        raw=(ROOT/name).read_bytes();body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
        for i,t in enumerate(body['timestamp']):
            day=datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat();q=body['indicators']['quote'][0]
            if q['open'][i] is not None and q['close'][i] is not None:prices[day]=(F(q['open'][i]),F(q['close'][i]))
        for e in body['events']['dividends'].values():divs[datetime.fromtimestamp(e['date'],ZoneInfo('America/New_York')).date().isoformat()]=F(e['amount'])
    for summary in manifest['results']:
        saved=json.loads((out/(summary['window']+'.json')).read_bytes());q=int(F(20000)/(prices[summary['first_open']][0]*F(10005,10000)));cash=F(20000)-q*prices[summary['first_open']][0]*F(10005,10000);receivable=F(0);peak=F(20000);dd=F(0);annual={};prior=F(20000)
        assert q==saved['order']['quantity']
        for row in saved['ledger']:
            day=row['date']
            if day>summary['first_open']:receivable+=q*divs.get(day,F(0))
            value=cash+q*prices[day][1]+receivable
            assert row['shares']==q and F(row['cash'])==cash and F(row['dividend_receivable'])==receivable and F(row['equity'])==value
            peak=max(peak,value);dd=max(dd,1-value/peak);year=day[:4]
            if year not in annual:annual[year]={'start':prior}
            annual[year].update(end=value,return_pct=float(value/annual[year]['start']-1)*100,end_date=day);prior=value
        assert abs(float(dd*100)-summary['drawdown_pct'])<1e-10
        reports.append(dict(window=summary['window'],daily_accounting_exact=True,dd_exact=True,annual=annual))
    (out/'independent_audit.json').write_text(json.dumps(reports,indent=2,default=str),encoding='utf-8');print(json.dumps(reports,indent=2,default=str))
if __name__=='__main__':run()
