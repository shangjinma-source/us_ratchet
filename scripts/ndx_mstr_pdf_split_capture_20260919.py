"""Single request for the issuer-hosted July 11 2024 Form 8-K PDF mirror."""
import hashlib,json
from pathlib import Path
from types import FunctionType
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save
OUTPUT=ROOT/'data/cache/research/current_mstr_pdf_split_20260919_v1'
URL='https://assets.contentstack.io/v3/assets/bltb564490bc5201f31/blt18e2241b888f48d6/668fc60700db89f5c1ea3e76/form-8-k_07-11-2024.pdf'
if __name__=='__main__':
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(transport.__file__).resolve(),ROOT/'scripts/ndx_current_22_price_capture_20260919.py')}
    OUTPUT.mkdir(parents=True,exist_ok=False);f=transport.capture
    bound=FunctionType(f.__code__,dict(f.__globals__,OUTPUT=OUTPUT),f.__name__,f.__defaults__,f.__closure__)
    row=bound(('mstr_pdf',URL));report=dict(schema='MSTR_PDF_SPLIT_ORIGINAL_CAPTURE_V1',captures=[row],source_hashes=sources,point_in_time_verified=False,promotion_allowed=False,failed_urls_retried=False)
    p=OUTPUT/'manifest.json';sha=save(p,report)
    for path,h in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h:raise ValueError('Capture source differs')
    print(json.dumps(dict(path=str(p),sha256=sha,http_status=row.get('http_status'))))
