"""Local raw-signal/cost cross-check for seven early windows, without search."""
import csv, gzip, hashlib, json, sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/old_window_source_reuse_20261026/early_raw_routes_v1.json'

def main():
    pins={}; cache={}
    def norm(p):
        p=Path(p);return (p.relative_to(ROOT) if p.is_absolute() else p).as_posix()
    def read(p,expected=None):
        p=norm(p);b=(ROOT/p).read_bytes();h=hashlib.sha256(b).hexdigest()
        if expected and expected!=h:raise ValueError('SOURCE_CHANGED:'+p)
        pins[p]=h;return b
    def doc(p,children=False):
        d=json.loads(read(p))
        if children:
            for source,h in d.get('source_hashes',{}).items():read(source,h)
        return d
    oldpath='tmp/historical_training_prepare_20261014_v4/prepared.json'
    old=doc(oldpath,True)
    timeline=doc('tmp/old_window_membership_timeline_20261026/timeline.json')
    calendar=doc('tmp/old_window_official_calendar_20261026/review.json')
    eligibility=doc('tmp/old_window_regular_way_20261026/review.json')
    inventory=doc('tmp/old_window_source_reuse_20261026/inventory.json')
    doc('tmp/old_window_nominal_anchor_20261026/review.json',True)
    doc('tmp/ilmn_coordinate_review_20261026/review.json',True)
    doc('tmp/three_spinoff_signal_review_20261026/review.json',True)
    fixed=doc('tmp/fixed12_training_prepare_20261014_v6/prepared.json',True)
    later=doc('tmp/next12_training_prepare_20261014_v1/prepared.json',True)
    read('scripts/prepare_old_early_raw_routes.py')
    def quotes(p,ticker):
        p=norm(p)
        if p in cache:return cache[p]
        b=read(p)
        if p.endswith('.csv'):
            rows=list(csv.DictReader(b.decode('utf-8-sig').splitlines()))
            values={r.get('Date',r.get('date')):r.get('Close',r.get('close')) for r in rows}
            events=[]
        else:
            c=json.loads(gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b,parse_float=str)['chart']['result'][0]
            if c['meta']['symbol']!=ticker:raise ValueError('SYMBOL_MISMATCH:'+ticker)
            zone=ZoneInfo(c['meta']['exchangeTimezoneName']);q=c['indicators']['quote'][0]['close']
            values={datetime.fromtimestamp(t,zone).date().isoformat():q[i] for i,t in enumerate(c['timestamp'])}
            events=[dict(date=datetime.fromtimestamp(e['date'],zone).date().isoformat(),factor=str(Fraction(e['numerator'])/Fraction(e['denominator']))) for e in c.get('events',{}).get('splits',{}).values()]
        cache[p]=(values,events);return values,events
    donor={}
    for document in (fixed,later):
        for w in document['windows']:
            for c in w['candidates']:donor.setdefault(c['ticker'],norm(c['training_source']))
    special={'ILMN':'tmp/fixed12_extended_quote_capture_20261014_v1/ILMN.response.bin',
        'ANSS':'tmp/anss_terminal_bridge_20261026/ANSS_price_candidate.csv',
        'SPLK':'tmp/splk_sgen_bridge_20261025/SPLK.csv',
        'WBA':'tmp/chartexchange_three_probe_20261025/WBA.csv'}
    old_by_day={w['decision_cutoff']:w for w in old['windows']}
    prior_ids={c['ticker']:c for c in old['windows'][-1]['candidates']}
    short={(r['decision_date'],r['ticker']):r for r in eligibility['rows'] if r['status']=='EXCLUDED_SHORT_REGULAR_HISTORY'}
    outputs=[]
    for m in timeline['monthly_candidates'][:7]:
        day=m['decision_date'];days=[d for d in calendar['official_sessions'] if d<=day][-253:]
        oldwindow=old_by_day.get(day);ids={c['ticker']:c for c in oldwindow['candidates']} if oldwindow else prior_ids
        candidates=[]
        for ticker in m['members']:
            prior=ids.get(ticker);c=dict(ticker=ticker,blockers=[],source_references=[oldpath],identity_certified=False)
            if (day,ticker) in short:
                c.update(status='EXCLUDED_TRAINING_RULE',exclusion_evidence=short[(day,ticker)])
                candidates.append(c);continue
            if prior is None:
                c['blockers'].append('NO_PREDECISION_IDENTITY_EVIDENCE');c['status']='BLOCKED';candidates.append(c);continue
            c.update(security_id=prior['security_id'],issuer_id=prior['issuer_id'],identity_evidence=prior.get('identity_evidence'),identity_available_by_cutoff=prior.get('identity_available_by_cutoff'),identity_status=prior.get('identity_status'))
            if not prior.get('identity_available_by_cutoff'):c['blockers'].append('IDENTITY_NOT_AVAILABLE_BY_CUTOFF')
            paths=[]
            if ticker in special:paths.append(special[ticker])
            current='data/cache/research/current_raw_capture_20261014_v1/'+ticker+'.response.bin'
            if (ROOT/current).exists():paths.append(current)
            if ticker in donor:paths.append(donor[ticker])
            paths += [norm(r['path']) for r in inventory['rows'] if r['ticker']==ticker and r.get('first') and r['first']<=days[0] and r.get('last','')>=day]
            selected=None
            for path in dict.fromkeys(paths):
                try: values,events=quotes(path,ticker)
                except (KeyError,TypeError,IndexError):continue
                if all(values.get(d) is not None for d in days):selected=(path,values,events);break
            if selected is None:c['blockers'].append('NO_COMPLETE_RAW_SOURCE');c['status']='BLOCKED';candidates.append(c);continue
            path,values,events=selected
            factor=Fraction(1)
            for event in events:
                if event['date']>day:factor*=Fraction(event['factor'])
            cost=Fraction(values[day])*factor
            nominal_values={}
            for nominalpath in prior['raw_paths']:
                try: nv,_=quotes(nominalpath,ticker);nominal_values.update(nv)
                except (KeyError,TypeError,IndexError):continue
            nominal=nominal_values.get(day)
            if nominal is None:c['blockers'].append('NO_INDEPENDENT_NOMINAL_DECISION_OBSERVATION')
            elif abs(cost-Fraction(nominal))>Fraction('0.01'):c['blockers'].append('NOMINAL_DECISION_UNIT_DISAGREEMENT')
            if path.endswith('.csv') and ticker not in ('ANSS','SPLK','WBA'):
                c['blockers'].append('ARCHIVE_SPLIT_SIGNAL_POLICY_NOT_BOUND')
            c.update(training_source=norm(path),training_close=[str(Fraction(values[d])) for d in days],missing_training_dates=[],decision_cost=str(cost),
                nominal_crosscheck=dict(observed=nominal,restored=str(cost),difference=str(abs(cost-Fraction(nominal))) if nominal else None,
                    tolerance_usd='0.01',nominal_sources=prior['raw_paths']),coordinate_events=events,
                training_basis='FIXED_SOURCE_RAW_PRICE_SIGNAL_NOT_TOTAL_RETURN',status='BLOCKED' if c['blockers'] else 'READY_CONDITIONAL')
            candidates.append(c)
        outputs.append(dict(decision_cutoff=day,training_dates=days,candidates=candidates,members=m['members'],
            status='BLOCKED' if any(c['blockers'] for c in candidates) else 'READY_CONDITIONAL'))
    for p,h in pins.items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_CHANGED_DURING_RUN:'+p)
    result=dict(windows=outputs,source_hashes=pins,execution_authorized=False,search_calls=0,economic_runs=0,
        limitations=['Conditional historical identities are not complete PIT certification.',
        'Provider event multipliers restore price coordinates only, never security quantities.',
        'Raw ratios are price signals, not total return. Nominal observations cross-check to one US cent.'])
    OUT.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps([dict(date=w['decision_cutoff'],status=w['status'],blockers=[(c['ticker'],c['blockers']) for c in w['candidates'] if c['blockers']]) for w in outputs]))

if __name__=='__main__':main()
