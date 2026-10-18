"""Capture the distinct March 27 updated OCC memo hosted by MIAX once."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
OUTPUT=ROOT/'data/cache/research/standard_split_official_evidence_20260912_v1'

if __name__=='__main__':
    target=OUTPUT/'mnst_updated_manifest.json'
    if target.exists() or (OUTPUT/'mnst_20230328_updated_miax.response.bin').exists():raise FileExistsError('Do not repeat captured request')
    transport.OUTPUT=OUTPUT
    capture=transport.capture(('mnst_20230328_updated_miax','https://www.miaxglobal.com/sites/default/files/alert-files/MNST_Split_52178.pdf'))
    sources={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__).resolve(),Path(transport.__file__).resolve())}
    report=dict(schema='MNST_DISTINCT_UPDATED_OCC_MEMO_CAPTURE',captures=[capture],source_hashes=sources)
    with target.open('xb') as stream:stream.write((json.dumps(report,indent=2,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),status=capture.get('http_status'))))
