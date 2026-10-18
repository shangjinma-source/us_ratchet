"""One request per newly located official action document; no market-data requests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
OUTPUT=ROOT/'data/cache/research/standard_split_official_evidence_20260912_v1'
DOCUMENTS=(
 ('amzn_20220606_occ50496','https://infomemo.theocc.com/infomemos?number=50496'),
 ('cprt_20221104_occ51286','https://infomemo.theocc.com/infomemos?number=51286'),
 ('cprt_20230822_occ53008','https://infomemo.theocc.com/infomemos?number=53008'),
 ('dxcm_20220613_occ50507_miax','https://www.miaxglobal.com/sites/default/files/alert-files/DXCM_Split__50507.pdf'),
 ('mnst_20230328_occ52066','https://infomemo.theocc.com/infomemos?number=52066'),
 ('odfl_20240328_occ54255_miax','https://www.miaxglobal.com/sites/default/files/alert-files/ODFL_Split_54255.pdf'),
 ('pcar_20230208_occ51729','https://infomemo.theocc.com/infomemos?number=51729'),
 ('tsla_20220825_issuer_8k','https://ir.tesla.com/_flysystem/s3/sec/000156459022028207/tsla-8k_20220804-gen.pdf'))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    OUTPUT.mkdir(parents=True,exist_ok=False);transport.OUTPUT=OUTPUT
    with ThreadPoolExecutor(max_workers=2) as executor:captures=list(executor.map(transport.capture,DOCUMENTS))
    sources={str(Path(__file__).resolve()):sha(__file__),str(Path(transport.__file__).resolve()):sha(transport.__file__)}
    report=dict(schema='STANDARD_SPLIT_OFFICIAL_RAW_CAPTURE',source_hashes=sources,captures=captures,maximum_requests_per_url=1,
                provider_prices_not_requested=True,point_in_time_verified=False,promotion_allowed=False)
    path=OUTPUT/'manifest.json'
    with path.open('xb') as stream:stream.write((json.dumps(report,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=sha(path),statuses=[(row['name'],row.get('http_status')) for row in captures])))


if __name__=='__main__':main()
