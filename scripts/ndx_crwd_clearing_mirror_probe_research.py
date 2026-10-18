"""One explicitly inferred exchange mirror URL; only actual returned body is evidence."""
import hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
OUTPUT=ROOT/'data/cache/research/remaining_standard_split_evidence_20260912_v1'
if __name__=='__main__':
 target=OUTPUT/'crwd_mirror_manifest.json'
 if target.exists() or (OUTPUT/'crwd_miax.response.bin').exists():raise FileExistsError('Already attempted')
 transport.OUTPUT=OUTPUT
 capture=transport.capture(('crwd_miax','https://www.miaxglobal.com/sites/default/files/alert-files/CRWD_Split_59135.pdf'))
 sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(transport.__file__).resolve())}
 with target.open('xb') as stream:stream.write((json.dumps(dict(schema='INFERRED_URL_ACTUAL_RESPONSE_PROBE',url_discovery='OCC_59135_CONFIRMED_MIRROR_PATH_INFERRED_NOT_ASSERTED',captures=[capture],source_hashes=sources),indent=2,sort_keys=True)+'\n').encode())
 print(json.dumps(dict(path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),status=capture.get('http_status'))))
