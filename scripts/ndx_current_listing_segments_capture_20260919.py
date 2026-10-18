"""One request per three official listing-segment documents, raw-only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
OUTPUT=ROOT/'data/cache/research/current_listing_segments_20260919_v1'
URLS={
 'hona_when_issued':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-399',
 'sndk_when_issued':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-38',
 'fer_us_listing':'https://www.nasdaq.com/press-release/ferrovial-begins-trading-on-nasdaq-under-symbol-fer-2024-05-09'}
if __name__=='__main__':
 OUTPUT.mkdir(parents=True,exist_ok=False)
 transport.OUTPUT=OUTPUT
 with ThreadPoolExecutor(max_workers=3) as executor:
  captures=list(executor.map(transport.capture,URLS.items()))
 sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(transport.__file__).resolve())}
 path=OUTPUT/'manifest.json'
 with path.open('xb') as handle:
  handle.write((json.dumps(dict(schema='OFFICIAL_LISTING_SEGMENT_CAPTURE_NOT_PROVIDER_BINDING',captures=captures,source_hashes=sources),sort_keys=True,indent=2)+'\n').encode())
 print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),statuses=[(row['name'],row.get('http_status')) for row in captures])))
