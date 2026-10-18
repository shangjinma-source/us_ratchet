"""EA raw-slot inspection and dated issuer evidence; no quote requests or repairs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'ea_historical_identity_gap_review_20260912_v1'
INDEX=BASE/'provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json'
INDEX_SHA='5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117'
DOCUMENTS=(
 ('completed_merger_sec_8k','https://www.sec.gov/Archives/edgar/data/712515/000114036126031157/ef20079099_8k.htm'),
 ('completed_merger_issuer','https://www.ea.com/security/news/ea-announces-completion-of-acquisition'))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if sha(INDEX)!=INDEX_SHA:raise ValueError('External channel index differs')
    index=json.loads(INDEX.read_bytes());sources={str(INDEX):INDEX_SHA}
    channel,=index['provider_channels']['EA']
    path=Path(channel['path'])
    if sha(path)!=channel['sha256']:raise ValueError('Bound EA body differs')
    sources[str(path)]=channel['sha256']
    raw=path.read_bytes();chart,=json.loads(gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw)['chart']['result']
    quote,=chart['indicators']['quote'];slots=[]
    for ordinal,stamp in enumerate(chart['timestamp']):
        day=datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date().isoformat()
        values={field:quote[field][ordinal] for field in ('open','close','volume')}
        finite=all(type(values[field]) in (int,float) and math.isfinite(values[field]) and values[field]>0 for field in ('open','close'))
        slots.append(dict(session=day,**values,finite_positive_open_close=finite))
    local_filings=[]
    for relative in (
        'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0000712515/000071251522000011/ea-20220331.htm',
        'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec/issuer_0000712515/000162828026033617/ea-20260331.htm'):
        filing=ROOT/relative;sidecar=Path(str(filing)+'.manifest.json');meta=json.loads(sidecar.read_bytes())
        sources[str(filing)]=sha(filing);sources[str(sidecar)]=sha(sidecar)
        soup=BeautifulSoup(filing.read_bytes(),'html.parser')
        facts=[dict(name=node.get('name'),context=node.get('contextref'),value=node.get_text(' ',strip=True))
               for node in soup.find_all(lambda node:node.name and node.name.lower().endswith('nonnumeric'))
               if node.get('name','').split(':')[-1] in ('EntityCentralIndexKey','EntityRegistrantName','TradingSymbol','Security12bTitle','SecurityExchangeName')]
        if not any(row['name']=='dei:EntityCentralIndexKey' and row['value']=='0000712515' for row in facts):raise ValueError('Historical filing CIK differs')
        local_filings.append(dict(path=str(filing),sha256=sha(filing),capture_metadata=meta,explicit_inline_identity_facts=facts))
    local_prices=[]
    for relative in ('data/cache/EA.csv','data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw/EA.csv','data/cache/research/ndx_v11_current_price_basis_v1/raw/EA.csv'):
        csv_path=ROOT/relative;sources[str(csv_path)]=sha(csv_path)
        rows=list(csv.DictReader(io.StringIO(csv_path.read_text(encoding='utf-8-sig'))))
        dates=[row['Date'][:10] for row in rows]
        sidecar=Path(str(csv_path)+'.manifest.json');meta=json.loads(sidecar.read_bytes()) if sidecar.exists() else None
        if meta:
            sources[str(sidecar)]=sha(sidecar)
            if meta.get('content_sha256')!=sha(csv_path):raise ValueError('Local price manifest differs')
        local_prices.append(dict(path=str(csv_path),sha256=sha(csv_path),rows=len(rows),first_date=min(dates),last_date=max(dates),sidecar=meta,
                                 original_http_body_available_in_this_source=False,not_used_to_patch_new_provider_raw=True))
    OUTPUT.mkdir(parents=True,exist_ok=False);transport.OUTPUT=OUTPUT
    with ThreadPoolExecutor(max_workers=2) as executor:captures=list(executor.map(transport.capture,DOCUMENTS))
    sec=next(row for row in captures if row['name']=='completed_merger_sec_8k')
    verified=False
    if sec.get('http_status')==200:
        text=BeautifulSoup(Path(sec['raw_path']).read_bytes(),'html.parser').get_text(' ',strip=True)
        verified=all(fragment in text for fragment in ('On August 4, 2026','prior to the opening of trading on August 5, 2026','Trading of the Company Common Stock on Nasdaq was halted after the close of trading on the Closing Date.'))
    for capture in captures:
        if capture.get('raw_path'):sources[capture['raw_path']]=capture['raw_sha256']
    valid=[row for row in slots if row['finite_positive_open_close']]
    report=dict(schema='EA_HISTORICAL_IDENTITY_AND_PROVIDER_SLOT_DIAGNOSTIC',source_hashes=sources,captures=captures,
                provider_meta=chart['meta'],all_provider_slots=slots,slot_count=len(slots),finite_open_close_slot_count=len(valid),
                first_finite_open_close=valid[0]['session'],last_finite_open_close=valid[-1]['session'],
                regular_market_time_new_york=datetime.fromtimestamp(chart['meta']['regularMarketTime'],ZoneInfo('America/New_York')).isoformat(),
                post_aug4_finite_slots=[row for row in slots if row['session']>'2026-08-04' and row['finite_positive_open_close']],
                post_aug4_null_slots=[row['session'] for row in slots if row['session']>'2026-08-04' and not row['finite_positive_open_close']],
                local_dated_filing_identity=local_filings,existing_local_price_sources=local_prices,
                sec_completed_merger_and_halt_raw_verified=verified,
                adjudication='Historical EA issuer CIK and ticker are locally documented. Current provider meta alone cannot bind old history. Forty timestamp slots are not forty valid trading bars; finite quotes after the announced halt are not certified trades. The entire 2022-2024 training interval is missing.',
                wrong_security_identity_established=False,provider_trade_validity_certified=False,new_raw_discarded=False,
                historical_price_restored=False,point_in_time_verified=False,promotion_allowed=False,no_new_quote_requests=True)
    for source in (Path(__file__).resolve(),Path(transport.__file__).resolve()):sources[str(source)]=sha(source)
    for source,digest in sources.items():
        if sha(source)!=digest:raise ValueError('Source drift')
    path=OUTPUT/'report.json'
    with path.open('xb') as stream:stream.write((json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=sha(path),statuses=[(r['name'],r.get('http_status')) for r in captures],slots=len(slots),finite=len(valid),sec_verified=verified)))


if __name__=='__main__':main()
