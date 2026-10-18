"""Capture the actual Nasdaq quote-list endpoint, without historical backfill."""
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://api.nasdaq.com/api/quote/list-type/nasdaq100'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


SOURCE = Path(__file__).resolve()
LOADED = sha(SOURCE.read_bytes())


def run(folder):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    headers = {'User-Agent':'Mozilla/5.0','Accept':'application/json','Referer':'https://www.nasdaq.com/'}
    metadata = dict(request_url=URL,request_method='GET',started_at_utc=started,credentials_sent=False)
    raw = None
    try:
        with urlopen(Request(URL,headers=headers),timeout=25) as response:
            raw = response.read()
            metadata.update(status=response.status,final_url=response.url,headers={k:v for k,v in response.headers.items()
                if k.lower() in {'date','content-type','content-encoding','content-length','etag','last-modified','cache-control','age'}})
    except HTTPError as error:
        raw = error.read()
        metadata.update(status=error.code,final_url=error.url,error_type=type(error).__name__)
    except Exception as error:
        metadata.update(status=None,error_type=type(error).__name__)
    metadata['received_at_utc'] = datetime.now(timezone.utc).isoformat()
    if raw is not None:
        path = folder / 'nasdaq100_quote_list.response.bin'
        with path.open('xb') as stream:
            stream.write(raw)
        metadata.update(raw_path=str(path),raw_sha256=sha(raw),raw_bytes=len(raw))
    source = Path(__file__).resolve()
    manifest = dict(schema='ndx_current_quote_list_capture_v1',request=metadata,
        source_hashes={str(source):LOADED},
        historical_backfill_allowed=False,membership_effective_timestamp_verified=False,
        issuer_security_binding_verified=False,selection_performed=False,promotion_allowed=False)
    if sha(source.read_bytes()) != LOADED:
        raise ValueError('Capture source changed after loading')
    manifest_path = folder / 'manifest.json'
    with manifest_path.open('x',encoding='utf8') as stream:
        json.dump(manifest,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    if sha(source.read_bytes()) != LOADED:
        raise ValueError('Capture source changed during publication')
    # Receipt is durable before parsing; parsing failure never erases transport evidence.
    if metadata['status'] != 200 or raw is None:
        print(json.dumps(dict(manifest_sha256=sha(manifest_path.read_bytes()),status=metadata['status'])))
        return
    payload = json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
    data = payload['data']
    rows = data['data']['rows']
    symbols = [row['symbol'] for row in rows]
    if (type(data['totalrecords']) is not int or data['totalrecords']!=len(rows)
        or data['offset']!=0 or data['limit']<len(rows) or len(symbols)!=len(set(symbols))):
        raise ValueError('Complete unique current quote-list denominator required')
    result = dict(schema='ndx_current_quote_list_observation_v1',source_hashes=manifest['source_hashes'] | {
        str(manifest_path):sha(manifest_path.read_bytes()),str(path):sha(raw)},
        observed_security_count=len(rows),provider_display_date=data.get('date'),
        provider_asof=data['data'].get('asOf'),rows=rows,observed_symbols=symbols,
        observation_scope='CURRENT_OFFICIAL_QUOTE_LIST_ENDPOINT_NOT_HISTORICAL_MEMBERSHIP_CERTIFICATE',
        quote_display_time_is_not_membership_effective_time=True,
        security_class_to_issuer_adjudicated=False,historical_backfill_allowed=False,
        source_payload_says_100_issuers=False,point_in_time_membership_verified=False,
        current_tradable_pool_admitted=False,prices_used_for_training=False,promotion_allowed=False)
    output = folder / 'observation.json'
    with output.open('x',encoding='utf8') as stream:
        json.dump(result,stream,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')
    if sha(source.read_bytes()) != LOADED:
        raise ValueError('Capture source changed during observation publication')
    print(json.dumps(dict(manifest_sha256=sha(manifest_path.read_bytes()),observation_sha256=sha(output.read_bytes()),
        status=metadata['status'],rows=len(rows),display_date=data.get('date'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    run(parser.parse_args().output_dir)
