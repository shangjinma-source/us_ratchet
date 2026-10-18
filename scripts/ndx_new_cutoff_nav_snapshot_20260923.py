"""Copy a hard-pinned local NAV observation; no fetch, mapping or returns."""
import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
SOURCE_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/new_cutoff_nav_snapshot_20260923_v1'
INPUTS={
    'nav.csv':(ROOT/'data/cache/funds/012922.csv','020f3e636c732259dedb796606de49b89a0ee7df0263442ddae5f3e73dc76d1f'),
    'original_manifest.json':(ROOT/'data/cache/funds/012922.csv.manifest.json','dcb18867c3b4f75192927ca66f05ad972490bbf6b45f0aea275af4547575ae38'),
}


def require(condition,message):
    if not condition:raise ValueError(message)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result


def validate(raw,metadata_raw):
    metadata=json.loads(metadata_raw,object_pairs_hook=unique)
    require(metadata['dataset_key']==metadata['fund_code']=='012922' and metadata['dataset_type']=='fund_nav',
        'Exact fund identity required')
    require(metadata['content_sha256']==digest(raw) and type(metadata['content_bytes']) is int and
        metadata['content_bytes']==len(raw),'NAV bytes disagree with local manifest')
    require(metadata['publication_time_known'] is False,'Publication availability remains unknown')
    stamp=datetime.fromisoformat(metadata['fetched_at'])
    require(stamp.tzinfo is not None and stamp.utcoffset().total_seconds()==0,'Aware UTC fetch observation required')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    require(reader.fieldnames==['Date','UnitNav','AccumNav','DailyPct','Close'],'Exact observed CSV schema required')
    rows=list(reader);days=[]
    for row in rows:
        require(set(row)==set(reader.fieldnames) and all(value is not None for value in row.values()),'Malformed CSV row')
        day=row['Date'];require(date.fromisoformat(day).isoformat()==day,'Canonical NAV date required');days.append(day)
        values={key:Decimal(row[key]) for key in ('UnitNav','AccumNav','Close')}
        require(all(v.is_finite() and v>0 for v in values.values()),'Positive finite NAV fields required')
        require(values['Close']==values['UnitNav'],'Close must preserve the saved unit NAV convention')
        if row['DailyPct']:require(Decimal(row['DailyPct']).is_finite(),'Finite optional source DailyPct required')
    require(days==sorted(set(days)) and len(days)==1101 and days[0]=='2022-01-11' and days[-1]=='2026-09-21',
        'Exact unique observed NAV range/count required')
    require(type(metadata['row_count']) is int and type(metadata['source_record_count']) is int and
        metadata['row_count']==metadata['source_record_count']==len(rows) and
        metadata['data_start']==days[0] and metadata['data_end']==days[-1],'Manifest row/date denominator differs')
    return dict(row_count=len(rows),data_start=days[0],data_end=days[-1],observed_fetch_time=metadata['fetched_at'],
        selected_value_column='Close',selected_value_convention='SAVED_UNIT_NAV_NOT_ACCUMULATED_NAV',
        source_page_count_claim=metadata['source_page_count'],source_pagination_independently_reverified=False)


def guard():
    require(digest(SOURCE.read_bytes())==SOURCE_SHA,'Loaded snapshot source changed')
    for path,sha in INPUTS.values():require(digest(path.read_bytes())==sha,'Original local NAV input changed')


def publish_bytes(path,raw):
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Published bytes changed')
    return dict(path=str(path),sha256=digest(raw))


def run():
    require(not OUTPUT.exists(),'Fresh fixed snapshot namespace required')
    guard();buffers={name:path.read_bytes() for name,(path,sha) in INPUTS.items()}
    for name,raw in buffers.items():require(digest(raw)==INPUTS[name][1],'Capture bytes changed')
    result=validate(buffers['nav.csv'],buffers['original_manifest.json']);guard()
    OUTPUT.mkdir(parents=True,exist_ok=False)
    copies={name:publish_bytes(OUTPUT/name,raw) for name,raw in buffers.items()}
    guard()
    report=dict(schema='NEW_CUTOFF_LOCAL_NAV_BYTES_SNAPSHOT_V1',captured_at_utc=datetime.now(timezone.utc).isoformat(),
        dataset_key='012922',observed_data=result,immutable_copies=copies,
        original_inputs_at_capture={name:dict(path=str(path),sha256=sha) for name,(path,sha) in INPUTS.items()},
        source_hashes={str(SOURCE):SOURCE_SHA,**{ref['path']:ref['sha256'] for ref in copies.values()}},
        mutable_originals_are_capture_observations_not_future_dependencies=True,
        **dict.fromkeys(('http_performed','original_files_modified','calendar_mapped','returns_calculated',
            'nav_publication_time_verified','currency_fx_equivalence_verified','fee_equivalence_verified',
            'legal_training_input_admitted','point_in_time_verified','promotion_allowed'),False))
    saved=publish_bytes(OUTPUT/'snapshot.json',(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())
    guard()
    for ref in [*copies.values(),saved]:require(digest(Path(ref['path']).read_bytes())==ref['sha256'],'Saved snapshot drift')
    require({p.name for p in OUTPUT.iterdir()}=={'nav.csv','original_manifest.json','snapshot.json'},'Unexpected snapshot files')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--publish',action='store_true')
    require(parser.parse_args().publish,'Explicit --publish required');print(json.dumps(run()))
