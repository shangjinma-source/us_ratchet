"""One new SEC accession request; never retry the prior blocked company URL."""
import hashlib
import json
from pathlib import Path
import sys
from types import FunctionType
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save
OUTPUT=ROOT/'data/cache/research/current_mstr_sec_split_20260919_v1'
URL='https://www.sec.gov/Archives/edgar/data/1050446/000119312524177515/d858108dex991.htm'

if __name__=='__main__':
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(transport.__file__).resolve(),ROOT/'scripts/ndx_current_22_price_capture_20260919.py')}
    OUTPUT.mkdir(parents=True,exist_ok=False)
    f=transport.capture
    bound=FunctionType(f.__code__,dict(f.__globals__,OUTPUT=OUTPUT),f.__name__,f.__defaults__,f.__closure__)
    row=bound(('mstr_sec_exhibit',URL))
    report=dict(schema='MSTR_SEC_SPLIT_ORIGINAL_CAPTURE_V1',captures=[row],source_hashes=sources,point_in_time_verified=False,promotion_allowed=False,prior_company_url_retried=False)
    p=OUTPUT/'manifest.json';sha=save(p,report)
    for path,h in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h:raise ValueError('Capture source differs')
    print(json.dumps(dict(path=str(p),sha256=sha,http_status=row.get('http_status'))))
