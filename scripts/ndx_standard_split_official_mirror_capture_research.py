"""Distinct exchange-hosted/issuer documents after bounded OCC transport failures."""
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
 ('amzn_20220606_miax','https://www.miaxglobal.com/sites/default/files/alert-files/AMZN_revsplit__50496.pdf'),
 ('cprt_20221104_miax','https://www.miaxglobal.com/sites/default/files/alert-files/CPRT_Split_51286.pdf'),
 ('cprt_20230822_miax','https://www.miaxglobal.com/sites/default/files/alert-files/CPRT_Split_53008.pdf'),
 ('mnst_20230328_issuer_proxy','https://investors.monsterbevcorp.com/static-files/99bd00c9-5a17-4f62-a64b-3a011c5c85fa'),
 ('pcar_20230208_miax','https://www.miaxglobal.com/sites/default/files/alert-files/PCAR_Split_51729.pdf'))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    previous=OUTPUT/'manifest.json'
    if sha(previous)!='cec2ed74cdcf0fadd117f7a35c567db8b9adf1efee9b5b87f45796d7a90474e7':raise ValueError('Previous failed requests changed')
    previous_document=json.loads(previous.read_bytes())
    previous_urls={row['request_url'] for row in previous_document['captures']}
    if previous_urls & {url for name,url in DOCUMENTS}:raise ValueError('Repeated request')
    if (OUTPUT/'supplement_manifest.json').exists():raise FileExistsError('Already captured supplement')
    transport.OUTPUT=OUTPUT
    with ThreadPoolExecutor(max_workers=2) as executor:captures=list(executor.map(transport.capture,DOCUMENTS))
    sources={str(previous):sha(previous),str(Path(__file__).resolve()):sha(__file__),str(Path(transport.__file__).resolve()):sha(transport.__file__)}
    report=dict(schema='OFFICIAL_SEPARATE_HOSTED_DOCUMENT_CAPTURE',source_hashes=sources,captures=captures,no_previous_url_retries=True,no_quote_requests=True)
    path=OUTPUT/'supplement_manifest.json'
    with path.open('xb') as stream:stream.write((json.dumps(report,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=sha(path),statuses=[(r['name'],r.get('http_status')) for r in captures])))


if __name__=='__main__':main()
