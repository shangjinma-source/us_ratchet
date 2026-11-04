"""Frozen QQQ market-state counts; no account returns or selection."""
import gzip
import hashlib
import json
from decimal import Decimal, localcontext
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
NAMES=['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']

def sequence(panel, days):
    with localcontext() as context:
        context.prec=80
        ema=sum(panel[d]['close'] for d in days[:20])/20
        result={}
        for i,day in enumerate(days[20:],20):
            ema+=(panel[day]['close']-ema)*Decimal(2)/21
            if i>=252:
                result[day]=dict(close=str(panel[day]['close']),ema=str(ema),on=panel[day]['close']>ema)
        return result

def main():
    pinned=json.loads((ROOT/'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json').read_bytes())['base_file_dependencies']
    panels=[];hashes={}
    for name in NAMES:
        raw=(ROOT/name).read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest()
        assert hashes[name]==pinned[name]
        r=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
        assert r['meta']['symbol']=='QQQ' and not r.get('events',{}).get('splits')
        quote=r['indicators']['quote'][0]
        panels.append({datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat():{k:Decimal(str(quote[k][i])) for k in ('open','close')} for i,t in enumerate(r['timestamp']) if all(quote[k][i] is not None for k in ('open','close'))})
    overlap=set(panels[0])&set(panels[1]);assert all(panels[0][d]==panels[1][d] for d in overlap)
    panel={**panels[0],**panels[1]};days=sorted(panel);signals=sequence(panel,days)
    assert days[252]=='2020-12-31'
    for cutoff in ('2020-12-31','2023-12-29','2026-07-30'):
        prefix=sequence(panel,[d for d in days if d<=cutoff])
        assert all(v==signals[d] for d,v in prefix.items())
    monthends={}
    for d in days:monthends[d[:7]]=d
    results=[]
    for anchor,end in [('2020-12-31','2023-12-29'),('2023-12-29','2026-07-30')]:
        sessions=[d for d in days if anchor<d<=end]
        states={mode:signals[anchor]['on'] for mode in ('daily','monthly_reentry')}
        transitions={mode:[] for mode in states};ledger=[]
        for execution in sessions:
            prior=days[days.index(execution)-1];assert prior<execution
            raw=signals[prior]['on'];previous=states.copy()
            states['daily']=raw
            if not raw:states['monthly_reentry']=False
            elif prior==monthends[prior[:7]]:states['monthly_reentry']=True
            for mode in states:
                if states[mode]!=previous[mode]:transitions[mode].append(dict(signal_date=prior,execution_date=execution,on=states[mode]))
            ledger.append(dict(date=execution,signal_date=prior,**states,
                delayed_reentry=states['daily'] and not states['monthly_reentry'],
                close_above_open=panel[execution]['close']>panel[execution]['open']))
        delayed=[r for r in ledger if r['delayed_reentry']]
        results.append(dict(anchor=anchor,end=end,sessions=len(sessions),initial_market_on=signals[anchor]['on'],
            transitions={mode:dict(count=len(rows),entries=sum(r['on'] for r in rows),exits=sum(not r['on'] for r in rows),rows=rows) for mode,rows in transitions.items()},
            delayed_reentry_sessions=len(delayed),delayed_sessions_up_intraday=sum(r['close_above_open'] for r in delayed),
            note='Initial state is not a transition. These are market-state switches, not executed trades or account returns.',ledger=ledger))
    output=ROOT/'tmp/ema20_market_states_20261105';output.mkdir(exist_ok=True)
    (output/'result.json').write_text(json.dumps(dict(source_hashes=hashes,overlap_equal=len(overlap),seed_first_day=days[0],seed_sma20_end=days[19],first_253_ready=days[252],precision=80,causal_prefix_checks=True,signals=signals,windows=results),indent=2),encoding='utf-8')
    print(json.dumps([{k:({mode:{a:b for a,b in v.items() if a!='rows'} for mode,v in val.items()} if k=='transitions' else val) for k,val in r.items() if k!='ledger'} for r in results],indent=2))

if __name__=='__main__':main()
