"""Capture three specifically requested primary exchange-change documents once."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
OUTPUT=ROOT/'data/cache/research/current_101_khc_exchange_20260919_v1'
URLS={
 'nasdaq_khc_press_release':'https://www.nasdaq.com/press-release/kraft-heinz-transfer-stock-exchange-listing-nyse-2026-08-26',
 'sec_khc_8k':'https://www.sec.gov/Archives/edgar/data/1637459/000163745926000057/khc-20260824.htm',
 'miax_khc_opening_market':'https://www.miaxglobal.com/alert/2026/09/14/miax-options-exchanges-change-market-underlying-security-used-openings-0'}
if __name__=='__main__':
 OUTPUT.mkdir(parents=True,exist_ok=False);transport.OUTPUT=OUTPUT
 with ThreadPoolExecutor(max_workers=3) as executor:captures=list(executor.map(transport.capture,URLS.items()))
 sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(transport.__file__).resolve())}
 path=OUTPUT/'manifest.json'
 with path.open('xb') as stream:stream.write((json.dumps(dict(schema='KHC_EXCHANGE_TRANSFER_PRIMARY_RESPONSE_CAPTURE_NOT_INDEX_REMOVAL_ADJUDICATION',captures=captures,source_hashes=sources),indent=2,sort_keys=True)+'\n').encode())
 print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),statuses=[(x['name'],x.get('http_status')) for x in captures])))
