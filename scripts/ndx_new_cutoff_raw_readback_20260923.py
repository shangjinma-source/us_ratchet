"""Independent raw channel observations only: no nominal reconstruction or identity."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PLAN_SHA = '96696abaaa7a8d9dc2765ce436ec2b312af74f4490243a963732bcf26bfedf71'
RUNNER_SHA = 'f26d8c29533d21c1ae35779f7eb8b3ff5ba9143632f9fe0091b3955bee4713bd'
FLAGS = ('prices_reconstructed','volume_unit_verified','complete_corporate_actions_verified',
         'historical_identity_verified','point_in_time_verified','legal_training_input_admitted','promotion_allowed')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path, expected, sources):
    path = str(Path(path).resolve())
    if path in sources and sources[path] != expected:
        raise ValueError('Conflicting source')
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Source SHA differs')
    sources[path] = expected
    return json.loads(raw)


def utc(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError('Aware UTC required')
    return result


def parse_channel(raw, ticker, receipt_day):
    body = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
    decoded = json.loads(body)
    chart = decoded['chart']
    if chart.get('error') is not None or len(chart.get('result') or []) != 1:
        raise ValueError('Single successful chart channel required')
    result = chart['result'][0]
    meta = result['meta']
    if meta['symbol'] != ticker or meta['exchangeTimezoneName'] != 'America/New_York':
        raise ValueError('Channel symbol or exchange timezone differs')
    timestamps = result['timestamp']
    if not timestamps or any(type(value) is not int for value in timestamps) or timestamps != sorted(set(timestamps)):
        raise ValueError('Strict unique increasing integer timestamps required')
    quotes = result['indicators']['quote']
    if len(quotes) != 1:
        raise ValueError('Single quote array required')
    arrays = {key:quotes[0][key] for key in ('open','high','low','close','volume')}
    adjusted = result['indicators'].get('adjclose')
    if adjusted is not None:
        if len(adjusted) != 1:
            raise ValueError('Ambiguous adjusted close')
        arrays['adjclose'] = adjusted[0]['adjclose']
    if any(len(array) != len(timestamps) for array in arrays.values()):
        raise ValueError('Quote and timestamp length differs')
    rows = []
    days = []
    for position, timestamp in enumerate(timestamps):
        day = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if day in days:
            raise ValueError('Multiple bars per New York day')
        days.append(day)
        values = {key:array[position] for key,array in arrays.items()}
        invalid = [key for key,value in values.items() if value is not None and
                   (type(value) not in (int,float) or not math.isfinite(value) or value < 0 or (key != 'volume' and value == 0))]
        if invalid:
            raise ValueError('Invalid raw numerical fields: ' + ','.join(invalid))
        rows.append(dict(timestamp_utc_epoch=timestamp, new_york_date=day, raw_provider_fields=values,
                         missing_fields=[key for key,value in values.items() if value is None],
                         excluded_receipt_day_or_later=day >= receipt_day))
    events = result.get('events', {})
    if not isinstance(events, dict):
        raise ValueError('Returned events object required')
    retained = [row for row in rows if not row['excluded_receipt_day_or_later']]
    return dict(ticker=ticker, decoded_sha256=hashlib.sha256(body).hexdigest(), rows=rows,
                raw_bar_count=len(rows), completed_date_bar_count=len(retained),
                last_completed_date=None if not retained else retained[-1]['new_york_date'],
                raw_provider_meta=meta, raw_returned_events=events,
                events_interpretation='UNCLASSIFIED_PROVIDER_PAYLOAD_NOT_COMPLETE_ACTION_CERTIFICATE',
                quote_price_unit='PROVIDER_RETURNED_NOT_CERTIFIED_NOMINAL',
                volume_unit='UNKNOWN_PROVIDER_UNIT_NO_SPLIT_ADJUSTMENT_ASSUMED', **dict.fromkeys(FLAGS,False))


def build(index_path, index_sha):
    sources = {str(SOURCE):LOADED_SHA}
    index = read(index_path,index_sha,sources)
    if index['schema'] != 'NEW_CUTOFF_RAW_CAPTURE_INDEX_V1' or index['plan_sha256'] != PLAN_SHA or index['runner_sha256'] != RUNNER_SHA:
        raise ValueError('Exact reviewed capture generation required')
    if index.get('prices_reconstructed') is not False or index.get('promotion_allowed') is not False:
        raise ValueError('Index scope cannot be upgraded')
    output = Path(index['output_directory'])
    expected_output = SOURCE.parents[1]/'data/cache/research/new_cutoff_raw_capture_20260923_v1'
    if output.resolve() != expected_output.resolve():
        raise ValueError('Dedicated raw capture root required')
    plan = read(output/'plan.json',PLAN_SHA,sources)
    entries = index['entries']
    if not entries or len(entries)>104 or [e['ticker'] for e in entries] != [r['ticker'] for r in plan['queue'][:len(entries)]]:
        raise ValueError('Nonempty exact queue prefix required')
    observations = []
    for entry in entries:
        ticker = entry['ticker']
        receipt_path = output/(ticker+'.receipt.json')
        if str(receipt_path) != entry['receipt_path']:
            raise ValueError('Receipt path differs')
        receipt = read(receipt_path,entry['receipt_sha256'],sources)
        started = read(output/(ticker+'.started.json'),receipt['started_sha256'],sources)
        if any(receipt.get(key)!=value for key,value in started.items()) or started['ticker'] != ticker or started['plan_sha256'] != PLAN_SHA or started['runner_sha256'] != RUNNER_SHA or type(started['attempt_count']) is not int or started['attempt_count']!=1:
            raise ValueError('Started binding differs')
        if started.get('request_method')!='GET' or started.get('credentials_sent') is not False or receipt.get('point_in_time_verified') is not False or receipt.get('promotion_allowed') is not False:
            raise ValueError('Receipt scope cannot be upgraded')
        start,received = utc(started['started_at_utc']),utc(receipt['received_at_utc'])
        start_day = start.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        receipt_day = received.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        row = next(row for row in plan['queue'] if row['ticker']==ticker)
        expected_url = row['request_url_template'].format(actual_request_start_utc_epoch=int(start.timestamp()))
        if start_day!='2026-09-23' or started['request_url']!=expected_url or receipt['completed_training_excludes_dates_on_or_after']!=receipt_day:
            raise ValueError('Clock, URL, or exclusion day differs')
        if row.get('prior_url_inventory_complete') is not True or row.get('prior_receipt') is None:
            raise ValueError('Prior inventory required')
        prior=urlparse(row['prior_receipt']['request_url']);query=parse_qs(prior.query,keep_blank_values=True)
        if prior.scheme!='https' or prior.netloc!='query1.finance.yahoo.com' or prior.path!='/v8/finance/chart/'+ticker or set(query)!={'period1','period2','interval','events'} or query['period1']!=['1640995200'] or query['interval']!=['1d'] or query['events']!=['div,splits'] or len(query['period2'])!=1 or not query['period2'][0].isdigit() or int(query['period2'][0])>=int(start.timestamp()):
            raise ValueError('Prior request is not an earlier exact channel URL')
        decoded_path=output/(ticker+'.decoded.json')
        if entry['decoded_path']!=str(decoded_path):
            raise ValueError('Decoded record path differs')
        decoded_record=read(decoded_path,entry['decoded_sha256'],sources)
        if decoded_record.get('ticker')!=ticker or decoded_record.get('receipt_sha256')!=entry['receipt_sha256'] or any(decoded_record.get(key) is not False for key in ('prices_reconstructed','cutoff_coverage_verified','promotion_allowed')):
            raise ValueError('Decoded scope or receipt binding differs')
        status = dict(ticker=ticker,receipt_sha256=entry['receipt_sha256'],http_status=receipt.get('http_status'),receipt_new_york_day=receipt_day)
        raw = None
        if 'raw_path' in receipt:
            raw_path = output/(ticker+'.response.bin')
            if str(raw_path)!=receipt['raw_path'] or sha(raw_path)!=receipt['raw_sha256'] or raw_path.stat().st_size!=receipt['raw_bytes']:
                raise ValueError('Raw bytes binding differs')
            sources[str(raw_path)] = receipt['raw_sha256']
            raw = raw_path.read_bytes()
        if raw is None or received<start or receipt_day!='2026-09-23' or receipt.get('final_url')!=expected_url or receipt.get('http_status')!=200:
            status['readback_status']='BLOCKED_RECEIPT_RETAINED_ATTEMPT_NO_RETRY'
        else:
            try:
                status.update(readback_status='RAW_CHANNEL_READBACK_ONLY',observation=parse_channel(raw,ticker,receipt_day))
            except (ValueError,KeyError,TypeError,OverflowError,OSError,EOFError) as error:
                status.update(readback_status='BLOCKED_RAW_SCHEMA_NO_RETRY',error_type=type(error).__name__)
        observations.append(status)
    for path,expected in sources.items():
        if sha(path)!=expected:
            raise ValueError('Source changed during readback')
    return dict(schema='NEW_CUTOFF_INDEPENDENT_RAW_READBACK_V1',index_path=str(Path(index_path).resolve()),index_sha256=index_sha,
                attempted_prefix_count=len(entries),queue_count=104,rows=observations,source_hashes=sources,
                capture_decoded_record_hash_and_scope_checked=True,raw_decoding_reperformed_independently=True,
                scope='RAW_PROVIDER_OBSERVATIONS_ONLY_NO_SECURITY_OR_ADJUSTMENT_ATTESTATION',**dict.fromkeys(FLAGS,False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',required=True);parser.add_argument('--index-sha',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=build(args.index,args.index_sha)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    if sha(path)!=hashlib.sha256(raw).hexdigest() or any(sha(source)!=expected for source,expected in result['source_hashes'].items()):
        raise ValueError('Published output or bound sources changed')
    print(json.dumps(dict(path=str(path.resolve()),sha256=sha(path))))
