"""Distinct official alternatives; never repeat failed document URLs."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
OUTPUT=ROOT/'data/cache/research/remaining_standard_split_evidence_20260912_v1'
URLS={
 'nflx_miax':'https://www.miaxglobal.com/sites/default/files/alert-files/NFLX_Split_57556.pdf',
 'panw_miax':'https://www.miaxglobal.com/sites/default/files/alert-files/PANW_Split_55607.pdf',
 'fast_miax':'https://www.miaxglobal.com/sites/default/files/alert-files/FAST_Split_56481.pdf',
 'crwd_occ':'https://infomemo.theocc.com/infomemos?number=59135',
 'lrcx_8937':'https://investor.lamresearch.com/download/8937_Lam_Signed_Oct_2024.pdf',
}
if __name__=='__main__':
 target=OUTPUT/'supplement_manifest.json'
 if target.exists() or any((OUTPUT/(name+'.response.bin')).exists() for name in URLS):raise FileExistsError('Already attempted')
 transport.OUTPUT=OUTPUT
 with ThreadPoolExecutor(max_workers=3) as executor:captures=list(executor.map(transport.capture,URLS.items()))
 sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(transport.__file__).resolve())}
 with target.open('xb') as stream:stream.write((json.dumps(dict(schema='DISTINCT_OFFICIAL_SPLIT_ALTERNATIVES',captures=captures,source_hashes=sources),indent=2,sort_keys=True)+'\n').encode())
 print(json.dumps(dict(path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),statuses=[(x['name'],x.get('http_status')) for x in captures])))
