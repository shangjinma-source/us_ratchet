"""Freeze current source bytes and classify gaps without modifying calendar v2."""
import csv
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
OUTPUT = ROOT/'data/cache/research/observation_gap_classification_20261002_v1'
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PINS = {
 'calendar_manifest':('data/cache/research/ndx_observed_us_session_calendar_v2/manifest.json','68404f2b127e45a608a49010d8d8beead28c3957288e8276554b56ee72194e6a'),
 'calendar_events':('data/cache/research/ndx_observed_us_session_calendar_v2/events.jsonl','8cca71da136f454f0f0c45096ab5b8723ebecdb385c4c64364d0e073f695be30'),
 'classifier':('backtest/ndx_observation_gap_recovery_research.py','329dd75821dde94572d34c94b1bc40b2d1a03c14e2e18cf2906cf39805d01dcb')}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run():
    if OUTPUT.exists():
        raise ValueError('Fixed capture namespace exists; no retry')
    if sha(SOURCE.read_bytes())!=LOADED_SHA:
        raise ValueError('Loaded capture code changed')
    sources = {str(SOURCE):LOADED_SHA}; raw_sources = {}; references = {}
    for role,(relative,expected) in PINS.items():
        path=ROOT/relative; raw=path.read_bytes()
        if sha(raw)!=expected:
            raise ValueError('Source mismatch: '+role)
        sources[str(path)]=expected; raw_sources[role]=raw
        references[role]={'path':str(path),'sha256':expected}
    rows_by_ticker={}
    for ticker in ('QQQ','SPY'):
        path=ROOT/'data/cache'/f'{ticker}.csv'; raw=path.read_bytes()
        sources[str(path)]=sha(raw); raw_sources[ticker]=raw
        records=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        if not records or not {'Date','Open','High','Low','Close','Volume'}<=set(records[0]):
            raise ValueError('Complete source columns required')
        dates=[row['Date'] for row in records]
        if dates!=sorted(set(dates)):
            raise ValueError('Unique ordered source dates required')
        rows_by_ticker[ticker]={row['Date']:row for row in records}
    manifest=json.loads(raw_sources['calendar_manifest'])
    last=manifest['latest_session_date']
    if last!='2026-09-24':
        raise ValueError('Pinned parent tail changed')
    common=sorted((set(rows_by_ticker['QQQ']) & set(rows_by_ticker['SPY']))-{day for day in rows_by_ticker['QQQ'] if day<=last})
    module_name='backtest.ndx_observation_gap_recovery_research'
    if module_name in sys.modules:
        raise ValueError('Fresh CLI required')
    module=importlib.import_module(module_name)
    if Path(module.__file__).resolve()!=Path(references['classifier']['path']).resolve():
        raise ValueError('Classifier module path differs')
    recorded=datetime.now(timezone.utc).isoformat()
    classification=module.classify_gap_recovery(last_sealed_session=last,common_source_sessions=common,
        observed_at_utc=recorded,prospective_start_date='2026-10-01')
    result={'schema':'CURRENT_SOURCE_GAP_CLASSIFICATION_CAPTURE_V1','classification':classification,
        'captured_at_utc':recorded,'captured_using_system_clock':True,'source_hashes':sources,
        'captured_source_references':{ticker:{'path':str(OUTPUT/f'{ticker}.csv'),'sha256':sha(raw_sources[ticker])} for ticker in ('QQQ','SPY')},
        'parent_references':references,'pending_source_rows':{ticker:{day:rows[day] for day in common} for ticker,rows in rows_by_ticker.items()},
        'current_source_rows_do_not_prove_historical_first_observation':True,
        'parent_full_validation_reexecuted':False,'old_calendar_mutated':False,
        'calendar_append_allowed':False,'candidate_seal_allowed':False,'cohort_registration_allowed':False,
        'source_price_rows_validated_for_execution':False,'promotion_allowed':False,'live_mutation_allowed':False}
    result['timezone_rules_source_bound']=False
    def guard():
        if not all(sha(Path(path).read_bytes())==digest for path,digest in sources.items()):
            raise ValueError('Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        for ticker in ('QQQ','SPY'):
            with (OUTPUT/f'{ticker}.csv').open('xb') as stream:
                stream.write(raw_sources[ticker])
        raw=(json.dumps(result,sort_keys=True,indent=2)+'\n').encode()
        with (OUTPUT/'classification.json').open('xb') as stream:
            stream.write(raw)
        guard()
        if (OUTPUT/'classification.json').read_bytes()!=raw or any((OUTPUT/f'{ticker}.csv').read_bytes()!=raw_sources[ticker] for ticker in ('QQQ','SPY')):
            raise ValueError('Capture readback differs')
        return {'path':str(OUTPUT/'classification.json'),'sha256':sha(raw),'recorded_at_utc':recorded,
            'missed_or_ineligible_row_count':classification['missed_or_ineligible_row_count'],
            'timeliness_candidate':classification['timeliness_candidate']}
    except Exception:
        (OUTPUT/'FAILED_DO_NOT_CONSUME').touch(exist_ok=False)
        raise


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
