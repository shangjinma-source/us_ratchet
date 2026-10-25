"""Local raw-signal/cost cross-check for seven early windows, without search."""
import csv, gzip, hashlib, json, sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/old_window_source_reuse_20261026/early_raw_routes_v2.json'

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
    recent_path='tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'
    recent=doc(recent_path)
    recent_sources={norm(r['source']):r for r in recent['fixed_sources']}
    split_semantics='tmp/qqq_20201231_anchor_20261025/official_split_semantics_batch1.json'
    doc(split_semantics,True)
    read('scripts/prepare_old_early_raw_routes_v2.py')
    def quotes(p,ticker):
        p=norm(p)
        if p in cache:return cache[p]
        b=read(p)
        if p.endswith('.csv'):
            rows=list(csv.DictReader(b.decode('utf-8-sig').splitlines()))
            values={}
            for r in rows:
                day=r.get('Date',r.get('date'))
                if day[4:5]!='-':day=datetime.strptime(day,'%d-%m-%Y').date().isoformat()
                values[day]=r.get('Close',r.get('close'))
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
            paths += [norm(r['path']) for r in inventory['rows'] if r['ticker']==ticker and r.get('first') and r['first']<=day and r.get('last','')>=days[0]]
            selected=None
            partial=[]
            for path in dict.fromkeys(paths):
                if ticker=='ILMN' and path.endswith('.csv'):continue
                try: values,events=quotes(path,ticker)
                except (KeyError,TypeError,IndexError):continue
                if all(values.get(d) is not None for d in days):selected=(path,values,events);break
                partial.append((path,values,events))
            if selected is None:
                for right_path,right,right_events in partial:
                    if not right.get(day):continue
                    for left_path,left,left_events in partial:
                        if not left.get(days[0]):continue
                        overlap=sorted(d for d in set(left)&set(right) if left[d] is not None and right[d] is not None)
                        if len(overlap)<10:continue
                        maximum=max(abs(Fraction(left[d])-Fraction(right[d])) for d in overlap)
                        if maximum>Fraction('0.00001'):continue
                        joined=dict(left);joined.update(right)
                        if not all(joined.get(d) is not None for d in days):continue
                        selected=(right_path,joined,right_events)
                        c['training_segments']=dict(earlier_source=norm(left_path),priority_source=norm(right_path),overlap_days=len(overlap),max_close_difference=str(maximum),source_priority='RIGHT_SOURCE_WHERE_PRESENT_ELSE_LEFT')
                        break
                    if selected:break
            if selected is None:c['blockers'].append('NO_COMPLETE_RAW_SOURCE');c['status']='BLOCKED';candidates.append(c);continue
            path,values,events=selected
            factor=Fraction(1)
            for event in events:
                if event['date']>day:factor*=Fraction(event['factor'])
            if norm(path) in recent_sources and ticker in ('AZN','SIRI','ILMN'):
                fixed_source=recent_sources[norm(path)]
                read(path,fixed_source['sha256'])
                factor=Fraction(fixed_source['calibration']['factor'])
                c['frozen_nominal_calibration']=dict(source=recent_path,calibration=fixed_source['calibration'])
            cost=Fraction(values[day])*factor
            nominal_values={}
            for nominalpath in prior['raw_paths']:
                try: nv,_=quotes(nominalpath,ticker);nominal_values.update(nv)
                except (KeyError,TypeError,IndexError):continue
            if day not in nominal_values:
                for p in (ROOT/'data/cache/research/root_price_byte_archive_20260919_v1').glob(ticker+'.*.csv'):
                    nv,_=quotes(p,ticker)
                    overlap=[d for d in set(nv)&set(nominal_values) if nv[d] and nominal_values[d]]
                    if len(overlap)<10 or any(abs(Fraction(nv[d])-Fraction(nominal_values[d]))>Fraction('0.01') for d in overlap):continue
                    if nv.get(day):
                        c['nominal_archive_bridge']=dict(source=norm(p),overlap_days=len(overlap),tolerance_usd='0.01')
                        nominal_values.update(nv);break
            nominal=nominal_values.get(day)
            if nominal is None:
                anchor_day='2024-05-31'
                anchor=nominal_values.get(anchor_day)
                anchor_factor=Fraction(1)
                for event in events:
                    if event['date']>anchor_day:anchor_factor*=Fraction(event['factor'])
                if anchor and values.get(anchor_day) and abs(Fraction(values[anchor_day])*anchor_factor-Fraction(anchor))<=Fraction('0.01'):
                    interval_events=[e for e in events if anchor_day<e['date']<=day]
                    allowed={('NVDA','2024-06-10','10'):split_semantics,('ILMN','2024-06-25','257/250'):'tmp/ilmn_coordinate_review_20261026/review.json'}
                    if any((ticker,e['date'],e['factor']) not in allowed for e in interval_events):c['blockers'].append('UNREVIEWED_ANCHOR_EXTENSION_EVENT')
                    c['nominal_cost_extension']=dict(anchor_date=anchor_day,anchor_price=anchor,restored_anchor=str(Fraction(values[anchor_day])*anchor_factor),
                        anchor_sources=prior['raw_paths'],decision_factor=str(factor),status='CALIBRATION_EXTENDED_NOT_INDEPENDENT_DAILY_ANCHOR',
                        interval_reviewed_coordinate_events=[dict(**e,source_reference=allowed.get((ticker,e['date'],e['factor']))) for e in interval_events],
                        assumption='SAME_PROVIDER_PRICE_COORDINATE_WITH_ONLY_RETURNED_EVENTS_BETWEEN_ANCHOR_AND_DECISION',independently_anchored_at_decision=False)
                else:c['blockers'].append('NO_INDEPENDENT_NOMINAL_DECISION_OBSERVATION')
            elif abs(cost-Fraction(nominal))>Fraction('0.01'):c['blockers'].append('NOMINAL_DECISION_UNIT_DISAGREEMENT')
            if path.endswith('.csv') and ticker not in ('ANSS','SPLK','WBA','EA'):
                c['blockers'].append('ARCHIVE_SPLIT_SIGNAL_POLICY_NOT_BOUND')
            if ticker=='EA' and path.endswith('.csv'):
                c['archive_conditional_admission']=dict(source='tmp/fixed12_training_prepare_20261014_v6/prepared.json',
                    basis='INHERITED_CONDITIONAL_ARCHIVE_NO_SPLIT_PRICE_SIGNAL_NOT_AUTHENTICATED')
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
