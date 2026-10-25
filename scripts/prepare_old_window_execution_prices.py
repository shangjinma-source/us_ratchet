"""Prepare isolated nominal quote candidates; never run selection or a ledger."""
import csv,gzip,hashlib,json,sys
from collections import defaultdict
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/old_window_execution_prices_20261026'

def main():
    pins={};cache={}
    def norm(p):
        p=Path(p);return (p.relative_to(ROOT) if p.is_absolute() else p).as_posix()
    def read(p,expected=None):
        p=norm(p);b=(ROOT/p).read_bytes();h=hashlib.sha256(b).hexdigest()
        if expected and expected!=h:raise ValueError('SOURCE_CHANGED:'+p)
        if p in pins and pins[p]!=h:raise ValueError('PIN_CONFLICT:'+p)
        pins[p]=h;return b
    def doc(p,children=True):
        d=json.loads(read(p))
        if children:
            for s,h in d.get('source_hashes',{}).items():read(s,h)
        return d
    training_path='tmp/old_window_source_reuse_20261026/unified_raw_compilation_v3.json'
    training=doc(training_path)
    if training['pure_compiled_windows']!=31:raise ValueError('TRAINING_NOT_ALL_COMPILED')
    calendar=doc('tmp/old_window_official_calendar_20261026/review.json')
    recent=doc('tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json',False)
    lifecycle=doc('tmp/old_holdings_lifecycle_gate_20261026/review.json')
    doc('tmp/wba_terminal_official_20261026/review.json')
    doc('tmp/anss_terminal_bridge_20261026/review.json')
    doc('tmp/ea_splk_lifecycle_20261026/review.json')
    read('scripts/prepare_old_window_execution_prices.py')
    sessions=[d for d in calendar['official_sessions'] if '2023-12-29'<=d<='2026-07-30']
    fixed={norm(r['source']):r for r in recent['fixed_sources']}
    def quotes(path,ticker):
        path=norm(path)
        if path in cache:return cache[path]
        raw=read(path);events=[];actions=[]
        if path.endswith('.csv'):
            rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()));bars={}
            for r in rows:
                d=r.get('date',r.get('Date'))
                if d[4:5]!='-':d=datetime.strptime(d,'%d-%m-%Y').date().isoformat()
                bar={k:r.get(k,r.get(k.title())) for k in ('open','high','low','close')}
                if all(v is not None and str(v).strip() for v in bar.values()):bars[d]=bar
        elif path.endswith('web_observation.json'):
            d=json.loads(raw,parse_float=str)
            bars={r['date']:{k:r[k] for k in ('open','high','low','close')} for r in d['rows']}
        else:
            chart=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
            if chart['meta']['symbol']!=ticker:raise ValueError('SYMBOL_MISMATCH:'+ticker)
            zone=ZoneInfo(chart['meta']['exchangeTimezoneName']);q=chart['indicators']['quote'][0];bars={}
            for i,t in enumerate(chart['timestamp']):
                bar={k:q[k][i] for k in ('open','high','low','close')}
                if all(v is not None for v in bar.values()):bars[datetime.fromtimestamp(t,zone).date().isoformat()]=bar
            for kind,items in chart.get('events',{}).items():
                for event in items.values():
                    day=datetime.fromtimestamp(event['date'],zone).date().isoformat()
                    actions.append(dict(kind=kind,date=day,provider_payload=event))
                    if kind=='splits':events.append(dict(date=day,factor=str(Fraction(event['numerator'])/Fraction(event['denominator']))))
        nominal={}
        for day,bar in bars.items():
            if day not in sessions:continue
            factor=Fraction(1)
            for event in events:
                if day<event['date']:factor*=Fraction(event['factor'])
            if path in fixed and ticker in ('AZN','SIRI','ILMN'):
                factor=Fraction(fixed[path]['calibration']['factor'])
                for event in fixed[path].get('provider_coordinate_events',[]):
                    if day>=event['date'] and event.get('apply_nominal_scale'):factor/=Fraction(event['factor'])
            values={k:str(Fraction(v)*factor) for k,v in bar.items()}
            if any(Fraction(v)<=0 for v in values.values()):raise ValueError('INVALID_OHLC:'+ticker+':'+day)
            if Fraction(values['high'])<max(Fraction(values['open']),Fraction(values['close']),Fraction(values['low'])):raise ValueError('INVALID_HIGH:'+ticker+':'+day)
            if Fraction(values['low'])>min(Fraction(values['open']),Fraction(values['close'])):raise ValueError('INVALID_LOW:'+ticker+':'+day)
            nominal[day]=values
        cache[path]=(nominal,events,actions);return cache[path]
    candidates=defaultdict(list);identities=defaultdict(dict)
    for w in training['windows']:
        for c in w['candidates']:
            if c['status']=='EXCLUDED_TRAINING_RULE':continue
            candidates[c['ticker']].append((w['decision_date'],c))
            identities[c['ticker']].setdefault(c['security_id'],[]).append(w['decision_date'])
    terminal={'ANSS':'2025-07-16','SPLK':'2024-03-15','WBA':'2025-08-27'}
    special={'ANSS':'tmp/anss_terminal_bridge_20261026/ANSS_price_candidate.csv',
        'SPLK':'tmp/splk_sgen_bridge_20261025/SPLK.csv','WBA':'tmp/chartexchange_three_probe_20261025/WBA.csv'}
    prices={};routes={};comparisons=[];gaps=[]
    for ticker,observations in sorted(candidates.items()):
        paths=[]
        if ticker in special:paths.append(special[ticker])
        paths += [norm(c['training_source']) for _,c in reversed(observations)]
        paths=list(dict.fromkeys(paths));captured=[]
        for path in paths:
            values,events,actions=quotes(path,ticker)
            captured.append((path,values,events,actions))
        joined={};selection={}
        for path,values,_,_ in reversed(captured):
            for day,bar in values.items():joined[day]=bar;selection[day]=path
        if ticker=='EA':
            ep='tmp/next12_ea_alternate_source_20261014_v1/web_observation.json'
            values,events,actions=quotes(ep,ticker);captured.append((ep,values,events,actions))
            for day,bar in values.items():
                if day>='2026-06-30':joined[day]=bar;selection[day]=ep
        if ticker in terminal:
            joined={d:v for d,v in joined.items() if d<=terminal[ticker]};selection={d:v for d,v in selection.items() if d<=terminal[ticker]}
        first=observations[0][0]
        required=[d for d in sessions if first<=d<=terminal.get(ticker,sessions[-1])]
        missing=[d for d in required if d not in joined]
        if missing:gaps.append(dict(ticker=ticker,missing_sessions=missing,first_required=first,scope='POTENTIALLY_HELD_AFTER_INDEX_EXIT'))
        overlaps=[]
        for index,(left,lv,_,_) in enumerate(captured):
            for right,rv,_,_ in captured[index+1:]:
                days=sorted(set(lv)&set(rv))
                if not days:continue
                maximum=max(abs(Fraction(lv[d][k])-Fraction(rv[d][k])) for d in days for k in ('open','high','low','close'))
                overlaps.append(dict(first_source=left,second_source=right,days=len(days),maximum_ohlc_difference=str(maximum),source_priority_not_blended=True))
        prices[ticker]=joined
        routes[ticker]=dict(priority_sources=paths,source_by_date=selection,source_overlaps=overlaps,
            known_last_trading_date=terminal.get(ticker),retained_after_index_exit=True,
            identity_observations=identities[ticker],identity_migration_required=len(identities[ticker])>1,
            coordinate_events_by_source={p:e for p,_,e,_ in captured},provider_actions_by_source={p:a for p,_,_,a in captured},
            source_action_stream_absent=[p for p,_,_,a in captured if not a],execution_authorized=False,
            unmodeled_reorganization_gate=(ticker=='SIRI'),terminal_rights_gate=ticker in terminal)
        for day,c in observations:
            bar=joined.get(day)
            if bar is None:comparisons.append(dict(decision_date=day,ticker=ticker,status='MISSING_DECISION_QUOTE'));continue
            old=Fraction(c['decision_cost']);actual=Fraction(bar['close']);delta=actual-old
            comparisons.append(dict(decision_date=day,ticker=ticker,security_id=c['security_id'],old_cost=str(old),nominal_close=str(actual),delta=str(delta),source=selection[day],
                status='EXACT' if delta==0 else ('WITHIN_ONE_CENT_NOT_EXACT' if abs(delta)<=Fraction('0.01') else 'MATERIAL_CONFLICT')))
    for p,h in pins.items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_CHANGED_DURING_RUN:'+p)
    result=dict(schema='OLD_WINDOW_EXECUTION_PRICE_CANDIDATES_V1',training_input=training_path,training_sha256=pins[training_path],
        source_hashes=pins,session_dates=sessions,ohlc_candidates_by_ticker=prices,source_routes=routes,decision_cost_comparisons=comparisons,
        retained_holding_price_gaps=gaps,execution_authorized=False,search_calls=0,economic_runs=0,
        limitations=['Ticker quote candidates are not an executable security-id ledger. Dated identities and actual corporate actions remain mandatory gates.',
            'Potentially held securities retain quotes after membership exit until verified last trading dates; termination preserves entitlement obligations.',
            'Provider factors restore nominal price coordinates only. They are not automatic share conversions or dividend amounts.',
            'No cash dividend, merger receivable or distributed child entitlement has been silently counted as cash.',
            'Cost representation differences are reported, never overwritten in training or quote bars.',
            'Data for unpriced future distributed rights requires actual-exposure admission; excluded short-history members are not deleted from training evidence.'])
    OUT.mkdir(exist_ok=True)
    target=OUT/'execution_prices_v1.json';target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    counts={s:sum(r['status']==s for r in comparisons) for s in sorted({r['status'] for r in comparisons})}
    print(json.dumps(dict(tickers=len(prices),sessions=len(sessions),decision_checks=len(comparisons),comparison_status=counts,gap_tickers=len(gaps),sha256=hashlib.sha256(target.read_bytes()).hexdigest())))

if __name__=='__main__':main()
