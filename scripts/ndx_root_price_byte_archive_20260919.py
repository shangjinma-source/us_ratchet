"""Preserve present mutable CSV bytes; does not change any running verifier."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_exact_price_cache_drift_research as drift
MANIFEST=ROOT/'data/cache/research/selected_delta_drift_snapshot_20260919_v1/manifest.json'
MANIFEST_SHA='beb22a53d179a725e359272273b14c8fc6ed6fe669e0fac574c0a4ff5f45fb9e'
OUTPUT=ROOT/'data/cache/research/root_price_byte_archive_20260919_v1'
SOURCE=Path(__file__).resolve()
LOADED=drift.file_sha(SOURCE)


def capture():
    if drift.file_sha(MANIFEST)!=MANIFEST_SHA:raise ValueError('Hard numerical snapshot manifest differs')
    manifest=json.loads(MANIFEST.read_bytes());contract=drift.load_contract()
    expected={p:h for p,h in manifest['historical_expected_source_hashes'].items()
              if Path(p).parent==ROOT/'data/cache' and Path(p).suffix=='.csv'}
    if len(expected)!=111 or not set(contract['exceptions'])<=set(expected):raise ValueError('Exact 111-root-price scope required')
    drift.verify_expected_sources(expected,contract)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    rows=[];started=datetime.now(timezone.utc).isoformat()
    for path,historical in sorted(expected.items()):
        raw=Path(path).read_bytes();observed=hashlib.sha256(raw).hexdigest()
        gap=contract['exceptions'].get(path)
        if observed!=(gap['observed_current_sha256'] if gap else historical):raise ValueError('Observed source changed before archival')
        target=OUTPUT/(Path(path).stem+'.'+observed+'.csv')
        with target.open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        if drift.file_sha(target)!=observed or drift.file_sha(path)!=observed:raise ValueError('Byte preservation check failed')
        rows.append(dict(original_path=path,expected_historical_sha256=historical,
            observed_at_capture_sha256=observed,archived_path=str(target),archived_sha256=observed,bytes=len(raw),
            historical_expected_bytes_preserved=observed==historical,
            archival_role='UNRESOLVED_HISTORICAL_GAP_CURRENT_OBSERVATION' if gap else 'EXACT_EXPECTED_HISTORICAL_BYTES'))
    sources={str(SOURCE):LOADED,str(drift.SOURCE):drift.LOADED,str(MANIFEST):MANIFEST_SHA,
             **contract['authority_source_hashes'],**{r['archived_path']:r['archived_sha256'] for r in rows}}
    for p,h in sources.items():
        if drift.file_sha(p)!=h:raise ValueError('Archive source differs')
    drift.verify_expected_sources(expected,contract)
    report=dict(schema='NDX_MUTABLE_ROOT_PRICE_EXACT_BYTE_ARCHIVE_V1',captured_started_at_utc=started,
        captured_finished_at_utc=datetime.now(timezone.utc).isoformat(),file_count=len(rows),
        historical_expected_bytes_preserved_count=sum(r['historical_expected_bytes_preserved'] for r in rows),
        unresolved_historical_gap_count=sum(not r['historical_expected_bytes_preserved'] for r in rows),
        rows=rows,source_hashes=sources,original_paths_modified=False,
        active_verifiers_modified=False,numerical_inputs_replaced=False,training_performed=False,
        historical_full_source_closure_recovered=False,point_in_time_verified=False,promotion_allowed=False)
    target=OUTPUT/'archive_manifest.json'
    raw=(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    with target.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    for p,h in sources.items():
        if drift.file_sha(p)!=h:raise ValueError('Archive source changed at publication')
    drift.verify_expected_sources(expected,contract)
    return dict(path=str(target),sha256=drift.file_sha(target),files=111,
        historical_exact=report['historical_expected_bytes_preserved_count'],historical_gaps=report['unresolved_historical_gap_count'])


if __name__=='__main__':print(json.dumps(capture()))
