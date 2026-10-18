"""One receipt per missing current CIK; preserve old captures and all HTTP failures."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
from scripts.ndx_current_22_price_capture_20260919 import save
from scripts import ndx_current101_conditional_issuer_map_20260919 as mapping

OUTPUT = ROOT/'data/cache/research/current_92_sec_submissions_capture_20260919_v1'
MAP = ROOT/'data/cache/research/current101_conditional_issuer_map_20260919_v1/issuer_map.json'
MAP_SHA = '491a46b575cff58df7c53886a47d1325c2184dcd033b2b357928678d92143890'
SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def build_plan():
    raw = MAP.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MAP_SHA:
        raise ValueError('Hard reviewed issuer map differs')
    original = json.loads(raw)
    if mapping.build() != original:
        raise ValueError('Original current issuer map no longer reproduces')
    rows = [dict(ticker=r['ticker'], candidate_cik=r['cik']) for r in original['rows']
            if not r['september_current_issuer_observation_available']]
    ciks = sorted({r['candidate_cik'] for r in rows})
    known = {r['cik'] for r in original['rows'] if r['september_current_issuer_observation_available']}
    if len(rows) != 92 or len(ciks) != 91 or set(ciks) & known:
        raise ValueError('Exact 92 old ticker /91 new CIK queries required')
    sources = dict(original['source_hashes'])
    sources.update({str(SOURCE): LOADED, str(MAP): MAP_SHA})
    for path in (Path(transport.__file__).resolve(), Path(mapping.__file__).resolve(),
                 ROOT/'scripts/ndx_current_22_price_capture_20260919.py'):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(schema='CURRENT_92_SEC_SUBMISSIONS_QUERY_PLAN_V1', rows=rows, query_ciks=ciks,
                source_hashes=sources, prior_cik_is_query_candidate_not_new_identity_proof=True,
                preexisting_nine_ciks_requested=False, historical_identity_verified=False,
                point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    plan = build_plan()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    plan_path = OUTPUT/'plan.json'
    plan_sha = save(plan_path, plan)
    transport.OUTPUT = OUTPUT
    requests = [(cik, 'https://data.sec.gov/submissions/CIK'+cik+'.json') for cik in plan['query_ciks']]
    captures = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for capture in pool.map(transport.capture, requests):
            captures.append(capture)
            print(json.dumps(dict(completed=len(captures), planned=91, cik=capture['name'],
                                  http_status=capture.get('http_status'))), flush=True)
    for path, expected in plan['source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Query source changed')
    path = OUTPUT/'manifest.json'
    sha = save(path, dict(schema='CURRENT_92_SEC_SUBMISSIONS_RAW_CAPTURE_V1',
                         plan_path=str(plan_path), plan_sha256=plan_sha, captures=captures,
                         source_hashes=plan['source_hashes'], current_identity_adjudicated=False,
                         historical_identity_verified=False, provider_price_identity_bound=False,
                         point_in_time_verified=False, promotion_allowed=False,
                         live_registry_modified=False, no_retry_performed=True))
    print(json.dumps(dict(path=str(path), sha256=sha,
                          successful=sum(c.get('http_status') == 200 for c in captures))))
