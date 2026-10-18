"""One externally evidenced 26-file drift exception, never a generic CSV waiver."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
REPORT=ROOT/'data/cache/research/delta_source_drift_20260919_v1/historical_source_drift.json'
REPORT_SHA='8295ca44ae9b98ab67e7a516f408f0c4e501f52e66200ab2df575463526f60c5'
MANIFEST=ROOT/'data/cache/research/delta_paired_snapshot_20260912_v1/manifest.json'
MANIFEST_SHA='a784d343acf4363530b2a452ef8e11709b5d5275a177fdd86dc7b4592918b891'
SELECTED_PLAN=ROOT/'data/cache/research/delta_selected_input_20260912_v1/plan.json'
SELECTED_PLAN_SHA='f0ff0242f08dcb62ceb19d5650db811fe8d0d83741f7ecc995b6a3945cf15266'


def file_sha(path):
    p=Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def load_contract():
    sources={str(REPORT):REPORT_SHA,str(MANIFEST):MANIFEST_SHA,str(SELECTED_PLAN):SELECTED_PLAN_SHA,str(SOURCE):LOADED}
    for p,h in sources.items():
        if file_sha(p)!=h:raise ValueError('Drift authority or loaded source differs: '+p)
    report=json.loads(REPORT.read_bytes());manifest=json.loads(MANIFEST.read_bytes());plan=json.loads(SELECTED_PLAN.read_bytes())
    if report['schema']!='ndx_delta_historical_source_drift_diagnosis_20260919_v1' or report['changed_count']!=26:
        raise ValueError('Exact externally recorded drift report required')
    exceptions={}
    for row in report['changes']:
        path=str(Path(row['path']).resolve())
        if path in exceptions or Path(path).parent!=ROOT/'data/cache' or Path(path).suffix!='.csv' or row['category']!='MUTABLE_ROOT_PRICE_CSV':
            raise ValueError('Exact root price-file drift coordinate required')
        expected=row['expected_historical_sha256'];observed=row['observed_current_sha256']
        if (expected==observed or manifest['source_hashes'].get(path)!=expected or plan['source_hashes'].get(path)!=expected
                or report['original_expected_sources'].get(path)!=expected):
            raise ValueError('Historical mapping differs from hard manifest and plan')
        exceptions[path]=dict(expected_historical_sha256=expected,observed_current_sha256=observed)
    if len(exceptions)!=26:raise ValueError('Exact 26-file exception denominator required')
    return dict(schema='ndx_exact_price_cache_drift_contract_v1',authority_source_hashes=sources,exceptions=exceptions,
                historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)


def verify_expected_sources(expected_sources,contract):
    """Return verified old sources separately from exact old/current observations."""
    if contract!=load_contract():raise ValueError('Contract differs from the hard-bound 26-file authority')
    verified={};observations=[]
    for path,expected in contract['authority_source_hashes'].items():
        if file_sha(path)!=expected:raise ValueError('Drift authority/source changed: '+path)
        verified[path]=expected
    # Check all observed gaps even if a caller supplies a smaller expected map.
    for path,entry in contract['exceptions'].items():
        if file_sha(path)!=entry['observed_current_sha256']:
            raise ValueError('Recorded current CSV changed again: '+path)
    for path,expected in expected_sources.items():
        path=str(Path(path).resolve())
        if path in contract['exceptions']:
            entry=contract['exceptions'][path]
            if expected!=entry['expected_historical_sha256']:
                raise ValueError('Different historical SHA cannot use recorded CSV exception: '+path)
            observations.append(dict(path=path,**entry,historical_bytes_verified=False,current_observation_unchanged=True))
        else:
            if file_sha(path)!=expected:raise ValueError('Non-exempt original source changed: '+path)
            if path in verified and verified[path]!=expected:raise ValueError('Conflicting verified source')
            verified[path]=expected
    return dict(verified_source_hashes=verified,historical_gap_observations=observations,
                historical_full_source_closure_verified=False)
