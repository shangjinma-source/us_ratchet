"""Existing-source arithmetic only; proportional cash-flow scenarios."""
import json,gzip
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime,date
from zoneinfo import ZoneInfo
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2]

def run():
    saved=json.loads((ROOT/'tmp/annual_contribution_estimate_20261104/exact_result.json').read_bytes())
    manifest=json.loads((ROOT/'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json').read_bytes())
    sources=['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']
    panels=[];pins={};event_counts=[]
    for name in sources:
        raw=(ROOT/name).read_bytes();pins[name]=sha256(raw).hexdigest();assert pins[name]==manifest['base_file_dependencies'][name]
        body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
        assert body['meta']['symbol']=='QQQ' and not body.get('events',{}).get('splits')
        panel={datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat():dict(close=body['indicators']['quote'][0]['close'][i],adjusted=body['indicators']['adjclose'][0]['adjclose'][i]) for i,t in enumerate(body['timestamp'])}
        panels.append(panel);event_counts.append(len(body.get('events',{}).get('dividends',{})))
    dates=[r['date'] for r in saved['arms']['baseline']['daily']]
    curves={mode:arm['daily'] for mode,arm in saved['arms'].items()}
    for field in ['close','adjusted']:
        asset=F(50000);invested=F(50000);unit=F(1);previous_day='2020-12-31';rows=[];year=None
        for day in dates:
            panel=panels[0] if day<='2023-12-29' else panels[1]
            assert panel[day][field] is not None and panel[previous_day][field] is not None
            if day[:4]!=year:asset+=50000;invested+=50000;year=day[:4]
            gross=F(panel[day][field])/F(panel[previous_day][field]);unit*=gross;asset*=gross
            rows.append(dict(date=day,asset=str(asset),invested=str(invested),unit_nav=str(unit)))
            previous_day=day
        curves['QQQ_'+field]=rows
    results={}
    for name,rows in curves.items():
        peak=F(1);peak_day='2020-12-31';worst=F(0);worst_peak=worst_trough=None;annual={};below=[];episodes=[];begin=None
        for r in rows:
            asset,unit,invested=map(F,[r['asset'],r['unit_nav'],r['invested']]);day=r['date']
            if unit>=peak:peak=unit;peak_day=day
            if 1-unit/peak>worst:worst=1-unit/peak;worst_peak=peak_day;worst_trough=day;worst_peak_unit=peak
            underwater=asset<invested
            if underwater:below.append(day)
            if underwater and begin is None:begin=day
            if not underwater and begin is not None:episodes.append(dict(start=begin,recovered=day,calendar_days=(date.fromisoformat(day)-date.fromisoformat(begin)).days));begin=None
            annual[day[:4]]=dict(date=day,asset=asset,invested=invested,net_gain=asset-invested,unit_nav=unit)
        if begin:episodes.append(dict(start=begin,recovered=None,calendar_days=(date.fromisoformat(rows[-1]['date'])-date.fromisoformat(begin)).days))
        recovery=next((r['date'] for r in rows if r['date']>worst_trough and F(r['unit_nav'])>=worst_peak_unit),None)
        end=rows[-1]['date'];a=annual['2025']
        results[name]=dict(annual=annual,end_asset=F(rows[-1]['asset']),net_gain=F(rows[-1]['asset'])-350000,
            principal_underwater_sessions=len(below),sessions=len(rows),principal_underwater_episodes=episodes,
            maximum_drawdown=worst,peak=worst_peak,trough=worst_trough,recovery=recovery,
            peak_to_recovery_or_end_days=(date.fromisoformat(recovery or end)-date.fromisoformat(worst_peak)).days,
            without_2026=dict(end_asset=a['asset'],invested=300000,net_gain=a['asset']-300000,time_weighted_return=a['unit_nav']-1))
    overlap=sorted(set(panels[0])&set(panels[1]));mismatches=sum(F(panels[0][d]['close'])!=F(panels[1][d]['close']) for d in overlap if panels[0][d]['close'] and panels[1][d]['close'])
    output=dict(scope='Existing daily return mapping; strategy segments not one continuous integer-share account. QQQ no transaction costs/tax; close excludes dividends; adjusted is vendor dividend-adjusted proxy, not independently certified total return. Annual first-session deposits receive full close-to-close return approximation.',source_hashes=pins,dividend_event_counts=event_counts,overlap_close_mismatches=mismatches,overlap_dates=len(overlap),results=results)
    target=ROOT/'tmp/qqq_contribution_comparison_20261104';target.mkdir(exist_ok=True);(target/'result.json').write_text(json.dumps(output,indent=2,default=float),encoding='utf-8')
    print(json.dumps(output,indent=2,default=float))
if __name__=='__main__':run()
