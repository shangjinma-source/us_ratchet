"""One META channel capture paired with separately sealed FB-to-META notice facts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ndx_identity_source_probe import capture
import scripts.ndx_identity_source_probe as capture_module


def run():
    facts=ROOT/'data/cache/research/identity_public_source_probe_20260912_v1/extracted_facts_20260912.json'
    sources={str(facts):'dfe62747ebce89e8545e6d89d1435803663b3cf8a153ba205be66ba8b513c4e5'}
    for path in (Path(__file__).resolve(),Path(capture_module.__file__).resolve()):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    if hashlib.sha256(facts.read_bytes()).hexdigest()!=sources[str(facts)]:raise ValueError('Bound rename facts drift')
    fact_report=json.loads(facts.read_bytes())
    for path,digest in fact_report['source_hashes'].items():
        if path in sources and sources[path]!=digest:raise ValueError('Source conflict')
        sources[path]=digest
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source drift')
    directory=ROOT/'data/cache/research/meta_historical_price_source_probe_20260912_v1'
    directory.mkdir(parents=True,exist_ok=False)
    now=datetime.now(timezone.utc)
    start=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())
    request=dict(name='yahoo_meta_20220101_through_received_daily_events',method='GET',direct=False,
        url='https://query1.finance.yahoo.com/v8/finance/chart/META?period1='+str(start)+'&period2='+str(int(now.timestamp()))+'&interval=1d&events=div%2Csplits')
    metadata,raw=capture(request)
    if raw is not None:
        path=directory/(metadata['name']+'.response.bin')
        with path.open('xb') as handle:handle.write(raw)
        digest=hashlib.sha256(raw).hexdigest()
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Raw readback differs')
        metadata.update(response_path=str(path),response_sha256=digest,response_bytes=len(raw))
    else:metadata.update(response_path=None,response_sha256=None,response_bytes=0)
    report=dict(schema='ndx_meta_historical_price_source_probe_v1',probes=[metadata],source_hashes=sources,
        requested_end_exclusive_utc=now.isoformat(),observed_at_utc=datetime.now(timezone.utc).isoformat(),
        separately_extracted_nasdaq_rename_fact=fact_report['nasdaq_meta_event'],
        provider_request_symbol='META',historical_price_rows_are_not_claimed_to_have_historical_ticker_META=True,
        price_usage='QUOTE_PRICE_RETURN_CANDIDATE_NOT_ADJCLOSE_TOTAL_RETURN',
        old_FB_cache_read_or_stitched=False,old_training_rerun=False,cache_modified=False,
        provider_historical_identity_binding_verified=False,point_in_time_verified=False,promotion_allowed=False)
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source drift')
    path=directory/'manifest.json';encoded=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
    with path.open('xb') as handle:handle.write(encoded)
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(encoded).hexdigest(),http_status=metadata['http_status'],bytes=metadata['response_bytes'])))


if __name__=='__main__':run()
