"""Exact immutable byte resolution; unresolved historical bytes stay unresolved."""
import hashlib
import json
from pathlib import Path
from backtest import ndx_exact_price_cache_drift_research as drift

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=drift.file_sha(SOURCE)
ARCHIVE=ROOT/'data/cache/research/root_price_byte_archive_20260919_v1/archive_manifest.json'
ARCHIVE_SHA='159c30f8d544a829b19898ce0d53bcd2d0a47d993ed22ec195fee08a96bbf260'
INVENTORY=ROOT/'data/cache/research/selected_delta_drift_snapshot_20260919_v1/manifest.json'
INVENTORY_SHA='beb22a53d179a725e359272273b14c8fc6ed6fe669e0fac574c0a4ff5f45fb9e'


def strict(sources):
    for path,sha in sources.items():
        if drift.file_sha(path)!=sha:raise ValueError('Archive authority/strict live source differs: '+path)


def merge(destination,addition):
    for p,h in addition.items():
        if p in destination and destination[p]!=h:raise ValueError('Source SHA conflict')
        destination[p]=h


def load_contract():
    sources={str(ARCHIVE):ARCHIVE_SHA,str(INVENTORY):INVENTORY_SHA,str(SOURCE):LOADED}
    strict(sources)
    archive=json.loads(ARCHIVE.read_bytes());inventory=json.loads(INVENTORY.read_bytes());old=drift.load_contract()
    merge(sources,old['authority_source_hashes']);merge(sources,archive['source_hashes'])
    strict(sources)
    expected={p:h for p,h in inventory['historical_expected_source_hashes'].items() if Path(p).parent==ROOT/'data/cache' and Path(p).suffix=='.csv'}
    rows={}
    for row in archive['rows']:
        p=row['original_path'];h=row['expected_historical_sha256'];actual=row['archived_sha256'];target=Path(row['archived_path'])
        if p in rows or expected.get(p)!=h or target!=ARCHIVE.parent/(Path(p).stem+'.'+actual+'.csv'):
            raise ValueError('Exact archive address/inventory required')
        if actual!=row['observed_at_capture_sha256'] or target.stat().st_size!=row['bytes'] or drift.file_sha(target)!=actual:raise ValueError('Archived bytes differ')
        gap=old['exceptions'].get(p)
        if gap:
            if h!=gap['expected_historical_sha256'] or actual!=gap['observed_current_sha256'] or row['historical_expected_bytes_preserved'] is not False or row['archival_role']!='UNRESOLVED_HISTORICAL_GAP_CURRENT_OBSERVATION':raise ValueError('Historical gap cannot be upgraded')
        elif actual!=h or row['historical_expected_bytes_preserved'] is not True or row['archival_role']!='EXACT_EXPECTED_HISTORICAL_BYTES':raise ValueError('Exact historical byte match required')
        rows[p]=row
    if set(rows)!=set(expected) or len(rows)!=111 or sum(r['historical_expected_bytes_preserved'] for r in rows.values())!=85:raise ValueError('Exact 111/85/26 denominator required')
    return dict(schema='ROOT_PRICE_ARCHIVE_RESOLUTION_CONTRACT_V1',rows=rows,authority_source_hashes=sources,historical_full_source_closure_recovered=False,point_in_time_verified=False,promotion_allowed=False)


def verify_expected_sources(expected_sources,contract):
    if contract!=load_contract():raise ValueError('Contract must equal hard archive authority')
    live=dict(contract['authority_source_hashes']);resolved=[];gaps=[]
    for path,historical in expected_sources.items():
        if type(path) is not str or not Path(path).is_absolute() or str(Path(path).resolve())!=path:raise ValueError('Exact absolute original source path required')
        row=contract['rows'].get(path)
        if row:
            if historical!=row['expected_historical_sha256']:raise ValueError('Different old SHA cannot resolve archive')
            evidence=dict(original_path=path,expected_historical_sha256=historical,archived_path=row['archived_path'],archived_sha256=row['archived_sha256'],original_live_path_verified=False)
            if row['historical_expected_bytes_preserved']:
                resolved.append(dict(evidence,historical_bytes_exact=True))
            else:gaps.append(dict(evidence,historical_bytes_recovered=False,role='SEALED_CURRENT_OBSERVATION_NOT_HISTORICAL_BYTES'))
        else:
            strict({path:historical});merge(live,{path:historical})
    strict(live)
    return dict(live_verified_source_hashes=live,archive_resolutions=resolved,historical_gap_observations=gaps,historical_full_source_closure_recovered=False,point_in_time_verified=False,promotion_allowed=False)


def read_historical_bytes(original_path,expected_sha256,contract):
    """Resolve only the 85 exact bytes; never substitute the 26 observations."""
    verified=verify_expected_sources({original_path:expected_sha256},contract)
    if len(verified['archive_resolutions'])!=1:raise ValueError('Historical price bytes were not recovered')
    record=verified['archive_resolutions'][0];raw=Path(record['archived_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Archive changed during byte read')
    return raw
