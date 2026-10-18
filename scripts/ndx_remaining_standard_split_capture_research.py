"""One request per previously uncaptured official split document, research only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
OUTPUT=ROOT/'data/cache/research/remaining_standard_split_evidence_20260912_v1'
URLS={
 'bkng':'https://www.miaxglobal.com/sites/default/files/alert-files/BKNG_Split_58460.pdf',
 'mnst':'https://www.miaxglobal.com/sites/default/files/alert-files/MNST_Split_59374.pdf',
 'lcid':'https://www.miaxglobal.com/sites/default/files/alert-files/LCID_Reverse_Split_57169.pdf',
 'fast':'https://s23.q4cdn.com/591718779/files/doc_financials/2025/Q1/04-23-25-Stock-Split-Press-Release-Final-no-exhibit.pdf',
 'lrcx':'https://newsroom.lamresearch.com/2024-05-21-Lam-Research-Corporation-Announces-10-Billion-Share-Repurchase-Authorization-and-a-10-for-1-Stock-Split',
 'lrcx_identity':'https://www.sec.gov/Archives/edgar/data/707549/000070754924000117/lrcx-20240925.htm',
 'panw':'https://investors.paloaltonetworks.com/static-files/96a965da-52c9-4202-9b64-36acac236357',
 'crwd':'https://ir.crowdstrike.com/static-files/aad9615c-cb35-40f0-b619-67eb24bb0c6b',
 'klac':'https://ir.kla.com/sec-filings/all-sec-filings/content/0001193125-26-212093/d116682dex991.htm',
 'nflx':'https://www.sec.gov/Archives/edgar/data/1065280/000106528025000407/ex991_q425stocksplit.htm',
 'orly':'https://corporate.oreillyauto.com/wp-content/uploads/2025/07/2025-Stock-Split-FAQ.pdf',
}
if __name__=='__main__':
 OUTPUT.mkdir(parents=True,exist_ok=False)
 transport.OUTPUT=OUTPUT
 with ThreadPoolExecutor(max_workers=3) as executor:captures=list(executor.map(transport.capture,URLS.items()))
 sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(transport.__file__).resolve())}
 report=dict(schema='REMAINING_STANDARD_SPLIT_OFFICIAL_CAPTURE',captures=captures,source_hashes=sources,pit_verified=False,provider_identity_verified=False)
 path=OUTPUT/'manifest.json'
 with path.open('xb') as stream:stream.write((json.dumps(report,indent=2,sort_keys=True)+'\n').encode())
 print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),statuses=[(x['name'],x.get('http_status')) for x in captures])))
