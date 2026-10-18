"""Bind execution clarifications without changing continuous OHLC or weights."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tmp/fixed12_monthly_limit_inputs_20261014_v1/prepared.json'
OUTPUT=ROOT/'tmp/fixed12_monthly_limit_inputs_20261014_v2'


if __name__=='__main__':
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='bfbdf94f461faccab480132711f2e903c0830a2ded95b7c1f9f0b315b7619106':raise ValueError('Prior frozen input differs')
    result=json.loads(raw)
    name='research_contracts/fixed12_monthly_limit_execution_clarifications_20261014_v1.json'
    notes=(ROOT/name).read_bytes()
    result['execution_clarifications']=json.loads(notes)
    result['source_hashes'][name]=hashlib.sha256(notes).hexdigest()
    result['source_hashes'][str(SOURCE)]=hashlib.sha256(raw).hexdigest()
    result['source_hashes'][str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for path,digest in result['source_hashes'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed: '+path)
    OUTPUT.mkdir()
    path=OUTPUT/'prepared.json'
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    draft=dict(status='DRAFT_NOT_EXECUTABLE_PROVIDER_AND_RUNNER_PINS_PENDING',input_path=str(path),input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        maximum_book_calls=3,maximum_search_calls=0,modes=[m['mode'] for m in result['modes']],
        initial_cash_per_independent_mode='20000',monthly_cash_reset=False,create_only=True,automatic_retry_allowed=False,
        source_hashes=result['source_hashes'],source_dataset_review_pending=True)
    with (OUTPUT/'registration_draft.json').open('x',encoding='utf-8') as f:json.dump(draft,f,indent=2)
    print(draft['input_sha256'])
