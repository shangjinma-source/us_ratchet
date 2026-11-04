"""One existing-dividend WDC lookback pair; preserve frozen parent and all other data."""
import json,gzip,hashlib
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime
from zoneinfo import ZoneInfo
from copy import deepcopy

ROOT=Path(__file__).resolve().parents[2]
PARENT='tmp/risk_budget_pair_extension_20261105/risk_inputs_zero_event_frontier_v1.json'
EXPECTED='2860c13da7db7b888581b4c4e60090f87e92b19c55ed3dd2b0e22c0e45a7cdbc'
SID='security:0000106040:958102105'
DATE='2026-01-30'

def main():
    raw=(ROOT/PARENT).read_bytes();assert hashlib.sha256(raw).hexdigest()==EXPECTED
    parent=json.loads(raw);pins=dict(parent['source_hashes'])
    for name,expected in pins.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    training_path='tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json'
    execution_path='tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
    training=json.loads((ROOT/training_path).read_bytes());execution=json.loads((ROOT/execution_path).read_bytes())
    window=next(w for w in training['windows'] if w['decision_date']==DATE)
    candidate=next(c for c in window['candidates'] if c.get('security_id')==SID)
    dates=window['training_dates'][-64:];values=list(map(F,candidate['training_close'][-64:]))
    assert dates[0]=='2025-10-29' and len(dates)==64
    source=candidate['training_source'];body=(ROOT/source).read_bytes()
    data=json.loads(gzip.decompress(body) if body[:2]==b'\x1f\x8b' else body,parse_float=str)['chart']['result'][0]
    prices={datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat():F(data['indicators']['quote'][0]['close'][i])
            for i,t in enumerate(data['timestamp']) if data['indicators']['quote'][0]['close'][i] is not None}
    nominal=execution['ohlc'][SID]
    assert all(values[i]==prices[d]==F(nominal[d]['close']) for i,d in enumerate(dates))
    events=[]
    for kind,event_map in data.get('events',{}).items():
        for event in event_map.values():
            day=datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat()
            if dates[0]<day<=DATE:events.append((kind,day,event))
    assert len(events)==1 and events[0][0:2]==('dividends','2025-12-04')
    mapped=[e for e in execution['dividend_events'] if e['security_id']==SID and dates[0]<e['ex_date']<=DATE]
    assert len(mapped)==1 and mapped[0]['ex_date']=='2025-12-04' and F(mapped[0]['amount_per_share'])==F(1,8)
    assert F(events[0][2]['amount'])==F(1,8)
    dividends={mapped[0]['ex_date']:F(mapped[0]['amount_per_share'])}
    gross={d:str((values[i]+dividends.get(d,F(0)))/values[i-1]) for i,d in enumerate(dates) if i}
    # Independent economic arithmetic from nominal execution bars, not trained closes.
    independent={d:str((F(nominal[d]['close'])+dividends.get(d,F(0)))/F(nominal[dates[i-1]]['close'])) for i,d in enumerate(dates) if i}
    assert gross==independent
    extension=deepcopy(parent);row=next(r for r in extension['windows'] if r['window']=='later' and r['decision_date']==DATE)
    assert SID not in row['arguments']['stock_gross_returns']
    assert set(gross)==set(row['arguments']['qqq_gross_returns'])
    row['arguments']['stock_gross_returns'][SID]=gross
    row.setdefault('extension_pair_evidence',[]).append(dict(window='later',decision_date=DATE,security_id=SID,ticker='WDC',
        basis='EXISTING_REVIEWED_DIVIDEND_POST_SPINOFF_NOMINAL_EQUALS_TRAINING_RAW',first_close=dates[0],last_close=DATE,
        source=source,source_sha256=hashlib.sha256(body).hexdigest(),mapped_dividend=mapped[0],
        unit_check='All64 training closes equal raw and frozen nominal execution closes; no interval split/distribution.'))
    extension['parent_artifact']=dict(path=PARENT,sha256=EXPECTED)
    extension['extension_scope']='Only later2026-01-30 WDC added; all parent pairs/QQQ/targets/equity unchanged. Parent2729 extension preserved.'
    extension['source_hashes'][PARENT]=EXPECTED
    extension['source_hashes'][Path(__file__).relative_to(ROOT).as_posix()]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    target=ROOT/'tmp/risk_budget_pair_extension_20261105/risk_inputs_wdc_v2.json'
    target.write_text(json.dumps(extension,indent=2),encoding='utf8')
    # Exact restoration confirms no other window fields changed.
    restored=deepcopy(extension)
    restored_row=next(r for r in restored['windows'] if r['window']=='later' and r['decision_date']==DATE)
    restored_row['arguments']['stock_gross_returns'].pop(SID)
    restored_row['extension_pair_evidence'].pop()
    assert restored['windows']==parent['windows']
    report=dict(status='WDC_EXISTING_DIVIDEND_PAIR_PREPARED_AND_NOMINAL_ARITHMETIC_PASS',parent=extension['parent_artifact'],
                artifact_path=target.relative_to(ROOT).as_posix(),artifact_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                changed_pairs=[dict(window='later',decision_date=DATE,security_id=SID)],checked_returns=63,
                mapped_dividend=mapped[0],source_hashes=extension['source_hashes'],network_calls=0,economic_runs=0,
                limits='Conditional frozen price/action sources; January WDC window is wholly after February2025 spinoff. Issuer dividend accrual not assumed broker cash availability.')
    (target.parent/'wdc_extension_review.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_hashes','mapped_dividend')}))

if __name__=='__main__':main()
