"""Capture a distinct clearing memo to close the missing FTNT first-trading-day fact."""
import hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
OUTPUT=ROOT/'data/cache/research/standard_split_registry_20260912_v2'
if __name__=='__main__':
 OUTPUT.mkdir(parents=True,exist_ok=False);transport.OUTPUT=OUTPUT
 row=transport.capture(('ftnt_occ50626_miax','https://www.miaxglobal.com/sites/default/files/alert-files/FTNT_Split__50626.pdf'))
 sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(transport.__file__).resolve())}
 path=OUTPUT/'ftnt_manifest.json'
 with path.open('xb') as stream:stream.write((json.dumps(dict(schema='FTNT_FIRST_ADJUSTED_SESSION_NEW_OFFICIAL_MEMO',captures=[row],source_hashes=sources),indent=2,sort_keys=True)+'\n').encode())
 print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),status=row.get('http_status'))))
